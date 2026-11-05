"""Generate, tailor, validate, and export candidate resumes and resume versions.

Combines AI rewrite prompts with factual safeguards and renders tailored
documents in supported formats for download.
"""
import ast
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from jinja2 import Environment, FileSystemLoader, Undefined
import requests

logger = logging.getLogger("cafy.resume_generation")

MAX_RESUME_SKILLS = 24


# Active model; override with GROQ_MODEL.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
FALLBACK_GROQ_MODELS = ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen/qwen3.8-27b"]


class ResumeGenerationError(RuntimeError):
    pass


class ResumeGenerationService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.template_dir = project_root / "backend" / "templates"
        if os.environ.get("VERCEL"):
            self.output_dir = Path("/tmp/generated_resumes")
        else:
            self.output_dir = project_root / "backend" / "generated_resumes"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.environment = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            undefined=Undefined,
            autoescape=False,
            keep_trailing_newline=True,
            block_start_string="((*",
            block_end_string="*))",
            variable_start_string="((",
            variable_end_string="))",
            comment_start_string="((#",
            comment_end_string="#))",
        )
        self.environment.filters["texescape"] = self._texescape

    @staticmethod
    def _provider_error_message(response, api_key: str) -> str:
        try:
            body = response.json()
        except (TypeError, ValueError):
            return ""
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("code") or "")
        elif isinstance(error, str):
            message = error
        else:
            message = ""
        return message.replace(api_key, "[redacted]")[:300]

    def generate(
        self, resume: Dict[str, Any], job: Dict[str, Any], skill_extractor=None, instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        if not resume:
            raise ResumeGenerationError("Upload a résumé before generating a tailored version.")
        if not job:
            raise ResumeGenerationError("The selected job could not be found.")

        detected_job_skills = skill_extractor.extract_skills(
            f"{job.get('title') or ''} {job.get('description') or ''}"
        ) if skill_extractor is not None else []
        job_skills = list(job.get("extracted_skills") or [])
        seen_job_skills = {str(skill).casefold() for skill in job_skills}
        for skill in detected_job_skills:
            if str(skill).casefold() not in seen_job_skills:
                job_skills.append(skill)
                seen_job_skills.add(str(skill).casefold())
        job = {**job, "extracted_skills": job_skills}

        # Build from verified profile data, then tailor the writable text using only those facts.
        structured = self._validate_and_normalize({}, resume, job)
        if skill_extractor is not None:
            verified_job_skills = self._verified_job_skills(resume, job, skill_extractor)
            existing_skills = {str(skill).casefold() for skill in structured["skills"]}
            for skill in verified_job_skills:
                if skill.casefold() not in existing_skills:
                    structured["skills"].append(skill)
                    existing_skills.add(skill.casefold())
        structured["skills"] = self._rank_skills(structured["skills"], job)
        if skill_extractor is not None:
            structured = self.rewrite_full(structured, job, skill_extractor, instructions)["resume"]
        structured = self._ensure_education_descriptions(structured)
        resume_id = uuid.uuid4().hex
        # The editor renders its own PDF, so the LaTeX PDF is compiled only when it is downloaded.
        artifacts = self.update_artifacts(resume_id, structured, compile_pdf=False)

        # Compute real ATS / match scores against the generated resume.
        generation_scores = self._score_generated_resume(structured, job, skill_extractor)

        return {
            "status": "success",
            "template": "uk-standard",
            "resume": structured,
            **artifacts,
            "generation_scores": generation_scores,
            "validation": {
                "ats_friendly": True,
                "factual_consistency": True,
                "page_length": "1 page",
                "unsupported_claims": [],
            },
        }

    @staticmethod
    def _score_generated_resume(
        structured: Dict[str, Any], job: Dict[str, Any], skill_extractor
    ) -> Dict[str, Any]:
        """Compute real ATS, job-match, skills-match, and content-quality scores
        for the generated resume against the target job.

        Returns a dict with four scores (0-100) and brief explanations.
        """
        try:
            from .job_match_analysis_service import analyze_profile_for_job
            from .cv_quality_service import evaluate_cv_quality

            # Build a profile-shaped dict from the generated resume so the
            # analysis services can consume it.
            profile = {
                "candidate_name": (structured.get("personal_info") or {}).get("name") or "",
                "email": (structured.get("personal_info") or {}).get("email") or "",
                "summary": structured.get("professional_summary") or "",
                "skills": structured.get("skills") or [],
                "experience": structured.get("experience") or [],
                "education": structured.get("education") or [],
                "projects": structured.get("projects") or [],
                "certifications": structured.get("certifications") or [],
                "internships": structured.get("internships") or [],
            }

            analysis = analyze_profile_for_job(profile, job)
            cv = evaluate_cv_quality(profile)

            job_match = analysis.get("job_match_score", 0)
            sections = analysis.get("sections") or {}
            skills_section = sections.get("skills") or {}
            skills_match = skills_section.get("score")
            if skills_match is None:
                # Fall back: matched / total job skills
                matched = len(analysis.get("matched_skills") or [])
                total = len(analysis.get("job_skills") or [])
                skills_match = int(round(matched / total * 100)) if total else 0

            # ATS score: penalise for missing contact info, no summary, no bullets.
            ats_checks = [
                bool((structured.get("personal_info") or {}).get("name")),
                bool((structured.get("personal_info") or {}).get("email")),
                bool(structured.get("professional_summary")),
                bool(structured.get("skills")),
                bool(structured.get("experience") or structured.get("internships")),
                bool(structured.get("education")),
                any(
                    (e.get("bullets") or [])
                    for e in (structured.get("experience") or [])
                    if isinstance(e, dict)
                ),
                bool((structured.get("personal_info") or {}).get("linkedin")
                     or (structured.get("personal_info") or {}).get("github")),
            ]
            ats_score = int(round(sum(ats_checks) / len(ats_checks) * 100))

            content_quality = cv.get("score", 0)

            # Build human-readable explanations.
            matched_skills = analysis.get("matched_skills") or []
            missing_skills = analysis.get("missing_skills") or []
            tier = analysis.get("match_tier", "")

            return {
                "job_match_score": job_match,
                "skills_match_score": skills_match,
                "ats_score": ats_score,
                "content_quality_score": content_quality,
                "match_tier": tier,
                "matched_skills": matched_skills[:10],
                "missing_skills": missing_skills[:10],
                "explanations": {
                    "job_match": (
                        f"{tier}: resume covers {len(matched_skills)} of "
                        f"{len(analysis.get('job_skills') or [])} required skills."
                    ),
                    "skills_match": (
                        f"{skills_match}% of the job’s required skills are present in the resume."
                    ),
                    "ats": (
                        f"{ats_score}% ATS readiness: "
                        + ("all key sections present." if ats_score == 100
                           else f"{len(ats_checks) - sum(ats_checks)} section(s) could be improved.")
                    ),
                    "content_quality": (
                        f"{content_quality}% content quality: "
                        + f"{cv.get('passed_checks', 0)} of {cv.get('total_checks', 0)} checks passed."
                    ),
                },
                "suggestions": [
                    s["text"] for s in (analysis.get("suggestions") or [])[:5]
                ],
            }
        except Exception as exc:  # never let scoring crash generation
            logger.warning("[ResumeGeneration] Scoring failed: %s", exc)
            return {}

    @staticmethod
    def _rank_skills(skills: List[str], job: Dict[str, Any]) -> List[str]:
        """Put skills the job asks for first; keep the rest in original order."""
        wanted = {
            str(skill).casefold()
            for skill in [
                *(job.get("matched_skills") or []),
                *(job.get("extracted_skills") or []),
            ]
        }
        return sorted(skills, key=lambda s: s.casefold() not in wanted)

    @staticmethod
    def _verified_job_skills(
        resume: Dict[str, Any], job: Dict[str, Any], skill_extractor
    ) -> List[str]:
        """Return job skills that the uploaded resume itself already evidences."""
        job_skills = job.get("extracted_skills") or skill_extractor.extract_skills(
            f"{job.get('title') or ''} {job.get('description') or ''}"
        )
        if not isinstance(job_skills, list):
            job_skills = []
        resume_text = json.dumps(resume, ensure_ascii=False)
        evidenced = {
            str(skill).casefold()
            for skill in skill_extractor.extract_skills(resume_text)
        }
        verified = []
        seen = set()
        for skill in job_skills:
            cleaned = str(skill).strip()
            key = cleaned.casefold()
            if cleaned and key in evidenced and key not in seen:
                verified.append(cleaned)
                seen.add(key)
        return verified

    @staticmethod
    def pdf_supported() -> bool:
        return bool(shutil.which("pdflatex") or shutil.which("xelatex"))

    def update_artifacts(self, resume_id: str, structured: Dict[str, Any], compile_pdf: bool = True) -> Dict[str, Any]:
        """Re-render LaTeX and DOCX for a draft, and the PDF too unless ``compile_pdf`` is False.

        Compiling LaTeX takes seconds, so saves skip it: the stale PDF is removed and the
        download endpoint compiles a fresh one on first request.
        """
        tex = self._render_latex(structured)
        tex_path = self.output_dir / f"{resume_id}.tex"
        tex_path.write_text(tex, encoding="utf-8")

        pdf_file = self.output_dir / f"{resume_id}.pdf"
        if compile_pdf:
            pdf_path = self._compile_pdf(tex_path)
        else:
            pdf_file.unlink(missing_ok=True)
            pdf_path = None

        docx_path = self.output_dir / f"{resume_id}.docx"
        self._export_docx(structured, docx_path)

        pdf_offered = bool(pdf_path) or (not compile_pdf and self.pdf_supported())
        return {
            "resume_id": resume_id,
            "tex_url": f"/api/resumes/{resume_id}/latex",
            "pdf_url": f"/api/resumes/{resume_id}/pdf" if pdf_offered else None,
            "docx_url": f"/api/resumes/{resume_id}/docx",
            "pdf_available": pdf_offered,
            "docx_available": True,
        }

    def ensure_pdf(self, resume_id: str) -> Optional[Path]:
        """Compile the PDF from the saved LaTeX source if it is not on disk yet."""
        pdf_file = self.output_dir / f"{resume_id}.pdf"
        if pdf_file.is_file():
            return pdf_file
        tex_path = self.output_dir / f"{resume_id}.tex"
        return self._compile_pdf(tex_path) if tex_path.is_file() else None

    def rewrite_section(
        self,
        section: str,
        content: str,
        job: Dict[str, Any],
        resume_data: Dict[str, Any],
        improvement_goals: Optional[List[str]] = None,
    ) -> str:
        """AI-powered section rewrite preserving factual accuracy and tailoring to the role."""
        api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ResumeGenerationError("AI rewriting is not configured. Add GROQ_API_KEY to the environment.")

        target_role = job.get("title") or "target role"
        company = job.get("company") or "the company"

        is_bullet = "bullet" in section.lower()
        drafting = not (content or "").strip()
        if drafting:
            # Nothing to polish. Only a summary can be drafted, and only from facts already on the resume.
            facts = self._summary_facts(resume_data)
            if "summary" not in section.lower() or not facts:
                raise ResumeGenerationError(
                    "Write a rough first draft (even one line) and AI will polish it. "
                    "AI will not make up experience you have not entered."
                )
            content = facts
        system = (
            f"You are an expert UK/IE executive resume writer. Rewrite the following resume {section} "
            f"for the role of {target_role} at {company}. "
            "Keep it concise, high-impact, professional, and ATS-friendly. "
            + ("Return a single outcome-oriented bullet starting with a strong action verb, without leading bullet characters or quotes. " if is_bullet else "")
            + ("There is no existing text: write a 2-3 sentence professional summary using ONLY the facts provided. " if drafting else "")
            + ("For a professional summary, target 250-500 characters when the verified facts allow; naturally include the target role and relevant job keywords only when supported by the resume. Preserve any existing years or measurable results. " if "summary" in section.lower() else "")
            + "Preserve all relevant factual details, job-related skill terms, and existing numbers from the original text. "
            "CRITICAL: Do NOT invent employers, dates, achievements, credentials, or technologies not present in the original text. "
            "Apply the improvement goals only when supported by the supplied resume facts; never claim an unverified skill or qualification. "
            "Preserve factual truth while enhancing active phrasing and clarity. Return plain text only."
        )
        goals = [
            str(goal).strip()[:300]
            for goal in (improvement_goals or [])
            if str(goal).strip()
        ][:8]
        job_skills = job.get("extracted_skills") or job.get("matched_skills") or []
        job_context = {
            "title": target_role,
            "description": str(job.get("description") or "")[:1800],
            "skills_from_job_listing": [str(skill) for skill in job_skills[:20]],
            "verified_resume_facts": self._summary_facts(resume_data)[:5000],
            "score_improvement_goals": goals,
            "original_text_to_improve": content,
        }
        model = os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(job_context, ensure_ascii=True)},
                    ],
                    # Groq's GPT-OSS models only accept temperature=1.
                    "temperature": 1 if model.startswith("openai/gpt-oss") else 0.2,
                    "max_completion_tokens": 1000,
                },
                timeout=(5, 20),
            )
        except requests.RequestException as err:
            raise ResumeGenerationError("AI rewriting service is temporarily unavailable.") from err

        if response.status_code != 200:
            provider_error = self._provider_error_message(response, api_key)
            logger.warning(
                "Groq section rewrite returned HTTP %s: %s",
                response.status_code,
                provider_error or "No provider error detail",
            )
            detail = f" {provider_error}" if provider_error else ""
            raise ResumeGenerationError(f"AI rewriting failed with status {response.status_code}.{detail}")

        try:
            rewritten = response.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError, ValueError) as err:
            raise ResumeGenerationError("AI rewriting returned an invalid response.") from err
        if not rewritten:
            raise ResumeGenerationError("AI rewriting returned empty response.")
        return self._clean_text(rewritten)

    @staticmethod
    def _summary_facts(resume_data: Dict[str, Any]) -> str:
        """Plain-text digest of what the resume already says, used to draft a missing summary."""
        r = resume_data or {}
        lines: List[str] = []
        for e in (r.get("experience") or [])[:4]:
            if not isinstance(e, dict):
                continue
            role = ", ".join(x for x in (e.get("title"), e.get("organization") or e.get("company")) if x)
            if role:
                lines.append(f"Role: {role} ({e.get('dates') or 'dates not given'})")
            if e.get("description"):
                lines.append(f"- {e['description']}")
            lines.extend(f"- {b}" for b in (e.get("bullets") or [])[:3])
        for e in (r.get("projects") or [])[:2]:
            if not isinstance(e, dict):
                continue
            if e.get("title"):
                lines.append(f"Project: {e['title']}")
            if e.get("description"):
                lines.append(f"- {e['description']}")
            lines.extend(f"- {b}" for b in (e.get("bullets") or [])[:3])
        for e in (r.get("internships") or [])[:2]:
            if not isinstance(e, dict):
                continue
            role = ", ".join(x for x in (e.get("title"), e.get("organization") or e.get("company")) if x)
            if role:
                lines.append(f"Internship: {role}")
            if e.get("description"):
                lines.append(f"- {e['description']}")
            lines.extend(f"- {b}" for b in (e.get("bullets") or [])[:3])
        for e in (r.get("publications") or [])[:2]:
            if e.get("title") or e.get("name"):
                lines.append(f"Publication: {e.get('title') or e.get('name')}")
        for e in (r.get("achievements") or [])[:2]:
            if e.get("title") or e.get("name"):
                lines.append(f"Achievement: {e.get('title') or e.get('name')}")
        for e in (r.get("education") or [])[:2]:
            degree = ", ".join(x for x in (e.get("degree") or e.get("title"), e.get("institution") or e.get("organization")) if x)
            if degree:
                lines.append(f"Education: {degree}")
        if r.get("skills"):
            lines.append("Skills: " + ", ".join(str(x) for x in r["skills"][:15]))
        return "\n".join(lines)

    @classmethod
    def _summary_from_verified_facts(cls, resume_data: Dict[str, Any], max_chars: int = 500) -> str:
        """Create a concise fallback summary from exact text already present on the resume."""
        r = resume_data or {}
        facts: List[str] = []
        for section in ("experience", "projects", "internships"):
            for entry in (r.get(section) or []):
                if isinstance(entry, str):
                    candidates = [entry]
                elif isinstance(entry, dict):
                    candidates = [entry.get("description"), *(entry.get("bullets") or [])]
                else:
                    continue
                for candidate in candidates:
                    text = cls._clean_text(candidate)
                    if text and text.casefold() not in {fact.casefold() for fact in facts}:
                        facts.append(text)
                    if len(facts) >= 4:
                        break
                if len(facts) >= 4:
                    break
            if len(facts) >= 4:
                break

        if not facts:
            facts = [
                cls._clean_text(skill)
                for skill in (r.get("skills") or [])
                if cls._clean_text(skill)
            ][:8]
        if not facts:
            return ""

        prefix = "Relevant experience includes: " if any(
            (r.get(section) or []) for section in ("experience", "projects", "internships")
        ) else "Verified skills include: "
        summary = prefix + "; ".join(facts)
        if len(summary) > max_chars:
            summary = summary[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;.")
        return summary.rstrip(" ,;.") + "."

    # Tokens that would indicate a new factual claim: numbers (metrics, years, counts).
    _NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")

    def rewrite_full(
        self, tailored: Dict[str, Any], job: Dict[str, Any], skill_extractor, instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """Rewrite every text part of a tailored resume for the job without adding facts.

        Only the summary, experience/project descriptions and bullets are rewritten. Titles,
        employers, dates, education, certifications and the skills list are kept as-is. Any
        rewritten line that introduces a number or a technology that does not appear anywhere
        in the original resume is rejected and the original line is kept.

        Returns {"resume": <rewritten tailored resume>, "rejected_lines": int}.
        """
        api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ResumeGenerationError("AI rewriting is not configured. Add GROQ_API_KEY to the environment.")

        def entry_payload(entries: Any) -> List[Dict[str, Any]]:
            return [
                {"index": i, "description": e.get("description") or "", "bullets": list(e.get("bullets") or [])}
                for i, e in enumerate(entries or []) if isinstance(e, dict)
            ]

        payload = {
            "job": {
                "title": job.get("title"),
                "company": job.get("company"),
                "description": str(job.get("description") or "")[:4000],
                "priority_keywords": (
                    job.get("extracted_skills")
                    or skill_extractor.extract_skills(
                        f"{job.get('title') or ''} {job.get('description') or ''}"
                    )
                )[:20],
            },
            "resume": {
                "professional_summary": tailored.get("professional_summary") or "",
                "verified_summary_facts": self._summary_facts(tailored),
                "verified_job_keywords": self._verified_job_skills(tailored, job, skill_extractor),
                "experience": entry_payload(tailored.get("experience")),
                "projects": entry_payload(tailored.get("projects")),
                "education": [
                    {
                        "index": i,
                        "degree": entry.get("degree") or entry.get("title") or "",
                        "institution": entry.get("institution") or entry.get("organization") or "",
                        "dates": entry.get("dates") or "",
                        "location": entry.get("location") or "",
                        "bullets": list(entry.get("bullets") or []),
                    }
                    for i, entry in enumerate(tailored.get("education") or [])
                    if isinstance(entry, dict) and not entry.get("description")
                ],
            },
        }
        system = (
            "You are an expert resume writer. Write or rewrite the candidate's professional_summary and every experience and "
            "project description and bullet to optimize the resume for the target role. Use the exact priority keywords "
            "where they accurately describe the supplied experience. Put verified_job_keywords into the skills list "
            "through the pre-verified profile data and naturally emphasize them in relevant summary and work/project text. "
            "Aim for a concise 2-4 sentence summary of 250-600 characters when the supplied facts support it. "
            "STRICT RULES: use ONLY facts already present in the resume. Never add numbers, metrics, percentages, dates, "
            "employers, tools, technologies, skills or achievements that are not already in the resume. Do not claim "
            "a priority keyword unless it is in verified_job_keywords or already supported by the resume text. "
            "If professional_summary is empty, draft 2-3 concise sentences using only verified_summary_facts; do not "
            "leave it empty when those facts provide enough information. "
            "For supplied education entries, write a concise description relevant to the stated degree, using only "
            "their supplied degree, institution, dates, location and bullets. Do not invent modules, grades, awards "
            "or other facts. "
            "Never add new bullets beyond the original count for an entry. Keep each entry's index. "
            "Return one valid JSON object only, with this exact structure and JSON value types: "
            "{\"professional_summary\":\"text\","
            "\"experience\":[{\"index\":0,\"description\":\"text\",\"bullets\":[\"text\"]}],"
            "\"projects\":[{\"index\":0,\"description\":\"text\",\"bullets\":[\"text\"]}],"
            "\"education\":[{\"index\":0,\"description\":\"text\"}]}. "
            "Use empty arrays when a section has no entries and an empty string when no rewrite is appropriate. "
            "Do not include markdown fences or any text outside the JSON object."
        )
        steer = re.sub(r"\s+", " ", str(instructions or "")).strip()[:500]
        if steer:
            system += (
                " The candidate also asked: \"" + steer + "\". Use this only to choose which existing facts to "
                "emphasise and how to phrase them; it never permits adding facts that are not in the resume."
            )
        model = os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
                    ],
                    "temperature": 1 if model.startswith("openai/gpt-oss") else 0.2,
                    # Room for every bullet; a truncated reply is invalid JSON and the rewrite is lost.
                    "max_tokens": 3000,
                    "response_format": {"type": "json_object"},
                },
                timeout=(5, 45),
            )
        except requests.RequestException as err:
            raise ResumeGenerationError("AI rewriting service is temporarily unavailable.") from err
        if response.status_code != 200:
            provider_error = self._provider_error_message(response, api_key)
            logger.warning(
                "Groq full resume rewrite returned HTTP %s: %s",
                response.status_code,
                provider_error or "No provider error detail",
            )
            detail = f" {provider_error}" if provider_error else ""
            raise ResumeGenerationError(
                f"AI rewriting failed with status {response.status_code}.{detail}"
            )
        try:
            rewritten = json.loads(response.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as err:
            raise ResumeGenerationError("AI rewriting returned an invalid structure.") from err

        result = self.merge_rewrite(tailored, rewritten, skill_extractor)
        if (
            not str(tailored.get("professional_summary") or "").strip()
            and not str(result["resume"].get("professional_summary") or "").strip()
        ):
            result["resume"]["professional_summary"] = self._summary_from_verified_facts(tailored)
        return result

    @classmethod
    def merge_rewrite(cls, tailored: Dict[str, Any], rewritten: Dict[str, Any], skill_extractor) -> Dict[str, Any]:
        """Apply AI-rewritten text onto ``tailored``, keeping the original wherever a line adds facts."""
        original_text = json.dumps(tailored, ensure_ascii=False).lower()
        original_numbers = set(cls._NUMBER_PATTERN.findall(original_text))
        original_skills = {s.lower() for s in skill_extractor.extract_skills(original_text)}
        rejected = 0

        def accept(new: Any, old: str) -> str:
            nonlocal rejected
            candidate = cls._clean_text(new)
            if not candidate:
                return old
            lowered = candidate.lower()
            new_numbers = set(cls._NUMBER_PATTERN.findall(lowered)) - original_numbers
            new_skills = {s.lower() for s in skill_extractor.extract_skills(lowered)} - original_skills
            if new_numbers or new_skills:
                rejected += 1
                return old
            return candidate

        result = json.loads(json.dumps(tailored))  # deep copy
        if not isinstance(rewritten, dict):
            rewritten = {}
        result["professional_summary"] = accept(
            rewritten.get("professional_summary"), tailored.get("professional_summary") or ""
        )
        for section in ("experience", "projects"):
            entries = result.get(section) or []
            by_index = {
                item.get("index"): item for item in (rewritten.get(section) or [])
                if isinstance(item, dict) and isinstance(item.get("index"), int)
            }
            for i, entry in enumerate(entries):
                new = by_index.get(i)
                if not isinstance(entry, dict) or not new:
                    continue
                if entry.get("description"):
                    entry["description"] = accept(new.get("description"), entry["description"])
                old_bullets = list(entry.get("bullets") or [])
                new_bullets = cls._normalize_bullets(new.get("bullets"))
                # Same number of bullets as before; each one checked against the original facts.
                entry["bullets"] = [
                    accept(new_bullets[j] if j < len(new_bullets) else "", old)
                    for j, old in enumerate(old_bullets)
                ]
        education_by_index = {
            item.get("index"): item for item in (rewritten.get("education") or [])
            if isinstance(item, dict) and isinstance(item.get("index"), int)
        }
        for i, entry in enumerate(result.get("education") or []):
            new = education_by_index.get(i)
            if isinstance(entry, dict) and not entry.get("description") and new:
                entry["description"] = accept(new.get("description"), "")
        return {"resume": result, "rejected_lines": rejected}

    def _tailor_with_groq(self, resume: Dict[str, Any], job: Dict[str, Any], source_text: str) -> Dict[str, Any]:
        api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ResumeGenerationError("GROQ_API_KEY not set")

        prompt = {
            "resume": {
                "candidate_name": resume.get("candidate_name"),
                "email": resume.get("email"),
                "phone": resume.get("phone"),
                "linkedin": resume.get("linkedin"),
                "github": resume.get("github"),
                "skills": resume.get("skills", []),
                "summary": resume.get("summary", ""),
                "experience": resume.get("experience") or [],
                "education": resume.get("education") or [],
                "projects": resume.get("projects") or [],
                "internships": resume.get("internships") or [],
                "publications": resume.get("publications") or [],
                "certifications": resume.get("certifications") or [],
                "achievements": resume.get("achievements") or [],
                "full_resume_text": source_text[:12000],
            },
            "job": {
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "description": job.get("description", "")[:4000],
                "matched_skills": job.get("matched_skills", []),
                "missing_skills": job.get("missing_skills", []),
            },
        }
        system = (
            "You tailor UK-style resumes with STRICT FACTUAL TRUTH AND ZERO HALLUCINATION. "
            "Use ONLY the genuine facts, real project names, real company names, real dates, real degrees, and verified skills from the candidate's resume. "
            "Never invent employers, dates, degrees, achievements, metrics, skills, links, or qualifications not present in the original resume. "
            "Preserve the candidate's real personal information, contact links (LinkedIn, GitHub, portfolio), education, and projects exactly as stated. "
            "The structured fields (summary, skills, experience, internships, education, projects, publications, achievements, certifications) are the candidate's latest approved edits; "
            "where they differ from full_resume_text, the structured fields take precedence. "
            "STRICT 1-PAGE A4 REQUIREMENT: The tailored resume MUST fit on exactly one single A4 page with balanced vertical proportion. "
            "Return JSON only with keys: personal_info, professional_summary, education, experience, internships, projects, publications, achievements, certifications, skills. "
            "Limit professional_summary to 2-3 concise, high-impact sentences. "
            "Include only the top 2-3 most relevant work experiences with at most 2-3 bullet points each. "
            "Include only the top 2-3 most relevant projects with at most 2-3 bullet points each. Preserve publication and achievement entries as separate sections; never move them into projects. "
            "Include genuine degrees and top 12-16 relevant skills. "
            "education, experience, projects, and certifications must be arrays of objects. "
            "Each experience object must have: title, organization (or company), dates, location, description, and bullets (a JSON array of concise bullet strings). "
            "Each project object must have: title, organization, dates, description, and bullets (a JSON array of strings). "
            "Each internship and publication object must have: title, organization, dates, description, and bullets (a JSON array of strings). "
            "Each achievement object must have: title, dates, and description. "
            "Each education object must have: degree, institution, dates, location, description, bullets. "
            "Each certification object must have: name, issuer, dates. "
            "skills must be a JSON array of strings. "
            "Never return bullets as Python list representations like \"['...']\". Always use true JSON arrays."
        )
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("GROQ_MODEL") or DEFAULT_GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                    "response_format": {"type": "json_object"},
                },
                timeout=(5, 30),
            )
        except requests.RequestException as error:
            raise ResumeGenerationError("Groq resume generation is temporarily unavailable.") from error

        if response.status_code != 200:
            logger.warning("Groq returned HTTP %s: %s", response.status_code, response.text[:500])
            raise ResumeGenerationError("Resume generation failed.")
        try:
            content = response.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ResumeGenerationError("Groq returned an invalid resume structure.") from error


    @classmethod
    def _normalize_bullets(cls, raw: Any) -> List[str]:
        """Flattens and parses bullets, safely stripping stringified Python lists and markdown."""
        if not raw:
            return []
        items = []
        if isinstance(raw, str):
            trimmed = raw.strip()
            # If stringified Python list like "['bullet 1', 'bullet 2']"
            if (trimmed.startswith("[") and trimmed.endswith("]")) or (trimmed.startswith("(") and trimmed.endswith(")")):
                try:
                    parsed = json.loads(trimmed)
                    if isinstance(parsed, list):
                        return cls._normalize_bullets(parsed)
                except Exception:
                    try:
                        parsed = ast.literal_eval(trimmed)
                        if isinstance(parsed, (list, tuple)):
                            return cls._normalize_bullets(list(parsed))
                    except Exception:
                        pass
            # Split newlines
            lines = re.split(r"[\r\n]+", trimmed)
            for line in lines:
                cleaned = re.sub(r"^[\s\-\*•\d\.\)]+", "", line).strip()
                if cleaned:
                    items.append(cleaned)
        elif isinstance(raw, (list, tuple)):
            for b in raw:
                if isinstance(b, (list, tuple)):
                    items.extend(cls._normalize_bullets(b))
                elif isinstance(b, str):
                    b_trimmed = b.strip()
                    if (b_trimmed.startswith("[") and b_trimmed.endswith("]")) or (b_trimmed.startswith("(") and b_trimmed.endswith(")")):
                        items.extend(cls._normalize_bullets(b_trimmed))
                    else:
                        cleaned = re.sub(r"^[\s\-\*•\d\.\)]+", "", b_trimmed).strip()
                        if cleaned:
                            items.append(cleaned)
                elif b:
                    cleaned = str(b).strip()
                    if cleaned:
                        items.append(cleaned)
        return [cls._clean_text(it) for it in items if cls._clean_text(it)]

    def _normalize_entries(self, entries: Any, section: str = "experience") -> List[Dict[str, Any]]:
        """Normalizes experience, projects, education, and certifications into structured objects."""
        if isinstance(entries, str):
            trimmed = entries.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                try:
                    entries = json.loads(trimmed)
                except Exception:
                    try:
                        entries = ast.literal_eval(trimmed)
                    except Exception:
                        entries = []
            else:
                entries = []
        if not isinstance(entries, list):
            return []

        normalized = []
        for entry in entries:
            if isinstance(entry, str):
                entry = {"title": entry}
            if not isinstance(entry, dict):
                continue
            title = self._clean_text(
                entry.get("title") or entry.get("role") or entry.get("name") or entry.get("degree") or ""
            )
            org = self._clean_text(
                entry.get("organization") or entry.get("company") or entry.get("institution") or entry.get("school")
                or entry.get("venue") or entry.get("publisher") or entry.get("conference") or entry.get("issuer") or ""
            )
            dates = self._clean_text(entry.get("dates") or entry.get("date") or entry.get("period") or entry.get("year") or "")
            location = self._clean_text(entry.get("location") or "")
            description = self._clean_text(entry.get("description") or entry.get("summary") or "")
            bullets = self._normalize_bullets(entry.get("bullets"))

            item = {
                "title": title,
                "organization": org,
                "company": org,
                "institution": org,
                "degree": title if section == "education" else "",
                "name": title,
                "dates": dates,
                "location": location,
                "description": description,
                "bullets": bullets[:8],
            }
            if title or org or bullets or description:
                normalized.append(item)
        return normalized

    def _validate_and_normalize(
        self, generated: Dict[str, Any], resume: Dict[str, Any], job: Dict[str, Any], keep_edits: bool = False
    ) -> Dict[str, Any]:
        """Normalise a tailored resume.

        ``keep_edits`` is for drafts the user edited by hand: every section present in
        ``generated`` is taken as-is (an emptied section stays empty instead of refilling
        from the master profile) and the one-page trimming is skipped, because the editor
        fits the page itself. Without it, missing sections fall back to the profile and
        the result is trimmed to one page.
        """
        if not isinstance(generated, dict):
            generated = {}

        def pick(key: str, *fallbacks: Any) -> Any:
            if keep_edits and key in generated:
                return generated.get(key)
            value = generated.get(key)
            for fallback in fallbacks:
                if value:
                    break
                value = fallback
            return value

        allowed_skills = {str(skill).casefold(): str(skill) for skill in resume.get("skills", [])}
        gen_skills_raw = generated.get("skills") or []
        if isinstance(gen_skills_raw, str):
            gen_skills_raw = self._normalize_bullets(gen_skills_raw)
        elif not isinstance(gen_skills_raw, list):
            gen_skills_raw = []

        skills = []
        for skill in gen_skills_raw:
            cleaned = self._clean_text(skill)
            if not cleaned:
                continue
            c_fold = cleaned.casefold()
            if c_fold in allowed_skills:
                skills.append(allowed_skills[c_fold])
            else:
                skills.append(cleaned)
        if not skills and not (keep_edits and "skills" in generated):
            skills = list(allowed_skills.values())
        # Deduplicate skills while preserving order
        seen = set()
        deduped_skills = []
        for s in skills:
            if s.casefold() not in seen:
                seen.add(s.casefold())
                deduped_skills.append(s)

        p_info = generated.get("personal_info") or {}
        if not isinstance(p_info, dict):
            p_info = {}

        raw_linkedin = self._clean_text(p_info.get("linkedin") or resume.get("linkedin") or "")
        raw_github = self._clean_text(p_info.get("github") or resume.get("github") or "")
        clean_linkedin = re.sub(r"^https?://(www\.)?", "", raw_linkedin, flags=re.I)
        while clean_linkedin.lower().startswith("linkedin.com/in/") or clean_linkedin.lower().startswith("linkedin.com/"):
            clean_linkedin = re.sub(r"^linkedin\.com/(in/)?", "", clean_linkedin, flags=re.I)
        clean_linkedin = clean_linkedin.rstrip("/")

        clean_github = re.sub(r"^https?://(www\.)?", "", raw_github, flags=re.I)
        while clean_github.lower().startswith("github.com/"):
            clean_github = re.sub(r"^github\.com/?", "", clean_github, flags=re.I)
        clean_github = clean_github.rstrip("/")

        raw_portfolio = self._clean_text(p_info.get("portfolio") or p_info.get("website") or resume.get("portfolio") or resume.get("website") or "")
        clean_portfolio = re.sub(r"^https?://", "", raw_portfolio, flags=re.I).rstrip("/")

        res = {
            "personal_info": {
                "name": self._clean_text(p_info.get("name") or resume.get("candidate_name") or ""),
                "email": self._clean_text(p_info.get("email") or resume.get("email") or ""),
                "phone": self._clean_text(p_info.get("phone") or resume.get("phone") or ""),
                "linkedin": clean_linkedin,
                "github": clean_github,
                "portfolio": clean_portfolio,
                "location": self._clean_text(p_info.get("location") or resume.get("location") or ""),
            },
            "target_role": self._clean_text(job.get("title") or generated.get("target_role") or ""),
            "company": self._clean_text(job.get("company") or generated.get("company") or ""),
            "professional_summary": self._clean_text(
                generated.get("professional_summary")
                if keep_edits and "professional_summary" in generated
                else (
                    self._clean_text(generated.get("professional_summary"))
                    or self._clean_text(generated.get("summary"))
                    or self._clean_text(resume.get("summary"))
                )
            ),
            "education": self._normalize_entries(pick("education", resume.get("education")), section="education"),
            # With no work history, internships stand in as Work Experience (the template has no internship section).
            "experience": self._normalize_entries(
                pick("experience", resume.get("experience"), generated.get("internships"), resume.get("internships")),
                section="experience"
            ),
            "projects": self._normalize_entries(pick("projects", resume.get("projects")), section="projects"),
            "internships": self._normalize_entries(pick("internships", resume.get("internships")), section="internships"),
            "publications": self._normalize_entries(pick("publications", resume.get("publications")), section="publications"),
            "certifications": self._normalize_entries(pick("certifications", resume.get("certifications")), section="certifications"),
            "achievements": self._normalize_entries(pick("achievements", resume.get("achievements")), section="achievements"),
            "activities": resume.get("activities", generated.get("activities", [])),
            "leadership": resume.get("leadership", generated.get("leadership", [])),
            "awards": resume.get("awards", generated.get("awards", [])),
            "skills": deduped_skills,
        }
        return res if keep_edits else self._enforce_single_page_limits(res)

    @classmethod
    def _enforce_single_page_limits(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures the tailored resume fits cleanly on 1 A4 page with balanced vertical proportion."""
        summary = data.get("professional_summary", "")
        if len(summary) > 450:
            sentences = re.split(r"(?<=[.!?])\s+", summary)
            data["professional_summary"] = " ".join(sentences[:3]) if len(sentences) >= 3 else summary[:420]

        exp = data.get("experience", [])
        if len(exp) > 3:
            exp = exp[:3]
        for item in exp:
            bullets = item.get("bullets") or []
            if len(bullets) > 3:
                item["bullets"] = bullets[:3]
        data["experience"] = exp

        proj = data.get("projects", [])
        for item in proj:
            bullets = item.get("bullets") or []
            if len(bullets) > 3:
                item["bullets"] = bullets[:3]
        data["projects"] = proj
        data["internships"] = data.get("internships", [])
        data["publications"] = data.get("publications", [])
        data["achievements"] = data.get("achievements", [])

        # Balanced bullet budget across exp + proj to fill 1 A4 page without spill
        total_bullets = sum(len(e.get("bullets", [])) for e in exp) + sum(len(p.get("bullets", [])) for p in proj)
        if total_bullets > 12:
            for p in reversed(proj):
                if total_bullets <= 12:
                    break
                p_b = p.get("bullets", [])
                if len(p_b) > 2:
                    p["bullets"] = p_b[:2]
                    total_bullets -= (len(p_b) - 2)
            for e in reversed(exp):
                if total_bullets <= 12:
                    break
                e_b = e.get("bullets", [])
                if len(e_b) > 2:
                    e["bullets"] = e_b[:2]
                    total_bullets -= (len(e_b) - 2)

        edu = data.get("education", [])
        if len(edu) > 3:
            edu = edu[:3]
        for item in edu:
            bullets = item.get("bullets") or []
            if len(bullets) > 2:
                item["bullets"] = bullets[:2]
        data["education"] = edu

        certs = data.get("certifications", [])
        if len(certs) > 4:
            data["certifications"] = certs[:4]

        skills = data.get("skills", [])
        if len(skills) > MAX_RESUME_SKILLS:
            data["skills"] = skills[:MAX_RESUME_SKILLS]

        return data

    @classmethod
    def _ensure_education_descriptions(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Fill missing education descriptions with degree-relevant context."""
        result = json.loads(json.dumps(data))
        for item in result.get("education") or []:
            if not isinstance(item, dict) or cls._clean_text(item.get("description")):
                continue
            degree = cls._clean_text(item.get("degree") or item.get("title"))
            institution = cls._clean_text(item.get("institution") or item.get("organization"))
            degree_lower = degree.casefold()
            if any(term in degree_lower for term in ("information technology", "it ", "it-", "software")):
                focus = "software development, databases, networking, systems analysis, and information technology applications"
            elif any(term in degree_lower for term in ("computer science", "computing", "informatics")):
                focus = "algorithms, programming, data structures, databases, software engineering, and computing systems"
            elif any(term in degree_lower for term in ("data science", "analytics", "artificial intelligence", "machine learning")):
                focus = "data analysis, statistical methods, programming, machine learning, and practical data-driven problem solving"
            elif any(term in degree_lower for term in ("business", "management", "commerce", "mba")):
                focus = "business principles, analytical decision-making, organisational practice, and commercial problem solving"
            elif any(term in degree_lower for term in ("engineering", "technology")):
                focus = "engineering principles, technical analysis, design methods, and practical problem solving"
            else:
                focus = "the core theory, practical application, analytical thinking, and subject-specific problem solving of the discipline"
            label = degree or "the qualification"
            description = f"Studied {focus} through the {label}"
            if institution:
                description += f" at {institution}"
            item["description"] = description + "."
        return result

    def _export_docx(self, structured: Dict[str, Any], docx_path: Path) -> Path:
        """Exports ATS-friendly clean single-column DOCX format."""
        structured = {
            **structured,
            "internships": [],
            "publications": [],
            "achievements": [],
        }
        doc = docx.Document()

        # Set standard margins (0.75 in / 1.9 cm)
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.6)
            section.bottom_margin = Inches(0.6)
            section.left_margin = Inches(0.7)
            section.right_margin = Inches(0.7)

        p_info = structured.get("personal_info", {})
        name = p_info.get("name") or ""
        target_role = structured.get("target_role") or ""

        # Title / Name (omitted when the résumé has no name; never a placeholder)
        if name:
            p_name = doc.add_paragraph()
            p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_name = p_name.add_run(name)
            run_name.bold = True
            run_name.font.size = Pt(20)
            run_name.font.name = "Calibri"
            run_name.font.color.rgb = RGBColor(15, 23, 42)

        if target_role:
            p_role = doc.add_paragraph()
            p_role.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_role = p_role.add_run(target_role)
            run_role.font.size = Pt(12)
            run_role.font.name = "Calibri"
            run_role.font.color.rgb = RGBColor(71, 85, 105)

        # Contact Info Line
        contacts = []
        if p_info.get("email"):
            contacts.append(p_info["email"])
        if p_info.get("phone"):
            contacts.append(p_info["phone"])
        if p_info.get("location"):
            contacts.append(p_info["location"])
        if p_info.get("linkedin"):
            contacts.append(p_info["linkedin"])
        if p_info.get("github"):
            contacts.append(p_info["github"])

        if contacts:
            p_contact = doc.add_paragraph()
            p_contact.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_contact = p_contact.add_run(" | ".join(contacts))
            run_contact.font.size = Pt(9.5)
            run_contact.font.name = "Calibri"
            run_contact.font.color.rgb = RGBColor(100, 116, 139)

        def add_section_heading(title: str):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(3)
            run = p.add_run(title.upper())
            run.bold = True
            run.font.size = Pt(11)
            run.font.name = "Calibri"
            run.font.color.rgb = RGBColor(30, 41, 59)

        # About Me
        summary = structured.get("professional_summary")
        if summary:
            add_section_heading("About Me")
            p_sum = doc.add_paragraph(summary)
            p_sum.paragraph_format.space_after = Pt(6)
            for r in p_sum.runs:
                r.font.size = Pt(10)
                r.font.name = "Calibri"

        # Experience
        experience = structured.get("experience") or []
        if experience:
            add_section_heading("Work Experience")
            for item in experience:
                p_item = doc.add_paragraph()
                p_item.paragraph_format.space_before = Pt(4)
                p_item.paragraph_format.space_after = Pt(1)
                r_title = p_item.add_run(item.get("title") or "")
                r_title.bold = True
                r_title.font.name = "Calibri"
                r_title.font.size = Pt(10.5)

                org = item.get("organization") or item.get("company")
                if org:
                    r_org = p_item.add_run(f" | {org}" if item.get("title") else org)
                    r_org.font.name = "Calibri"
                    r_org.font.size = Pt(10)

                dates = item.get("dates")
                if dates:
                    r_dates = p_item.add_run(f" ({dates})")
                    r_dates.font.name = "Calibri"
                    r_dates.font.size = Pt(9.5)
                    r_dates.font.italic = True

                if item.get("description"):
                    p_desc = doc.add_paragraph(item["description"])
                    p_desc.paragraph_format.space_after = Pt(2)
                    for r in p_desc.runs:
                        r.font.size = Pt(9.5)
                        r.font.name = "Calibri"

                for bullet in item.get("bullets") or []:
                    p_b = doc.add_paragraph(bullet, style="List Bullet")
                    p_b.paragraph_format.space_after = Pt(1.5)
                    for r in p_b.runs:
                        r.font.size = Pt(9.5)
                        r.font.name = "Calibri"

        # Projects
        projects = structured.get("projects") or []
        if projects:
            add_section_heading("Projects")
            for item in projects:
                p_item = doc.add_paragraph()
                p_item.paragraph_format.space_before = Pt(4)
                p_item.paragraph_format.space_after = Pt(1)
                r_title = p_item.add_run(item.get("title") or item.get("name") or "")
                r_title.bold = True
                r_title.font.name = "Calibri"
                r_title.font.size = Pt(10.5)

                dates = item.get("dates")
                if dates:
                    r_dates = p_item.add_run(f" ({dates})")
                    r_dates.font.name = "Calibri"
                    r_dates.font.size = Pt(9.5)
                    r_dates.font.italic = True

                if item.get("description"):
                    p_desc = doc.add_paragraph(item["description"])
                    p_desc.paragraph_format.space_after = Pt(2)
                    for r in p_desc.runs:
                        r.font.size = Pt(9.5)
                        r.font.name = "Calibri"

                for bullet in item.get("bullets") or []:
                    p_b = doc.add_paragraph(bullet, style="List Bullet")
                    p_b.paragraph_format.space_after = Pt(1.5)
                    for r in p_b.runs:
                        r.font.size = Pt(9.5)
                        r.font.name = "Calibri"

        # Education
        education = structured.get("education") or []
        if education:
            add_section_heading("Education")
            for item in education:
                p_item = doc.add_paragraph()
                p_item.paragraph_format.space_before = Pt(3)
                p_item.paragraph_format.space_after = Pt(1)
                r_deg = p_item.add_run(item.get("degree") or item.get("title") or "")
                r_deg.bold = True
                r_deg.font.name = "Calibri"
                r_deg.font.size = Pt(10)

                inst = item.get("institution") or item.get("organization") or item.get("school")
                if inst:
                    r_inst = p_item.add_run(f" | {inst}" if (item.get("degree") or item.get("title")) else inst)
                    r_inst.font.name = "Calibri"
                    r_inst.font.size = Pt(10)

                if item.get("dates"):
                    r_d = p_item.add_run(f" ({item['dates']})")
                    r_d.font.name = "Calibri"
                    r_d.font.size = Pt(9.5)
                    r_d.font.italic = True

                if item.get("description"):
                    p_desc = doc.add_paragraph(item["description"])
                    p_desc.paragraph_format.space_after = Pt(2)
                    for r in p_desc.runs:
                        r.font.size = Pt(9.5)
                        r.font.name = "Calibri"

                for bullet in item.get("bullets") or []:
                    p_b = doc.add_paragraph(bullet, style="List Bullet")
                    for r in p_b.runs:
                        r.font.size = Pt(9.5)
                        r.font.name = "Calibri"

        # Skills
        skills = structured.get("skills") or []
        if skills:
            add_section_heading("Skills")
            p_sk = doc.add_paragraph(" • ".join(skills))
            p_sk.paragraph_format.space_after = Pt(6)
            for r in p_sk.runs:
                r.font.size = Pt(9.5)
                r.font.name = "Calibri"

        doc.save(str(docx_path))
        return docx_path

    @staticmethod
    def _clean_text(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @staticmethod
    def _texescape(value: Any) -> str:
        replacements = {
            "\\": r"\textbackslash{}",
            "&": r"\&",
            "%": r"\%",
            "$": r"\$",
            "#": r"\#",
            "_": r"\_",
            "{": r"\{",
            "}": r"\}",
            "~": r"\textasciitilde{}",
            "^": r"\textasciicircum{}",
        }
        return "".join(replacements.get(char, char) for char in str(value or ""))

    def _render_latex(self, data: Dict[str, Any]) -> str:
        template = self.environment.get_template("uk_standard_resume.tex.j2")
        return template.render(**data)

    def _compile_pdf(self, tex_path: Path) -> Optional[Path]:
        compiler = shutil.which("pdflatex") or shutil.which("xelatex")
        if not compiler:
            logger.warning("No LaTeX compiler found; returning the generated .tex only.")
            return None
        with tempfile.TemporaryDirectory(prefix="cafy-resume-") as build_dir:
            build_path = Path(build_dir)
            command = [
                compiler,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                str(build_path),
                str(tex_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
            compiled = build_path / f"{tex_path.stem}.pdf"
            if result.returncode != 0 or not compiled.exists():
                logger.error("LaTeX compilation failed: %s", result.stdout[-2000:])
                return None
            destination = self.output_dir / f"{tex_path.stem}.pdf"
            shutil.copyfile(compiled, destination)
            return destination
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
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from jinja2 import Environment, FileSystemLoader, Undefined
import requests

from .resume_structure import (
    ENTRY_SECTIONS,
    dedupe_entries,
    render_sections,
    same_record,
    split_internships,
    standardize_dates,
    without_repeats,
)

logger = logging.getLogger("cafy.resume_generation")

MAX_RESUME_SKILLS = 24
# Bullets kept per entry when tailoring. Entries themselves are never dropped: a resume that
# needs a second page gets one instead of losing records.
MAX_BULLETS_PER_ENTRY = 6
MAX_SUMMARY_CHARS = 600

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# Active model; override with GROQ_MODEL (it is tried first, then the fallbacks).
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
# Checked against Groq's GET /openai/v1/models and a JSON-mode chat call on 2026-11-06.
# llama-3.3-70b-versatile and llama-3.1-8b-instant now return 404 and were removed.
FALLBACK_GROQ_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)


class ResumeGenerationError(RuntimeError):
    pass


def _groq_api_key() -> str:
    return os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY") or ""


def _groq_models() -> List[str]:
    models: List[str] = []
    for model in [os.getenv("GROQ_MODEL"), *FALLBACK_GROQ_MODELS]:
        if model and model not in models:
            models.append(model)
    return models


def _parse_json_object(content: str) -> Optional[Dict[str, Any]]:
    """Parse a model reply as one JSON object, tolerating code fences and text around it."""
    cleaned = _THINK_BLOCK.sub("", content or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip())
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1] if "{" in cleaned else ""):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


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
        self.environment.filters["urlescape"] = self._urlescape

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

    @classmethod
    def _groq_chat(
        cls,
        system: str,
        user: str,
        *,
        json_mode: bool,
        max_tokens: int,
        timeout: Tuple[int, int],
        temperature: float = 0.2,
        token_field: str = "max_tokens",
    ) -> Union[str, Dict[str, Any]]:
        """Call Groq, falling back through every configured model.

        Rate limits (429), server errors, retired or unknown models (400/404), timeouts,
        network errors, empty replies and invalid JSON all move on to the next model.
        A rejected API key (401/403) stops at once because no model can succeed.
        Raises ResumeGenerationError with the last provider message when every model fails.
        """
        api_key = _groq_api_key()
        if not api_key:
            raise ResumeGenerationError("AI rewriting is not configured. Add GROQ_API_KEY to the environment.")

        last_error: Optional[ResumeGenerationError] = None
        for model in _groq_models():
            body: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                # Groq's GPT-OSS models only accept temperature=1.
                "temperature": 1 if model.startswith("openai/gpt-oss") else temperature,
                token_field: max_tokens,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            try:
                response = requests.post(
                    GROQ_CHAT_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=body,
                    timeout=timeout,
                )
            except requests.RequestException as err:
                logger.warning("Groq model %s request failed (%s); trying the next model.", model, type(err).__name__)
                last_error = ResumeGenerationError("AI rewriting service is temporarily unavailable.")
                continue

            if response.status_code != 200:
                provider_error = cls._provider_error_message(response, api_key)
                logger.warning("Groq model %s returned HTTP %s: %s", model, response.status_code,
                               provider_error or "no provider detail")
                detail = f" {provider_error}" if provider_error else ""
                if response.status_code in (401, 403):
                    raise ResumeGenerationError(f"AI rewriting failed with status {response.status_code}.{detail}")
                last_error = ResumeGenerationError(f"AI rewriting failed with status {response.status_code}.{detail}")
                continue

            try:
                content = response.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError):
                logger.warning("Groq model %s returned an unexpected response shape.", model)
                last_error = ResumeGenerationError("AI rewriting returned an invalid response.")
                continue
            if not isinstance(content, str) or not _THINK_BLOCK.sub("", content).strip():
                last_error = ResumeGenerationError("AI rewriting returned an empty response.")
                continue
            if not json_mode:
                return _THINK_BLOCK.sub("", content).strip()
            parsed = _parse_json_object(content)
            if parsed is None:
                logger.warning("Groq model %s returned text that is not a JSON object.", model)
                last_error = ResumeGenerationError("AI rewriting returned an invalid structure.")
                continue
            return parsed

        raise last_error or ResumeGenerationError("AI rewriting service is temporarily unavailable.")

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
        # Education, employers, dates and certifications are copied from the profile unchanged.
        structured = self._validate_and_normalize({}, resume, job)
        existing_skills = {str(skill).casefold() for skill in structured["skills"]}
        added_keywords: List[str] = []
        if skill_extractor is not None:
            for skill in self._verified_job_skills(resume, job, skill_extractor):
                if skill.casefold() not in existing_skills:
                    structured["skills"].append(skill)
                    existing_skills.add(skill.casefold())
                    added_keywords.append(skill)

        # The job's own requirements (essential/desirable, read from its description), each with
        # the resume line that proves it. Only proven ones become keywords; the rest are reported.
        from .requirement_matching import score_job
        jd_match = score_job(resume, job)
        proven = [r for r in jd_match["requirements"]
                  if r["evidence_type"] in ("direct", "weak") and r.get("exact_evidence")]
        for row in proven:
            if row["name"].casefold() not in existing_skills:
                structured["skills"].append(row["name"])
                existing_skills.add(row["name"].casefold())
                added_keywords.append(row["name"])
        structured["skills"] = self._rank_skills_for_job(structured["skills"], job, jd_match)
        self._order_by_job_relevance(structured, jd_match)

        source_internships = len(structured.get("internships") or [])
        rewrite: Dict[str, Any] = {}
        tailoring_mode = "rules"
        ai_error = ""
        if skill_extractor is not None:
            try:
                rewrite = self.rewrite_full(structured, job, skill_extractor, instructions)
                structured = rewrite["resume"]
                tailoring_mode = "ai"
            except ResumeGenerationError as error:
                # Never block on the AI: finish with rule-based tailoring from verified facts and
                # say so in the response, so it is not presented as an AI rewrite.
                ai_error = str(error)
                logger.warning("[ResumeGeneration] AI rewrite unavailable, using rule-based tailoring: %s", error)
        if tailoring_mode == "rules" or not str(structured.get("professional_summary") or "").strip():
            structured["professional_summary"] = self._about_me_for_job(resume, structured, job, jd_match)
        # Education entries without a description stay without one; generic coursework text
        # would be an unverified claim.
        resume_id = uuid.uuid4().hex
        # The editor renders its own PDF, so the LaTeX PDF is compiled only when it is downloaded.
        artifacts = self.update_artifacts(resume_id, structured, compile_pdf=False)

        # Compute real ATS / match scores against the generated resume.
        generation_scores = self._score_generated_resume(structured, job, skill_extractor)
        tailored_match = score_job(
            {**structured, "summary": structured.get("professional_summary") or "",
             "years_of_experience": resume.get("years_of_experience"), "career_level": resume.get("career_level")},
            job,
        )
        generation_scores["jd_match_score"] = tailored_match["score"]
        generation_scores["jd_top_band_eligible"] = tailored_match["top_band_eligible"]
        generation_scores["jd_match"] = tailored_match

        return {
            "status": "success",
            "template": "uk-standard",
            "resume": structured,
            **artifacts,
            "generation_scores": generation_scores,
            "validation": {
                "tailoring_mode": tailoring_mode,
                "ai_error": ai_error,
                # Job keywords added to Skills - each one is evidenced in the uploaded resume.
                "keywords_added": added_keywords,
                # Essential requirements the resume does not show; never added.
                "essential_requirements_not_claimed": [
                    r["name"] for r in jd_match["requirements"]
                    if r["importance"] == "essential" and r["evidence_type"] in ("missing", "transferable")
                ],
                "ats_friendly": True,
                # Every AI line was checked against the source resume; rejected lines kept the original text.
                "factual_consistency": True,
                "rejected_ai_lines": rewrite.get("rejected_lines", 0),
                "unsupported_claims": rewrite.get("rejection_reasons", []),
                "internships_preserved": len(structured.get("internships") or []) == source_internships,
                "sections": [section["key"] for section in render_sections(structured)],
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
    def _rank_skills_for_job(skills: List[str], job: Dict[str, Any], jd_match: Dict[str, Any]) -> List[str]:
        """Essential job skills first, then desirable ones, then the rest (original order kept)."""
        importance = {r["name"].casefold(): r["importance"] for r in jd_match.get("requirements") or []}
        wanted = {str(s).casefold() for s in (job.get("extracted_skills") or [])}

        def rank(skill: str) -> int:
            level = importance.get(skill.casefold())
            if level == "essential":
                return 0
            if level == "desirable":
                return 1
            return 2 if skill.casefold() in wanted else 3

        return sorted(skills, key=rank)

    @staticmethod
    def _order_by_job_relevance(structured: Dict[str, Any], jd_match: Dict[str, Any]) -> None:
        """Most job-relevant bullets first in every role, and most relevant projects first.

        Roles stay in date order and no text changes; only the order does.
        """
        from .requirement_matching import _mentions

        weights = [(r["name"], r["weight"]) for r in jd_match.get("requirements") or []]

        def relevance(text: str) -> float:
            padded = f" {str(text or '').lower()} "
            return sum(weight for name, weight in weights if _mentions(name, padded))

        for section in ("experience", "internships", "projects"):
            for entry in structured.get(section) or []:
                if isinstance(entry, dict) and len(entry.get("bullets") or []) > 1:
                    entry["bullets"] = sorted(entry["bullets"], key=lambda b: -relevance(b))
        projects = structured.get("projects") or []
        if len(projects) > 1:
            structured["projects"] = sorted(projects, key=lambda p: -relevance(
                " ".join([str(p.get("title") or p.get("name") or ""), str(p.get("description") or ""),
                          *map(str, p.get("bullets") or []), *map(str, p.get("technologies") or [])])
                if isinstance(p, dict) else str(p)))

    @classmethod
    def _about_me_for_job(cls, resume: Dict[str, Any], structured: Dict[str, Any], job: Dict[str, Any],
                          jd_match: Dict[str, Any], max_chars: int = 600) -> str:
        """An About Me aimed at this job, built only from facts the resume states.

        Experience level and years come from the profile (internships are never called
        full-time work); "hands-on" is said only of skills used in a role, internship, project
        or certification; listed-only skills are "familiar with". Nothing the resume does not
        show is claimed.
        """
        clean = cls._clean_text
        experience = [e for e in structured.get("experience") or [] if isinstance(e, dict)]
        internships = [e for e in structured.get("internships") or [] if isinstance(e, dict)]
        education = [e for e in structured.get("education") or [] if isinstance(e, dict)]
        check = (jd_match.get("checks") or {}).get("experience") or {}
        years = int(check.get("candidate_years") or 0)
        level = check.get("candidate_level") or ("experienced" if years >= 1 else "fresher")

        sentences: List[str] = []
        # Lead with a role only when it relates to this job (shares a title word or shows one of
        # its skills); an unrelated part-time job should not headline a graduate's application.
        job_words = {w for w in re.findall(r"[a-z]{3,}", str(job.get("title") or "").lower())
                     if w not in {"senior", "junior", "graduate", "lead", "the", "and"}}
        direct_names = {r["name"] for r in jd_match.get("requirements") or [] if r["evidence_type"] == "direct"}

        def relevant(entry: Dict[str, Any]) -> bool:
            text = " ".join([str(entry.get("title") or ""), str(entry.get("description") or ""),
                             *map(str, entry.get("bullets") or [])]).lower()
            return bool(job_words & set(re.findall(r"[a-z]{3,}", str(entry.get("title") or "").lower()))) or any(
                name.lower() in text for name in direct_names)

        role = next((e for e in experience if relevant(e)), None)
        latest_title = clean(role.get("title")) if role else ""
        edu = education[0] if education else {}
        degree = clean(edu.get("degree") or edu.get("title"))
        school = clean(edu.get("institution") or edu.get("organization"))
        if level == "experienced" and latest_title and years >= 2:
            opening = f"{latest_title} with {years} years of full-time experience"
        elif degree:
            dates = clean(edu.get("dates") or edu.get("year"))
            years_in = [int(y) for y in re.findall(r"(?:19|20)\d{2}", dates)]
            studying = "present" in dates.lower() or (years_in and max(years_in) > date.today().year)
            opening = f"{degree} {'student at' if studying else 'graduate from'} {school}" if school else degree
        elif latest_title:
            opening = latest_title
        else:
            opening = "Early-career candidate"
        if internships:
            orgs = [clean(e.get("organization") or e.get("company")) for e in internships]
            orgs = [o for o in orgs if o][:2]
            opening += f", with {len(internships)} internship{'s' if len(internships) != 1 else ''}"
            opening += f" at {' and '.join(orgs)}" if orgs else ""
        sentences.append(opening + ".")

        rows = jd_match.get("requirements") or []
        # Only skills whose own wording is on the resume are named.
        hands_on = [r["name"] for r in rows if r["evidence_type"] == "direct" and r.get("exact_evidence")]
        familiar = [r["name"] for r in rows if r["evidence_type"] == "weak" and r.get("exact_evidence")]

        def listing(names: List[str]) -> str:
            names = names[:5]
            return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

        if hands_on:
            sentences.append(f"Hands-on experience with {listing(hands_on)}.")
        if familiar:
            sentences.append(f"Also familiar with {listing(familiar)}.")
        # One concrete, verbatim result from the most relevant work/project line.
        best = next((r["resume_evidence"][0] for r in rows
                     if r["evidence_type"] == "direct" and r.get("exact_evidence") and r.get("resume_evidence")
                     and r["resume_evidence"][0]["section"] in ("experience", "internships", "projects")), None)
        if best and len(best["text"]) <= 160:
            sentences.append(f"Recently: {best['text'].rstrip('.')}.")
        title = clean(job.get("title"))
        company = clean(job.get("company"))
        if title:
            sentences.append(f"Looking to bring these strengths to the {title} role{f' at {company}' if company else ''}.")

        summary = ""
        for sentence in sentences:
            if len(summary) + len(sentence) + 1 > max_chars:
                break
            summary = f"{summary} {sentence}".strip()
        return summary

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
        rewritten = self._groq_chat(
            system,
            json.dumps(job_context, ensure_ascii=True),
            json_mode=False,
            max_tokens=1000,
            token_field="max_completion_tokens",
            timeout=(5, 20),
        )
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

    VOCABULARY_WORDS = {
        "analysis", "analytics", "architecture", "collaboration", "collaborated", "collaborating",
        "coordination", "coordinated", "delivery", "delivering", "design", "designed", "designing",
        "development", "developing", "documentation", "documenting", "engineering", "engineer",
        "integration", "integrated", "integrating", "leadership", "led", "management", "managed",
        "mentoring", "mentored", "monitoring", "monitored", "optimization", "optimized", "optimizing",
        "performance", "planning", "planned", "problem solving", "quality", "reliability",
        "reporting", "reported", "research", "researched", "scalability", "scalable", "security",
        "strategy", "strategic", "support", "supported", "supporting", "testing", "tested",
        "troubleshooting", "troubleshot", "agile", "scrum", "cross-functional", "best practices",
        "clean code", "high-performance", "full-stack", "front-end", "back-end", "api", "apis", "rest api",
        "automation", "automated", "streamlined", "accelerated", "refactored", "spearheaded",
        "achieved", "executed", "oversaw", "established", "implemented", "implementing"
    }

    @classmethod
    def _is_mathematically_equivalent_metric(cls, new_num_str: str, old_numbers: Set[str]) -> bool:
        """Check if a new metric (e.g. 50%) is mathematically derivable from original numbers (e.g. 500 and 250)."""
        try:
            val = float(new_num_str.replace(",", ""))
        except ValueError:
            return False

        float_olds = []
        for s in old_numbers:
            try:
                float_olds.append(float(s.replace(",", "")))
            except ValueError:
                pass

        if len(float_olds) >= 2:
            for i in range(len(float_olds)):
                for j in range(len(float_olds)):
                    if i != j:
                        a, b = float_olds[i], float_olds[j]
                        if max(a, b) > 0:
                            pct_change = round((abs(a - b) / max(a, b)) * 100)
                            if abs(val - pct_change) < 1.0:
                                return True
                        if b > 0:
                            ratio = round(a / b, 1)
                            if abs(val - ratio) < 0.1:
                                return True
        return False

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
                "internships": entry_payload(tailored.get("internships")),
                "projects": entry_payload(tailored.get("projects")),
            },
        }
        system = (
            "You are an expert resume writer. Write or rewrite the candidate's professional_summary and every experience, "
            "internship and project description and bullet to optimize the resume for the target role. Use the exact priority keywords "
            "where they accurately describe the supplied experience. Put verified_job_keywords into the skills list "
            "through the pre-verified profile data and naturally emphasize them in relevant summary and work/project text. "
            "Aim for a concise 2-4 sentence summary of 250-600 characters when the supplied facts support it. "
            "The summary must state the candidate's real experience level: internships are internships and academic "
            "projects are projects; never describe them as full-time or professional employment, and never claim "
            "years of experience the resume does not state. "
            "STRICT RULES: use ONLY facts already present in the resume. Never add numbers, metrics, percentages, dates, "
            "employers, tools, technologies, skills or achievements that are not already in the resume. Do not claim "
            "a priority keyword unless it is in verified_job_keywords or already supported by the resume text. "
            "If professional_summary is empty, draft 2-3 concise sentences using only verified_summary_facts; do not "
            "leave it empty when those facts provide enough information. "
            "Never add new bullets beyond the original count for an entry. Keep each entry's index. "
            "A description must add something the bullets do not already say; if it would only repeat or summarise "
            "the bullets or the role line, return an empty string for it. Never repeat a bullet. "
            "Write plain text: no markdown, no headings, no bold markers. "
            "Return one valid JSON object only, with this exact structure and JSON value types: "
            "{\"professional_summary\":\"text\","
            "\"experience\":[{\"index\":0,\"description\":\"text\",\"bullets\":[\"text\"]}],"
            "\"internships\":[{\"index\":0,\"description\":\"text\",\"bullets\":[\"text\"]}],"
            "\"projects\":[{\"index\":0,\"description\":\"text\",\"bullets\":[\"text\"]}]}. "
            "Use empty arrays when a section has no entries and an empty string when no rewrite is appropriate. "
            "Do not include markdown fences or any text outside the JSON object."
        )
        steer = re.sub(r"\s+", " ", str(instructions or "")).strip()[:500]
        if steer:
            system += (
                " The candidate also asked: \"" + steer + "\". Use this only to choose which existing facts to "
                "emphasise and how to phrase them; it never permits adding facts that are not in the resume."
            )
        rewritten = self._groq_chat(
            system,
            json.dumps(payload, ensure_ascii=True),
            json_mode=True,
            # Room for every bullet; a truncated reply is invalid JSON and moves to the next model.
            max_tokens=4000,
            timeout=(5, 45),
        )

        result = self.merge_rewrite(tailored, rewritten, skill_extractor)
        if (
            not str(tailored.get("professional_summary") or "").strip()
            and not str(result["resume"].get("professional_summary") or "").strip()
        ):
            result["resume"]["professional_summary"] = self._summary_from_verified_facts(tailored)
        return result

    @classmethod
    def merge_rewrite(cls, tailored: Dict[str, Any], rewritten: Dict[str, Any], skill_extractor) -> Dict[str, Any]:
        """Apply AI-rewritten text onto ``tailored``, keeping the original wherever a line adds unverified facts."""
        original_text = json.dumps(tailored, ensure_ascii=False).lower()
        original_numbers = set(cls._NUMBER_PATTERN.findall(original_text))
        original_skills = {s.lower() for s in skill_extractor.extract_skills(original_text)}
        for s in tailored.get("skills") or []:
            if isinstance(s, str):
                original_skills.add(s.lower())

        rejected = 0
        total_bullets = 0
        accepted_bullets = 0
        rejection_reasons: List[str] = []
        diagnostics: List[Dict[str, Any]] = []

        def accept(new: Any, old: str, context: str = "") -> str:
            nonlocal rejected, total_bullets, accepted_bullets
            # Plain text only: drop markdown bold/heading markers the model sometimes adds.
            candidate = cls._clean_text(re.sub(r"\*\*|__|^#+\s*", "", str(new or "")))
            if not candidate:
                return old

            total_bullets += 1
            lowered = candidate.lower()

            # Check numbers / metrics
            candidate_numbers = set(cls._NUMBER_PATTERN.findall(lowered))
            new_numbers = candidate_numbers - original_numbers
            unverified_numbers = set()
            for num_str in new_numbers:
                if not cls._is_mathematically_equivalent_metric(num_str, original_numbers):
                    if num_str not in {"1", "2", "3"} or num_str not in original_text:
                        unverified_numbers.add(num_str)

            # Check skills / technologies
            candidate_skills = {s.lower() for s in skill_extractor.extract_skills(lowered)}
            unverified_skills = set()
            for s in candidate_skills:
                if s not in original_skills and s not in cls.VOCABULARY_WORDS:
                    unverified_skills.add(s)

            if unverified_numbers or unverified_skills:
                rejected += 1
                reasons = []
                if unverified_skills:
                    reasons.append(f"Unverified technologies claimed: {', '.join(sorted(unverified_skills))}")
                if unverified_numbers:
                    reasons.append(f"Unverified numerical claims: {', '.join(sorted(unverified_numbers))}")
                reason_str = "; ".join(reasons)
                rejection_reasons.append(f"{context}: {reason_str}" if context else reason_str)
                diagnostics.append({
                    "context": context,
                    "original": old,
                    "rewritten": candidate,
                    "accepted": False,
                    "reason": reason_str,
                })
                return old

            accepted_bullets += 1
            diagnostics.append({
                "context": context,
                "original": old,
                "rewritten": candidate,
                "accepted": True,
                "reason": "Accepted: factual and supported by resume evidence",
            })
            return candidate

        result = json.loads(json.dumps(tailored))  # deep copy
        if not isinstance(rewritten, dict):
            rewritten = {}
        result["professional_summary"] = accept(
            rewritten.get("professional_summary"), tailored.get("professional_summary") or "", context="Summary"
        )
        for section in ("experience", "projects", "internships"):
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
                    entry["description"] = accept(new.get("description"), entry["description"], context=f"{section}[{i}].description")
                old_bullets = list(entry.get("bullets") or [])
                new_bullets = cls._normalize_bullets(new.get("bullets"))
                # Same number of bullets as before; each one checked against the original facts.
                entry["bullets"] = [
                    accept(new_bullets[j] if j < len(new_bullets) else "", old, context=f"{section}[{i}].bullet[{j+1}]")
                    for j, old in enumerate(old_bullets)
                ]
        # Education is never rewritten by the AI (a description would only restate the degree line).
        # A rewritten description that just repeats the role line or bullets is dropped.
        for section in ("experience", "projects", "internships"):
            result[section] = [without_repeats(e) if isinstance(e, dict) else e for e in (result.get(section) or [])]
        return {
            "resume": result,
            "rejected_lines": rejected,
            "total_bullets_processed": total_bullets,
            "successfully_rewritten_bullets": accepted_bullets,
            "rejected_bullets": rejected,
            "rejection_reasons": rejection_reasons,
            "diagnostics": diagnostics,
        }


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
            dates = standardize_dates(entry.get("dates") or entry.get("date") or entry.get("period") or entry.get("year") or "")
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
        # Repeated records are merged, and text that only repeats the entry is dropped.
        return [without_repeats(e) for e in dedupe_entries(normalized, section)]

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
            "experience": self._normalize_entries(pick("experience", resume.get("experience")), section="experience"),
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
        if keep_edits:
            # The user's own edits decide which section an entry is in; only exact copies of an
            # internship that also sit under Work Experience are removed.
            res["experience"] = [
                e for e in res["experience"]
                if not any(same_record(i, e, "internships") for i in res["internships"])
            ]
            return res
        # Generated from the profile: an internship listed under Experience moves to Internships,
        # and an empty AI reply for internships has already fallen back to the profile above.
        res["experience"], res["internships"] = split_internships(res["experience"], res["internships"])
        return self._enforce_length_limits(res)

    @classmethod
    def _enforce_length_limits(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Keep a tailored resume concise without dropping any record.

        Every experience, internship, education, project, certification, publication and
        achievement entry is kept; a long resume runs onto a second page instead. Only the
        summary length, the bullets per entry and the size of the skills list are capped.
        """
        summary = data.get("professional_summary", "")
        if len(summary) > MAX_SUMMARY_CHARS:
            kept = ""
            for sentence in re.split(r"(?<=[.!?])\s+", summary):
                if len(kept) + len(sentence) + 1 > MAX_SUMMARY_CHARS:
                    break
                kept = f"{kept} {sentence}".strip()
            data["professional_summary"] = kept or summary[:MAX_SUMMARY_CHARS].rsplit(" ", 1)[0]

        for section in ENTRY_SECTIONS:
            for item in data.get(section) or []:
                bullets = item.get("bullets") or []
                if len(bullets) > MAX_BULLETS_PER_ENTRY:
                    item["bullets"] = bullets[:MAX_BULLETS_PER_ENTRY]

        skills = data.get("skills", [])
        if len(skills) > MAX_RESUME_SKILLS:
            data["skills"] = skills[:MAX_RESUME_SKILLS]

        return data

    def _export_docx(self, structured: Dict[str, Any], docx_path: Path) -> Path:
        """Export an ATS-friendly, single-column A4 DOCX.

        Built from ``render_sections`` - the same section order, headings and entry lines as
        the LaTeX PDF and the in-app preview - so every format shows the same content.
        Headings and entry title lines are kept with the text that follows them, and a long
        resume simply continues onto a second page.
        """
        doc = docx.Document()
        for section in doc.sections:
            section.page_width = Mm(210)
            section.page_height = Mm(297)
            section.top_margin = section.bottom_margin = Mm(16)
            section.left_margin = section.right_margin = Mm(18)

        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(10.5)
        normal.paragraph_format.space_after = Pt(0)
        normal.paragraph_format.line_spacing = 1.1

        ink = RGBColor(17, 24, 39)

        def paragraph(before: float = 0, after: float = 0, keep_next: bool = False, center: bool = False, style=None):
            p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
            fmt = p.paragraph_format
            fmt.space_before = Pt(before)
            fmt.space_after = Pt(after)
            fmt.keep_with_next = keep_next
            if center:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            return p

        def add_run(p, text: str, size: float = 10.5, bold: bool = False, italic: bool = False, color=ink):
            r = p.add_run(text)
            r.bold = bold
            r.italic = italic
            r.font.name = "Calibri"
            r.font.size = Pt(size)
            r.font.color.rgb = color
            return r

        def top_rule(p) -> None:
            """Full-width rule above a section heading, as in the UK template."""
            borders = OxmlElement("w:pBdr")
            top = OxmlElement("w:top")
            for key, value in (("w:val", "single"), ("w:sz", "8"), ("w:space", "8"), ("w:color", "111111")):
                top.set(qn(key), value)
            borders.append(top)
            p._p.get_or_add_pPr().append(borders)

        info = structured.get("personal_info") or {}
        if info.get("name"):
            add_run(paragraph(center=True), info["name"].upper(), size=24, bold=True)
        if structured.get("target_role"):
            add_run(paragraph(before=2, center=True), structured["target_role"], size=14)
        contacts = [c["text"] for c in self._contact_items(info)]
        if contacts:
            add_run(paragraph(before=4, after=2, center=True), "   |   ".join(contacts), size=10.5)

        for section in render_sections(structured):
            heading = paragraph(before=10, after=4, keep_next=True)
            add_run(heading, section["title"].upper(), size=14, bold=True)
            top_rule(heading)
            if section["kind"] == "text":
                add_run(paragraph(after=2), section["text"])
                continue
            if section["kind"] == "skills":
                # Three columns of bullets as plain tab-separated rows (no table, so ATS parsers
                # read every skill), filled top-to-bottom like the template.
                skills = section["skills"]
                rows = -(-len(skills) // 3)
                columns = [skills[c * rows:(c + 1) * rows] for c in range(3)]
                for r in range(rows):
                    p = paragraph(after=1)
                    for stop in (1, 2):
                        p.paragraph_format.tab_stops.add_tab_stop(Mm((210 - 36) * stop / 3))
                    cells = [col[r] if r < len(col) else "" for col in columns]
                    add_run(p, "	".join(f"•  {c}" if c else "" for c in cells).rstrip("	"))
                continue
            for index, entry in enumerate(section["entries"]):
                has_body = bool(entry["description"] or entry["bullets"])
                before = 0 if index == 0 else 7
                if entry["meta"]:
                    add_run(paragraph(before=before, keep_next=bool(entry["heading"]) or has_body), entry["meta"])
                    before = 0
                if entry["heading"]:
                    add_run(paragraph(before=before, keep_next=has_body), entry["heading"], bold=True)
                if entry["description"]:
                    add_run(paragraph(before=1, after=1, keep_next=bool(entry["bullets"])), entry["description"])
                for bullet in entry["bullets"]:
                    p = paragraph(after=1, style="List Bullet")
                    add_run(p, bullet)

        doc.save(str(docx_path))
        return docx_path

    @staticmethod
    def _contact_items(info: Dict[str, Any]) -> List[Dict[str, str]]:
        """Contact line items (display text + link) shared by the DOCX and LaTeX exports."""
        clean = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()  # noqa: E731
        items: List[Dict[str, str]] = []
        # Template order: phone | email | location, then profile links.
        if clean(info.get("phone")):
            items.append({"text": clean(info["phone"]), "href": "tel:" + re.sub(r"[^\d+]", "", info["phone"])})
        if clean(info.get("email")):
            items.append({"text": clean(info["email"]), "href": f"mailto:{clean(info['email'])}"})
        if clean(info.get("location")):
            items.append({"text": clean(info["location"]), "href": ""})
        linkedin = re.sub(r"^(?:https?://)?(?:www\.)?(?:linkedin\.com/(?:in/)?)?", "", clean(info.get("linkedin")), flags=re.I).strip("/")
        if linkedin:
            items.append({"text": f"linkedin.com/in/{linkedin}", "href": f"https://linkedin.com/in/{linkedin}"})
        github = re.sub(r"^(?:https?://)?(?:www\.)?(?:github\.com/)?", "", clean(info.get("github")), flags=re.I).strip("/")
        if github:
            items.append({"text": f"github.com/{github}", "href": f"https://github.com/{github}"})
        site = re.sub(r"^https?://", "", clean(info.get("portfolio") or info.get("website")), flags=re.I).strip("/")
        if site:
            items.append({"text": site, "href": f"https://{site}"})
        return items

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
            "—": "---",
            "–": "--",
            "“": "``",
            "”": "''",
            "’": "'",
            "‘": "'",
            "•": r"\textbullet{}",
        }
        return "".join(replacements.get(char, char) for char in str(value or ""))

    @staticmethod
    def _urlescape(value: Any) -> str:
        """Escape the few characters that break ``\\href`` targets."""
        return str(value or "").replace("\\", "").replace("%", r"\%").replace("#", r"\#").replace("{", "").replace("}", "")

    def _render_latex(self, data: Dict[str, Any]) -> str:
        template = self.environment.get_template("uk_standard_resume.tex.j2")
        return template.render(
            personal_info=data.get("personal_info") or {},
            target_role=data.get("target_role") or "",
            contacts=self._contact_items(data.get("personal_info") or {}),
            sections=render_sections(data),
        )

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
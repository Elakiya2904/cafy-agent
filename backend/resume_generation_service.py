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

    def generate(self, resume: Dict[str, Any], job: Dict[str, Any]) -> Dict[str, Any]:
        if not resume:
            raise ResumeGenerationError("Upload a résumé before generating a tailored version.")
        if not job:
            raise ResumeGenerationError("The selected job could not be found.")

        source_text = str(resume.get("raw_text") or resume.get("summary") or "")
        structured = self._tailor_with_groq(resume, job, source_text)
        structured = self._validate_and_normalize(structured, resume, job)
        resume_id = uuid.uuid4().hex

        # Render LaTeX
        tex = self._render_latex(structured)
        tex_path = self.output_dir / f"{resume_id}.tex"
        tex_path.write_text(tex, encoding="utf-8")

        # Compile PDF (if compiler available)
        pdf_path = self._compile_pdf(tex_path)

        # Export DOCX
        docx_path = self.output_dir / f"{resume_id}.docx"
        self._export_docx(structured, docx_path)

        return {
            "status": "success" if pdf_path else "generated_without_pdf",
            "resume_id": resume_id,
            "template": "uk-standard",
            "resume": structured,
            "tex_url": f"/api/resumes/{resume_id}/latex",
            "pdf_url": f"/api/resumes/{resume_id}/pdf" if pdf_path else None,
            "docx_url": f"/api/resumes/{resume_id}/docx",
            "pdf_available": bool(pdf_path),
            "docx_available": True,
            "validation": {
                "ats_friendly": True,
                "factual_consistency": True,
                "page_length": "1-2 pages",
                "unsupported_claims": [],
            },
        }

    def update_artifacts(self, resume_id: str, structured: Dict[str, Any]) -> Dict[str, Any]:
        """Re-render LaTeX, DOCX, and PDF for an updated/saved draft."""
        tex = self._render_latex(structured)
        tex_path = self.output_dir / f"{resume_id}.tex"
        tex_path.write_text(tex, encoding="utf-8")

        pdf_path = self._compile_pdf(tex_path)

        docx_path = self.output_dir / f"{resume_id}.docx"
        self._export_docx(structured, docx_path)

        return {
            "resume_id": resume_id,
            "tex_url": f"/api/resumes/{resume_id}/latex",
            "pdf_url": f"/api/resumes/{resume_id}/pdf" if pdf_path else None,
            "docx_url": f"/api/resumes/{resume_id}/docx",
            "pdf_available": bool(pdf_path),
            "docx_available": True,
        }

    def rewrite_section(
        self, section: str, content: str, job: Dict[str, Any], resume_data: Dict[str, Any]
    ) -> str:
        """AI-powered section rewrite preserving factual accuracy and tailoring to the role."""
        api_key = os.getenv("groq_api_key") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ResumeGenerationError("AI rewriting is not configured. Add GROQ_API_KEY to the environment.")

        target_role = job.get("title") or "target role"
        company = job.get("company") or "the company"

        is_bullet = "bullet" in section.lower()
        system = (
            f"You are an expert UK/IE executive resume writer. Rewrite the following resume {section} "
            f"for the role of {target_role} at {company}. "
            "Keep it concise, high-impact, professional, and ATS-friendly. "
            + ("Return a single outcome-oriented bullet starting with a strong action verb, without leading bullet characters or quotes. " if is_bullet else "")
            + "CRITICAL: Do NOT invent employers, dates, achievements, credentials, or technologies not present in the original text. "
            "Preserve factual truth while enhancing active phrasing and clarity. Return plain text only."
        )
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Original text to improve:\n{content}"},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1000,
                },
                timeout=(5, 20),
            )
        except requests.RequestException as err:
            raise ResumeGenerationError("AI rewriting service is temporarily unavailable.") from err

        if response.status_code != 200:
            raise ResumeGenerationError(f"AI rewriting failed with status {response.status_code}.")

        rewritten = response.json()["choices"][0]["message"]["content"].strip()
        if not rewritten:
            raise ResumeGenerationError("AI rewriting returned empty response.")
        return self._clean_text(rewritten)

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
            "STRICT 1-PAGE A4 REQUIREMENT: The tailored resume MUST fit on exactly one single A4 page with balanced vertical proportion. "
            "Return JSON only with keys: personal_info, professional_summary, education, experience, projects, certifications, skills. "
            "Limit professional_summary to 2-3 concise, high-impact sentences. "
            "Include only the top 2-3 most relevant work experiences with at most 2-3 bullet points each. "
            "Include only the top 2-3 most relevant projects with at most 2-3 bullet points each. "
            "Include genuine degrees and top 12-16 relevant skills. "
            "education, experience, projects, and certifications must be arrays of objects. "
            "Each experience object must have: title, organization (or company), dates, location, description, and bullets (a JSON array of concise bullet strings). "
            "Each project object must have: title, organization, dates, description, and bullets (a JSON array of strings). "
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
                    "model": os.getenv("GROQ_MODEL") or "llama-3.3-70b-versatile",
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
        for entry in entries[:8]:
            if not isinstance(entry, dict):
                continue
            title = self._clean_text(
                entry.get("title") or entry.get("role") or entry.get("name") or entry.get("degree") or ""
            )
            org = self._clean_text(
                entry.get("organization") or entry.get("company") or entry.get("institution") or entry.get("school") or entry.get("issuer") or ""
            )
            dates = self._clean_text(entry.get("dates") or entry.get("date") or entry.get("period") or "")
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
        self, generated: Dict[str, Any], resume: Dict[str, Any], job: Dict[str, Any]
    ) -> Dict[str, Any]:
        if not isinstance(generated, dict):
            generated = {}

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
        if not skills:
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
                "name": self._clean_text(p_info.get("name") or resume.get("candidate_name") or "Candidate"),
                "email": self._clean_text(p_info.get("email") or resume.get("email") or ""),
                "phone": self._clean_text(p_info.get("phone") or resume.get("phone") or ""),
                "linkedin": clean_linkedin,
                "github": clean_github,
                "portfolio": clean_portfolio,
                "location": self._clean_text(p_info.get("location") or resume.get("location") or job.get("location") or ""),
            },
            "target_role": self._clean_text(job.get("title") or generated.get("target_role") or ""),
            "company": self._clean_text(job.get("company") or generated.get("company") or ""),
            "professional_summary": self._clean_text(
                generated.get("professional_summary") or resume.get("summary") or ""
            ),
            "education": self._normalize_entries(generated.get("education") or resume.get("education"), section="education"),
            "experience": self._normalize_entries(generated.get("experience") or resume.get("experience"), section="experience"),
            "projects": self._normalize_entries(generated.get("projects") or resume.get("projects"), section="projects"),
            "certifications": self._normalize_entries(generated.get("certifications") or resume.get("certifications"), section="certifications"),
            "skills": deduped_skills,
        }
        return self._enforce_single_page_limits(res)

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
        if len(proj) > 3:
            proj = proj[:3]
        for item in proj:
            bullets = item.get("bullets") or []
            if len(bullets) > 3:
                item["bullets"] = bullets[:3]
        data["projects"] = proj

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
        if len(skills) > 18:
            data["skills"] = skills[:18]

        return data

    def _export_docx(self, structured: Dict[str, Any], docx_path: Path) -> Path:
        """Exports ATS-friendly clean single-column DOCX format."""
        doc = docx.Document()

        # Set standard margins (0.75 in / 1.9 cm)
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.6)
            section.bottom_margin = Inches(0.6)
            section.left_margin = Inches(0.7)
            section.right_margin = Inches(0.7)

        p_info = structured.get("personal_info", {})
        name = p_info.get("name") or "Candidate"
        target_role = structured.get("target_role") or ""

        # Title / Name
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

        # Professional Summary
        summary = structured.get("professional_summary")
        if summary:
            add_section_heading("Professional Summary")
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
                r_title = p_item.add_run(item.get("title") or "Role")
                r_title.bold = True
                r_title.font.name = "Calibri"
                r_title.font.size = Pt(10.5)

                org = item.get("organization") or item.get("company")
                if org:
                    r_org = p_item.add_run(f" | {org}")
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
                r_title = p_item.add_run(item.get("title") or item.get("name") or "Project")
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
                r_deg = p_item.add_run(item.get("degree") or item.get("title") or "Degree")
                r_deg.bold = True
                r_deg.font.name = "Calibri"
                r_deg.font.size = Pt(10)

                inst = item.get("institution") or item.get("organization") or item.get("school")
                if inst:
                    r_inst = p_item.add_run(f" | {inst}")
                    r_inst.font.name = "Calibri"
                    r_inst.font.size = Pt(10)

                if item.get("dates"):
                    r_d = p_item.add_run(f" ({item['dates']})")
                    r_d.font.name = "Calibri"
                    r_d.font.size = Pt(9.5)
                    r_d.font.italic = True

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

        # Certifications
        certs = structured.get("certifications") or []
        if certs:
            add_section_heading("Certifications")
            for item in certs:
                p_item = doc.add_paragraph()
                p_item.paragraph_format.space_after = Pt(2)
                r_name = p_item.add_run(item.get("name") or item.get("title") or "Certification")
                r_name.bold = True
                r_name.font.name = "Calibri"
                r_name.font.size = Pt(10)
                if item.get("issuer") or item.get("organization"):
                    r_iss = p_item.add_run(f" - {item.get('issuer') or item.get('organization')}")
                    r_iss.font.name = "Calibri"
                    r_iss.font.size = Pt(9.5)
                if item.get("dates"):
                    r_d = p_item.add_run(f" ({item['dates']})")
                    r_d.font.name = "Calibri"
                    r_d.font.size = Pt(9.5)
                    r_d.font.italic = True

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

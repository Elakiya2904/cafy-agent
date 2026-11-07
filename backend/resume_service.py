"""Parse uploaded resumes and extract structured candidate profile information.

Handles PDF/DOCX text extraction, section classification, skill normalization,
and conversion to the profile shape used by matching and editing features.
"""
import os
import re
import io
import unicodedata
from functools import lru_cache
from typing import Dict, List, Any, Set, Optional, Tuple
import pypdf
import docx

try:
    from .profile_strength_service import evaluate_profile_strength
    from .resume_structure import dedupe_entries, full_time_years, split_internships
except ImportError:
    from profile_strength_service import evaluate_profile_strength
    from resume_structure import dedupe_entries, full_time_years, split_internships

# Comprehensive Skills Ontology & Categorization
SKILL_TAXONOMY = {
    "Programming Languages": [
        "Python", "JavaScript", "TypeScript", "Go", "Golang", "Java", "C++", "C#", ".NET",
        "Rust", "Ruby", "PHP", "Swift", "Kotlin", "SQL", "HTML", "CSS", "Bash", "Shell",
        "Scala", "R", "Dart", "Solidity", "Elixir"
    ],
    "Frontend Development": [
        "React", "React.js", "Vue", "Vue.js", "Angular", "Next.js", "Nuxt.js", "Svelte",
        "Tailwind CSS", "TailwindCSS", "Redux", "Zustand", "Webpack", "Vite", "GraphQL",
        "HTML5", "CSS3", "SCSS", "SASS", "WebSockets", "Bootstrap", "Responsive Design"
    ],
    "Backend & APIs": [
        "Node.js", "Express", "FastAPI", "Django", "Flask", "Spring Boot", "NestJS",
        "Ruby on Rails", "ASP.NET Core", "Go Fiber", "gRPC", "REST API", "Microservices",
        "Celery", "RabbitMQ", "Apache Kafka", "Kafka", "Webhooks"
    ],
    "Cloud & DevOps": [
        "AWS", "Amazon Web Services", "Azure", "GCP", "Google Cloud", "Docker",
        "Kubernetes", "K8s", "Terraform", "CI/CD", "GitHub Actions", "Jenkins",
        "Ansible", "Helm", "Linux", "Unix", "Nginx", "Prometheus", "Grafana",
        "Serverless", "Infrastructure as Code"
    ],
    "AI, Machine Learning & Data": [
        "PyTorch", "TensorFlow", "Scikit-Learn", "Pandas", "NumPy", "BigQuery",
        "Snowflake", "Databricks", "Apache Spark", "Spark", "PySpark", "Airflow", "dbt", "LLM",
        "LLMs", "Generative AI", "LangChain", "LlamaIndex", "RAG", "NLP",
        "Computer Vision", "Hugging Face", "Machine Learning", "Deep Learning", "ETL"
    ],
    "Databases & Storage": [
        "PostgreSQL", "Postgres", "MySQL", "MongoDB", "Redis", "Cassandra",
        "DynamoDB", "Elasticsearch", "SQLite", "Vector Database", "Pinecone",
        "ChromaDB", "Supabase", "Firebase"
    ],
    "Testing & Tools": [
        "Jest", "Cypress", "Playwright", "PyTest", "Selenium", "Git", "GitHub",
        "GitLab", "Jira", "Agile", "Scrum", "Figma", "Postman", "System Design"
    ]
}

SKILL_ALIASES = {
    "golang": "Go",
    "js": "JavaScript",
    "ts": "TypeScript",
    "py": "Python",
    "reactjs": "React",
    "react.js": "React",
    "nextjs": "Next.js",
    "vuejs": "Vue",
    "vue.js": "Vue",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "k8s": "Kubernetes",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "tailwind": "TailwindCSS",
    "tailwindcss": "TailwindCSS",
    "cicd": "CI/CD",
    "ci/cd": "CI/CD",
    "kafka": "Apache Kafka",
    "spark": "Apache Spark",
    "sklearn": "Scikit-Learn",
    "scikit-learn": "Scikit-Learn",
    "llm": "LLMs",
    "llms": "LLMs",
    "genai": "Generative AI",
    "rag": "RAG",
    "crm": "CRM",
    "b2b sales": "B2B Sales",
    "biz dev": "Business Development",
    "bd": "Business Development",
    "cold-calling": "Cold Calling",
    "pre sales": "Pre-Sales",
    "microsoft excel": "Excel",
    "microsoft powerpoint": "PowerPoint",
    "sales navigator": "LinkedIn Sales Navigator",
    "cross selling": "Cross-selling",
    "up-selling": "Upselling",
    "upselling": "Upselling"
}

# Non-engineering professions (teaching, accounting, finance, hardware, healthcare, ...)
from .skill_matching import SkillIndex, text_has_skill
from .skill_catalog import (
    ALIASES as CATALOG_ALIASES,
    GENERAL_SKILLS,
    all_roles as catalog_roles,
    domain_skill_taxonomy,
)
for _cat, _skills in domain_skill_taxonomy().items():
    SKILL_TAXONOMY.setdefault(_cat, [])
    SKILL_TAXONOMY[_cat] = list(dict.fromkeys(SKILL_TAXONOMY[_cat] + _skills))
SKILL_TAXONOMY["General & Soft Skills"] = list(GENERAL_SKILLS)
SKILL_ALIASES.update({k: v for k, v in CATALOG_ALIASES.items() if k not in SKILL_ALIASES})

ALL_CANONICAL_SKILLS = []
for cat_skills in SKILL_TAXONOMY.values():
    ALL_CANONICAL_SKILLS.extend(cat_skills)
ALL_CANONICAL_SKILLS = sorted(list(set(ALL_CANONICAL_SKILLS)), key=lambda s: len(s), reverse=True)
_CANONICAL_BY_LOWER: Dict[str, str] = {}
for _canonical in ALL_CANONICAL_SKILLS:
    _CANONICAL_BY_LOWER.setdefault(_canonical.lower(), _canonical)
# Very short names are skipped (they'd match ordinary letters) except real languages.
_SKILL_INDEX = SkillIndex([s for s in ALL_CANONICAL_SKILLS if len(s) > 2 or s in ("Go", "R", "C")])


class ResumeService:
    """
    Service responsible for extracting text, candidate metadata, and skills
    from uploaded resumes (PDF, DOCX, TXT), as well as evaluating profile strength.
    """

    def parse_resume(self, filename: str, content_bytes: bytes) -> Dict[str, Any]:
        ext = os.path.splitext(filename)[1].lower()
        text = ""

        if ext == ".pdf":
            text = self._read_pdf(content_bytes)
        elif ext in [".docx", ".doc"]:
            text = self._read_docx(content_bytes)
        else:
            try:
                text = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                text = self._read_pdf(content_bytes)

        return self.analyze_text(text, filename)

    def _read_pdf(self, content_bytes: bytes) -> str:
        reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        pages_text = []
        for page in reader.pages:
            layout_text = page.extract_text(extraction_mode="layout") or ""
            plain_text = page.extract_text() or ""
            processed_layout = self._process_multicol_layout(layout_text) if layout_text else ""
            if not processed_layout:
                page_text = plain_text
            elif not plain_text:
                page_text = processed_layout
            elif self._pdf_line_quality(plain_text) > self._pdf_line_quality(processed_layout) + 0.15:
                page_text = plain_text
            else:
                page_text = processed_layout
            if page_text:
                # Rejoin hyphenated word breaks at end of lines
                page_text = re.sub(r"([A-Za-z]{2,})-\n([A-Za-z]{2,})", r"\1\2", page_text)
                pages_text.append(page_text)
        extracted = "\n".join(pages_text).strip()
        return self._detect_scanned_pdf(extracted, len(reader.pages)) or extracted

    @staticmethod
    def _detect_scanned_pdf(extracted_text: str, page_count: int) -> Optional[str]:
        """Warning text when a PDF has pages but (almost) no extractable text, i.e. it is a scan."""
        if page_count > 0 and len(re.sub(r"\s+", "", extracted_text or "")) < 40:
            return "[Scanned or image-based PDF detected. No extractable text found. Text extraction requires OCR or a text-based PDF.]"
        return None

    def _extract_candidate_info(self, text: str) -> Dict[str, str]:
        """Name and contact details from the resume header (only what the text contains)."""
        email = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text or "")
        phone = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}", text or "")
        return {
            "name": self._detect_name(text or "", ""),
            "email": email.group(0) if email else "",
            "phone": phone.group(0).strip() if phone else "",
            "location": self._detect_location(text or ""),
        }

    @staticmethod
    def _process_multicol_layout(text: str) -> str:
        """If layout text has a consistent vertical gutter, separate left and right columns."""
        lines = text.splitlines()
        if len(lines) < 6:
            return text
        col_splits = []
        for line in lines:
            m = re.search(r"\S(\s{6,})\S", line)
            if m:
                col_splits.append(m.start(1))
        if len(col_splits) >= len(lines) * 0.4:
            median_split = sorted(col_splits)[len(col_splits) // 2] + 3
            left_lines = []
            right_lines = []
            for line in lines:
                if len(line) > median_split:
                    left = line[:median_split].strip()
                    right = line[median_split:].strip()
                    if left:
                        left_lines.append(left)
                    if right:
                        right_lines.append(right)
                else:
                    if line.strip():
                        left_lines.append(line.strip())
            return "\n".join(left_lines + ["\n"] + right_lines)
        return text

    @staticmethod
    def _pdf_line_quality(text: str) -> float:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return 0.0
        multiword_lines = sum(len(line.split()) > 1 for line in lines)
        return multiword_lines / len(lines)

    def _read_docx(self, content: Any) -> str:
        """Text of a DOCX (bytes or a file path), including tables and nested tables in order."""
        doc = docx.Document(io.BytesIO(content) if isinstance(content, (bytes, bytearray)) else str(content))
        lines: List[str] = []

        def extract_cell(cell) -> List[str]:
            cell_lines = []
            for p in cell.paragraphs:
                txt = p.text.strip()
                if txt:
                    cell_lines.append(txt)
            for tbl in cell.tables:
                for row in tbl.rows:
                    r_cells = []
                    for nested_cell in row.cells:
                        nested_txt = "\n".join(extract_cell(nested_cell))
                        if nested_txt and nested_txt not in r_cells:
                            r_cells.append(nested_txt)
                    if r_cells:
                        cell_lines.append(" | ".join(r_cells))
            return cell_lines

        # Traverse document body in true document order
        for element in getattr(doc.element, "body", []):
            if element.tag.endswith("p"):
                p = docx.text.paragraph.Paragraph(element, doc)
                txt = p.text.strip()
                if txt:
                    lines.append(txt)
            elif element.tag.endswith("tbl"):
                tbl = docx.table.Table(element, doc)
                for row in tbl.rows:
                    row_cells = []
                    for cell in row.cells:
                        cell_text = "\n".join(extract_cell(cell))
                        if cell_text and cell_text not in row_cells:
                            row_cells.append(cell_text)
                    if row_cells:
                        lines.append(" | ".join(row_cells))

        if not lines:
            for p in doc.paragraphs:
                txt = p.text.strip()
                if txt:
                    lines.append(txt)
            for table in doc.tables:
                for row in table.rows:
                    row_cells = []
                    for cell in row.cells:
                        cell_text = "\n".join([p.text.strip() for p in cell.paragraphs if p.text.strip()])
                        if cell_text and cell_text not in row_cells:
                            row_cells.append(cell_text)
                    if row_cells:
                        lines.append(" | ".join(row_cells))
        return "\n".join(lines)

    @staticmethod
    def _normalize_resume_text(text: str) -> str:
        """Make extracted text uniform before parsing.

        - NFKC folds PDF ligatures (e.g. the "fi" ligature) and odd spaces into plain text.
        - Windows line breaks become plain newlines.
        - A wide run of spaces inside a line is a column gap in the PDF layout (e.g. a role on the
          left and its dates on the right); it becomes " | " so it reads as a field separator
          instead of making the line too long to be recognised as an entry header.
        """
        text = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", "\n")
        return re.sub(r"(?<=\S)[ \t]{4,}(?=\S)", " | ", text)

    def analyze_text(self, text: str, filename: str = "Uploaded_Resume.pdf") -> Dict[str, Any]:
        text = self._normalize_resume_text(text)
        if "[Scanned or image-based PDF detected" in text:
            return {
                "filename": filename,
                "raw_text": text,
                "candidate_name": "",
                "personal_info": {"name": "", "email": "", "phone": "", "location": "", "linkedin": "", "github": "", "portfolio": ""},
                "email": "",
                "phone": "",
                "location": "",
                "linkedin": "",
                "github": "",
                "portfolio": "",
                "skills": [],
                "inferred_skills": [],
                "all_skills": [],
                "skill_evidence": {},
                "categorized_skills": {},
                "total_skills": 0,
                "years_of_experience": 0,
                "seniority_level": "Unknown",
                "target_roles": [],
                "summary": "",
                "professional_summary": "",
                "experience": [],
                "internships": [],
                "education": [],
                "projects": [],
                "publications": [],
                "certifications": [],
                "achievements": [],
                "extraction_status": "unsupported_scanned_pdf",
                "extraction_error": "Scanned or image-based PDF detected. No extractable text found. Text extraction requires OCR or a text-based PDF.",
                "profile_strength": evaluate_profile_strength({}),
            }

        # Contact Info strictly from resume (no fake fallbacks)
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}", text)
        phone = phone_match.group(0) if phone_match else ""

        linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_.-]+)", text, re.IGNORECASE)
        linkedin = linkedin_match.group(1) if linkedin_match else ""
        github_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_.-]+)", text, re.IGNORECASE)
        github = github_match.group(1) if github_match else ""

        # Portfolio search excluding email domain, linkedin, and github
        email_domain = email.split("@")[1].lower() if "@" in email else ""
        portfolio = ""
        portfolio_candidates = re.finditer(
            r"(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.(?:dev|me|io|app|tech|site|org|net|co\.uk|com)(?:/[a-zA-Z0-9_.-]+)*)",
            text,
            re.IGNORECASE,
        )
        for m in portfolio_candidates:
            cand_url = m.group(0).strip(" ,;()")
            domain = m.group(1).lower().split("/")[0]
            if any(ign in domain for ign in ["linkedin.com", "github.com", "gitlab.com", "medium.com", "twitter.com", "x.com"]):
                continue
            if email_domain and domain == email_domain:
                continue
            portfolio = cand_url
            break

        location = self._detect_location(text)
        candidate_name = self._detect_name(text, filename)

        sections = self._extract_sections(text)
        
        # Skill extraction: explicitly listed skills from skills section
        raw_skills_sec = sections.get("skills", "")
        section_skills = self.extract_skills(raw_skills_sec)
        known = {k.lower() for k in section_skills}
        for listed in self._extract_listed_skills(raw_skills_sec):
            normalized = self._normalize(listed)
            if normalized.lower() not in known:
                known.add(normalized.lower())
                section_skills.append(normalized)

        explicit_skills = sorted(section_skills)
        skill_evidence: Dict[str, List[str]] = {}
        for s in explicit_skills:
            skill_evidence.setdefault(s, []).append("skills")

        # Inferred skills: extract concrete technical skills from experience, projects, internships, education, certifications
        NON_TECHNICAL_WORDS = {
            "research", "reporting", "forecasting", "operations", "analysis", "management",
            "communication", "leadership", "organization", "strategy", "collaboration",
            "coordination", "planning", "monitoring", "presentation", "training"
        }
        inferred_skills_list = []
        for sec_name in ("experience", "projects", "internships", "education", "certifications", "summary"):
            sec_text = sections.get(sec_name, "")
            if not sec_text:
                continue
            found_in_sec = self.extract_skills(sec_text)
            for s in found_in_sec:
                if s.lower() in NON_TECHNICAL_WORDS:
                    continue
                if sec_name not in skill_evidence.setdefault(s, []):
                    skill_evidence[s].append(sec_name)
                if s.lower() not in known:
                    known.add(s.lower())
                    inferred_skills_list.append(s)

        inferred_skills = sorted(inferred_skills_list)
        all_skills = sorted(list(dict.fromkeys(explicit_skills + inferred_skills)))

        # Explicitly listed skills are exposed in parsed["skills"]
        skills = explicit_skills

        # Group by category (covering all evidenced skills)
        categorized: Dict[str, List[str]] = {}
        skill_pool = skills if skills else all_skills
        for cat, cat_skills in SKILL_TAXONOMY.items():
            cat_lower = {s.lower() for s in cat_skills}
            matches = [s for s in skill_pool if s.lower() in cat_lower]
            if matches:
                categorized[cat] = matches
        uncategorized = [s for s in skill_pool if not any(s in m for m in categorized.values())]
        if uncategorized:
            categorized["Other Skills"] = uncategorized

        # Experience & Seniority
        years, seniority = self._detect_experience(text)

        # Extract structured sections
        # Internships listed under "Experience" (title says intern/placement) get their own
        # section, and repeated records are merged, so nothing is double-counted or lost.
        experience, internships = split_internships(
            self._parse_experience(sections.get("experience", "")),
            self._parse_experience(sections.get("internships", "")),
        )
        # Dated full-time roles are better evidence than any "N years" phrase in the text
        # (which can come from a project or degree). Internships never count as years.
        dated_years = full_time_years(experience)
        if dated_years > 0:
            years = int(dated_years)
        elif internships and not experience:
            years = 0  # only internships: a fresher, whatever "N years" appears in the text
        career_level = "experienced" if years >= 1 else "fresher"
        target_roles = self._detect_roles(text, experience + internships)
        education = dedupe_entries(self._parse_education(sections.get("education", "")), "education")
        projects = dedupe_entries(self._parse_projects(sections.get("projects", "")), "projects")
        publications = dedupe_entries(self._parse_publications(sections.get("publications", "")), "publications")
        achievements = dedupe_entries(self._parse_achievements(sections.get("achievements", "")), "achievements")
        certifications = dedupe_entries(self._parse_certifications(sections.get("certifications", "")), "certifications")

        # Only use a summary the résumé actually contains; never paste raw text in.
        summary = sections.get("summary", "").strip() or self._preamble_summary(sections.get("preamble", ""))

        result: Dict[str, Any] = {
            "filename": filename,
            "raw_text": text[:20000],
            "candidate_name": candidate_name,
            "personal_info": {
                "name": candidate_name,
                "email": email,
                "phone": phone,
                "location": location,
                "linkedin": linkedin,
                "github": github,
                "portfolio": portfolio,
            },
            "email": email,
            "phone": phone,
            "location": location,
            "linkedin": linkedin,
            "github": github,
            "portfolio": portfolio,
            "skills": skills,
            "inferred_skills": inferred_skills,
            "all_skills": all_skills,
            "skill_evidence": skill_evidence,
            "categorized_skills": categorized,
            "total_skills": len(skills) if skills else len(all_skills),
            "years_of_experience": years,
            "career_level": career_level,
            "seniority_level": seniority,
            "target_roles": target_roles,
            "summary": summary,
            "professional_summary": summary,
            "experience": experience,
            "internships": internships,
            "education": education,
            "projects": projects,
            "publications": publications,
            "certifications": certifications,
            "achievements": achievements,
        }

        # Calculate profile strength score & recommendations
        result["profile_strength"] = evaluate_profile_strength(result)
        return result

    def extract_skills(self, text: str) -> List[str]:
        if not text:
            return []
        # Job descriptions are re-scanned on every upload; cache so only new text pays the cost.
        return list(_extract_skills_cached(self, text))

    def _extract_skills_uncached(self, text: str) -> Tuple[str, ...]:
        found: Set[str] = set()
        lower_text = f" {text.lower()} "

        # Special symbols regex
        special = {
            "c++": r"(?:\b|\s)c\+\+(?:\b|\s|,|\.)",
            "c#": r"(?:\b|\s)c#(?:\b|\s|,|\.)",
            ".net": r"(?:\b|\s)\.net(?:\b|\s|,|\.)",
            "node.js": r"(?:\b|\s)node(?:\.js)?(?:\b|\s|,|\.)",
            "react.js": r"(?:\b|\s)react(?:\.js)?(?:\b|\s|,|\.)",
            "ci/cd": r"(?:\b|\s)ci\/cd(?:\b|\s|,|\.)"
        }
        for sk, pat in special.items():
            literal = sk.split(".")[0] if sk.endswith(".js") else sk
            if literal in lower_text and re.search(pat, lower_text):
                found.add(self._normalize(sk))

        # Standard canonical check
        for canonical in _SKILL_INDEX.find(lower_text):
            found.add(self._normalize(canonical))

        return tuple(sorted(found))

    def _normalize(self, skill: str) -> str:
        cleaned = skill.strip().lower()
        if cleaned in SKILL_ALIASES:
            return SKILL_ALIASES[cleaned]
        return _CANONICAL_BY_LOWER.get(cleaned, skill.strip())

    def _detect_location(self, text: str) -> str:
        """Detect candidate location from header/contact section."""
        lines = [line.strip() for line in text.split("\n")[:15] if line.strip()]
        for line in lines:
            m = re.match(r"^(?:location|address|city|residence)\s*[:\-]\s*(.+)$", line, re.I)
            if m:
                return m.group(1).strip()
        uk_postcode = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
        city_country = re.compile(
            r"\b([A-Za-z\s.-]+,\s*(?:United Kingdom|UK|England|Scotland|Wales|Northern Ireland|Ireland|London|Manchester|Birmingham|Leeds|Glasgow|Edinburgh|Bristol|Cambridge|Oxford|USA|United States|Germany|France|Canada|[A-Z]{2}))\b",
            re.I,
        )
        for line in lines:
            if "@" in line or "http" in line or "github.com" in line or "linkedin.com" in line:
                parts = [p.strip() for p in re.split(r"[|•·\t]", line)]
                for part in parts:
                    if "@" in part or "http" in part or "github" in part or "linkedin" in part:
                        continue
                    if re.search(r"\d{3,}", part) and not uk_postcode.search(part):
                        continue
                    m = city_country.search(part)
                    if m:
                        return m.group(1).strip()
                    if uk_postcode.search(part) or ("," in part and 4 <= len(part) <= 50):
                        if not any(k in part.lower() for k in ["engineer", "developer", "resume", "cv", "experience"]):
                            return part.strip(" ,|-")
            else:
                m = city_country.search(line)
                if m:
                    return m.group(1).strip()
        return ""

    _NAME_WORD_PAT = re.compile(r"^[A-Za-zÀ-ÿ]+(?:[-'.][A-Za-zÀ-ÿ]+)*\.?$")

    def _detect_name(self, text: str, filename: str) -> str:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[:5]:
            words = line.split()
            if 2 <= len(words) <= 4 and all(self._NAME_WORD_PAT.match(w) for w in words):
                if line.lower() not in ["resume", "curriculum vitae", "contact information", "personal details", "profile"]:
                    return line
        return ""

    def _detect_experience(self, text: str) -> tuple[int, str]:
        matches = re.findall(r"(\d+)\+?\s*(?:years|yrs)(?:\s*of)?\s*(?:experience)?", text, re.IGNORECASE)
        years = 0
        if matches:
            nums = [int(m) for m in matches if int(m) < 40]
            if nums:
                years = max(nums)

        lower = text.lower()
        # Word boundaries so "Lead Generation" / "middle" don't read as seniority.
        is_lead = re.search(r"\blead\b(?!\s+(?:generation|gen|qualification|scoring|management|nurturing))", lower)
        if "principal" in lower or "director" in lower:
            seniority = "Principal / Lead"
        elif re.search(r"\bsenior\b", lower) or years >= 5:
            seniority = "Senior"
        elif is_lead:
            seniority = "Lead"
        elif re.search(r"\bmid(?:-level)?\b", lower) or (2 <= years < 5):
            seniority = "Mid-Level"
        elif "junior" in lower or re.search(r"\bintern(?:ship)?\b", lower) or (matches and years < 2):
            seniority = "Junior / Entry"
        else:
            # No stated years and no seniority keyword: don't assume a level.
            seniority = "Unknown"

        return years, seniority

    _SOFTWARE_ROLES = [
        "Full Stack Engineer", "Software Engineer", "Frontend Engineer", "Backend Engineer",
        "DevOps Engineer", "Cloud Engineer", "Data Scientist", "Machine Learning Engineer",
        "AI Engineer", "Data Engineer", "Site Reliability Engineer",
    ]
    # Single-word phrases only count as a role when they name a person (teacher, nurse, ...).
    _AGENT_NOUN = re.compile(r"(?:er|or|ist|ant|ian)$")

    def _detect_roles(self, text: str, experience: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        lower = text.lower()

        def present(phrase: str) -> bool:
            return re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])", lower) is not None

        detected = [r for r in self._SOFTWARE_ROLES if r.lower() in lower]
        for role, phrases in catalog_roles().items():
            if role in detected:
                continue
            if present(role) or any(
                present(p) for p in phrases
                if " " in p or (len(p) >= 6 and self._AGENT_NOUN.search(p))
            ):
                detected.append(role)

        # "Sales Executive" etc. imply the broader sales roles employers also post.
        if "Sales Executive" in detected:
            for extra in ("Account Executive", "Business Development Representative"):
                if extra not in detected:
                    detected.append(extra)

        # Nothing recognised: fall back to the job titles the résumé itself lists.
        if not detected and experience:
            for entry in experience:
                title = (entry.get("title") or "").strip()
                if 2 < len(title) <= 60 and title not in detected:
                    detected.append(title)
                if len(detected) >= 3:
                    break
        return detected

    def _extract_listed_skills(self, skills_section: str) -> List[str]:
        """Skills the résumé lists itself, so professions outside the catalog still count."""
        found: List[str] = []
        # Re-join wrapped lines: a line without its own "Category:" continues the previous
        # categorised line, and an unclosed "(" always continues onto the next line.
        logical: List[str] = []
        for raw in (skills_section or "").split("\n"):
            line = re.sub(r"^[\s\-\*•·▪●\d\.\)]+", "", raw).strip()
            if not line:
                continue
            prev = logical[-1] if logical else ""
            if prev and (prev.count("(") > prev.count(")") or (":" in prev and ":" not in line)):
                logical[-1] = f"{prev} {line}"
            else:
                logical.append(line)
        for line in logical:
            if ":" in line:
                line = line.split(":", 1)[1]
            for item in self._split_top_level(line):
                item = re.sub(r"\s*\([^)]*\)", "", item)  # "Linux (RHEL, Ubuntu)" -> "Linux"
                item = re.sub(r"\s+\d{4}(?:\s*/\s*\d{4})*$", "", item)  # "Windows Server 2019/2022"
                item = item.strip(" .-–")
                words = item.split()
                if 2 <= len(item) <= 40 and 1 <= len(words) <= 4 and not re.search(r"\d{4}|@|http", item):
                    found.append(item)
        return found

    @staticmethod
    def _split_top_level(line: str) -> List[str]:
        """Split a skills line on , ; | • and " / " or " & " - never inside parentheses."""
        items, depth, current = [], 0, ""
        i = 0
        while i < len(line):
            ch = line[i]
            depth += (ch == "(") - (ch == ")")
            if depth <= 0:
                if ch in ",;|•·":
                    items.append(current); current = ""; i += 1; continue
                rest = line[i:]
                sep = re.match(r"\s+/\s+|\s{2,}|\s+&\s+(?=[A-Z])", rest)
                if sep:
                    items.append(current); current = ""; i += sep.end(); continue
            current += ch
            i += 1
        items.append(current)
        return items

    # ---------------- Section Parsers ----------------

    def _extract_sections(self, text: str) -> Dict[str, str]:
        """Segments resume text into named sections based on header patterns."""
        headers = {
            "summary": r"(?:professional\s+summary|executive\s+summary|professional\s+profile|personal\s+profile|career\s+(?:summary|profile|objective|overview)|profile\s+summary|objective|summary|profile|about\s+me|career\s+highlights|overview)",
            "skills": r"(?:(?:key|core|technical|top|relevant|professional|it|digital|transferable|hard|soft|additional)\s+(?:technical\s+)?skills(?:\s*(?:&|and)\s*(?:tools|technologies|competencies|expertise))?|areas\s+of\s+expertise|skills\s*(?:&|and)\s*(?:technologies|tools|competencies|expertise|abilities)|core\s+competencies|technical\s+background|technical\s+expertise|toolbox|tools\s*(?:&|and)?\s*technologies|tech(?:nology)?\s+stack|skill\s*set|competencies|skills|tools)",
            "experience": r"(?:work\s+experience|professional\s+experience|employment\s+history|work\s+history|experience|relevant\s+experience|career\s+history|work\s+background)",
            "internships": r"(?:internships?\s*(?:experience)?|intern\s+experience|internships?\s*&?\s*experience|industrial\s+placements?|practicum)",
            "education": r"(?:education|academic\s+background|academic\s+qualifications|qualifications|academic\s+history)",
            "projects": r"(?:(?:technical|academic|personal|key|portfolio|course|selected)\s+projects|projects|software\s+projects)",
            "publications": r"(?:(?:research|selected)\s+publications?|publications?|research\s+papers?|papers?\s+published|articles)",
            "certifications": r"(?:certifications?\s*(?:&|and)\s*licenses|certifications?|licenses|certificates|professional\s+certifications?|credentials)",
            "achievements": r"(?:(?:achievements?|awards?|honou?rs?|accomplishments?)\s*(?:&|and)\s*(?:awards?|leadership|activities|honou?rs?|achievements?)|achievements?|accomplishments?|honou?rs?|awards?|key\s+achievements?|leadership(?:\s*(?:&|and)\s*activities)?|extra[- ]?curricular\s+activities)",
        }

        current_section = "preamble"
        section_lines: Dict[str, List[str]] = {k: [] for k in headers}
        section_lines["preamble"] = []

        lines = text.split("\n")
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                section_lines[current_section].append("")
                continue

            matched_sec = None
            inline_content = ""
            clean_heading = re.sub(r"^[\s#\-\*•:]+|[\s#\-\*•:]+$", "", trimmed)
            clean_heading = re.sub(r"\s+", " ", clean_heading)
            for sec_key, label_pattern in headers.items():
                if re.fullmatch(rf"(?:{label_pattern})", clean_heading, re.I):
                    matched_sec = sec_key
                    break
                inline_match = re.match(
                    rf"^(?:{label_pattern})\s*[:\-–—]\s*(.+)$",
                    clean_heading,
                    re.I,
                )
                if inline_match:
                    matched_sec = sec_key
                    inline_content = inline_match.group(1).strip()
                    break

            if matched_sec:
                current_section = matched_sec
                if inline_content:
                    section_lines[current_section].append(inline_content)
            else:
                section_lines[current_section].append(trimmed)

        return {k: "\n".join(v) for k, v in section_lines.items()}

    def _parse_experience(self, text: str) -> List[Dict[str, Any]]:
        """Parses job experience entries from experience section text."""
        if not text:
            return []

        entries = []
        current: Optional[Dict[str, Any]] = None

        range_date_pat = re.compile(
            r"(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?\b(?:19|20)\d{2}\s*(?:-|–|—|to)\s*"
            r"(?:(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2}|Present|Current)|"
            r"\b\d{1,2}/(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:\d{1,2}/(?:19|20)\d{2}|Present|Current)\b|"
            r"\b(?:19|20)\d{2}/\d{1,2}\s*(?:-|–|—|to)\s*(?:(?:19|20)\d{2}/\d{1,2}|Present|Current)\b",
            re.I,
        )
        single_date_pat = re.compile(
            r"\b(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?\b(?:19|20)\d{2}\b|"
            r"\b(?:Summer|Winter|Spring|Fall|Autumn)\s+(?:19|20)\d{2}\b",
            re.I,
        )
        TITLE_HINTS = re.compile(
            r"\b(?:intern|internship|engineer|developer|designer|manager|lead|architect|analyst|"
            r"consultant|admin|administrator|trainee|apprentice|specialist|officer|associate|programmer)\b",
            re.I,
        )
        COMPANY_HINTS = re.compile(
            r"\b(?:pvt|ltd|limited|technologies|inc|corp|corporation|solutions|services|systems|"
            r"labs|llc|gmbh|co|infotech|consulting|enterprises)\b",
            re.I,
        )
        LOCATION_LINE_PAT = re.compile(r"^[A-Za-z\s.\-]+,\s*[A-Za-z\s.\-]+$")

        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            is_bullet = bool(re.match(r"^[\s\-\*•\d\.\)]+", line_str))
            clean_line = re.sub(r"^[\s\-\*•\d\.\)]+", "", line_str).strip()

            d_match = range_date_pat.search(line_str) or single_date_pat.search(line_str)
            has_separator = ("|" in line_str or " - " in line_str or " – " in line_str or " — " in line_str or " at " in line_str.lower())

            if (d_match or has_separator) and not is_bullet and len(line_str) < 140:
                if current:
                    entries.append(current)

                dates = d_match.group(0).strip("()") if d_match else ""
                remainder = line_str[:d_match.start()] + line_str[d_match.end():] if d_match else line_str
                remainder = re.sub(r"[\(\)\[\]]", "", remainder).strip(" -|")

                parts = [p.strip() for p in re.split(r"\s*(?:\|| - | – | — |\s+at\s+)\s*", remainder) if p.strip()]
                # "Software Engineer, Monzo, London" uses commas instead of | or -.
                if len(parts) == 1 and "," in parts[0]:
                    comma_parts = [p.strip() for p in parts[0].split(",") if p.strip()]
                    if 2 <= len(comma_parts) <= 4:
                        parts = comma_parts
                location = ", ".join(parts[2:]) if len(parts) >= 3 else ""
                if len(parts) >= 2:
                    if TITLE_HINTS.search(parts[1]) or COMPANY_HINTS.search(parts[0]):
                        title = parts[1]
                        company = parts[0]
                    else:
                        title = parts[0]
                        company = parts[1]
                elif len(parts) == 1:
                    title = parts[0]
                    company = ""
                else:
                    title = ""
                    company = ""

                current = {
                    "title": title.strip("()[] "),
                    "company": company.strip("()[] "),
                    "organization": company.strip("()[] "),
                    "dates": dates.strip(),
                    "location": location.strip("()[] ,"),
                    "description": "",
                    "bullets": [],
                }
            elif current:
                if is_bullet:
                    current["bullets"].append(clean_line)
                elif not current["location"] and LOCATION_LINE_PAT.match(clean_line) and len(clean_line) < 60:
                    current["location"] = clean_line
                elif current["bullets"]:
                    # Continuation of the previous wrapped bullet line
                    current["bullets"][-1] = self._join_wrapped(current["bullets"][-1], clean_line)
                else:
                    if not current["description"]:
                        current["description"] = clean_line
                    else:
                        current["bullets"].append(clean_line)

        if current:
            entries.append(current)

        return entries

    def _parse_education(self, text: str) -> List[Dict[str, Any]]:
        """Parses education entries from education section text."""
        if not text:
            return []

        entries = []
        deg_pat = re.compile(r"\b(?:B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|B\.?Tech|M\.?Tech|Ph\.?D\.?|Bachelor|Master|Doctorate|Diploma|Associate)\b", re.I)
        month = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+"
        year_pat = re.compile(
            rf"\(?\b(?:{month})?(?:19|20)\d{{2}}(?:\s*(?:-|–|—|to)\s*(?:(?:{month})?(?:19|20)\d{{2}}|Present|Current))?\b\)?",
            re.I,
        )
        squash = lambda value: re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())  # noqa: E731

        inst_pat = re.compile(r"\b(?:university|college|institute|school|academy|polytechnic|IIT|NIT)\b", re.I)
        grade_pat = re.compile(r"\b(?:c?gpa|grade|percentage|honou?rs|first\s+class|distinction)\b|\d+(?:\.\d+)?\s*(?:/\s*\d+|%)", re.I)

        def split_header(line_str: str) -> Tuple[str, str, str, str, List[str]]:
            """Split an education line into (degree, institution, dates, location, grade notes).

            Handles 'Degree | Institution | Sep 2022 - Jun 2025',
            'Dr. N.G.P. Institute of Technology, Coimbatore | Expected May 2028' and
            'B.Tech, Information Technology | CGPA: 8.1/10'.
            """
            y_match = year_pat.search(line_str)
            dates = y_match.group(0).strip("() ") if y_match else ""
            remainder = (line_str[:y_match.start()] + line_str[y_match.end():]) if y_match else line_str
            remainder = re.sub(r"\b(?:expected(?:\s+graduation)?|graduat(?:ed|ion|ing))\s*:?", "", remainder, flags=re.I)
            parts = [p.strip(" |,-–—():") for p in re.split(r"\s*(?:\||\s[-–—]\s)\s*", remainder) if p.strip(" |,-–—():")]
            degree = institution = location = ""
            notes: List[str] = []
            for part in parts:
                if grade_pat.search(part) and not deg_pat.search(part) and not inst_pat.search(part):
                    notes.append(part)
                elif inst_pat.search(part) and not institution:
                    institution = part
                    # "Institute of Technology, Coimbatore": a trailing short place name is the location.
                    head, _, tail = part.rpartition(",")
                    if head and tail.strip() and len(tail.split()) <= 3 and not inst_pat.search(tail):
                        institution, location = head.strip(), tail.strip()
                elif not degree:
                    degree = part
                elif not institution:
                    institution = part
            return degree, institution, dates, location, notes

        lines = text.split("\n")
        current: Optional[Dict[str, Any]] = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            is_bullet = bool(re.match(r"^[\s\-\*•]+", line_str))
            clean_line = re.sub(r"^[\s\-\*•]+", "", line_str).strip()

            if (deg_pat.search(line_str) or inst_pat.search(line_str)) and not is_bullet:
                deg, inst, dates, location, notes = split_header(line_str)

                def fill(entry: Dict[str, Any]) -> None:
                    if inst and not entry.get("institution"):
                        entry["institution"] = entry["organization"] = inst
                    if deg and not entry.get("degree"):
                        entry["degree"] = entry["title"] = deg
                    if dates and not entry.get("dates"):
                        entry["dates"] = dates
                    if location and not entry.get("location"):
                        entry["location"] = location
                    for note in notes:
                        if squash(note) not in {squash(b) for b in entry["bullets"]}:
                            entry["bullets"].append(note)

                if current:
                    same_degree = squash(deg) and squash(deg) == squash(current.get("degree"))
                    same_inst = not inst or not current.get("institution") or squash(inst) == squash(current.get("institution"))
                    if same_degree and same_inst:
                        # The same degree written again (repeated block or a wrapped line): merge, never duplicate.
                        fill(current)
                        continue
                    if not inst and not dates and squash(current.get("degree")) and squash(deg).startswith(squash(current.get("degree"))):
                        # A longer form of the degree on its own line: keep the fuller title.
                        current["degree"] = current["title"] = deg
                        continue
                    # Two-line layout: "Institution | Dates" then "Degree | Grade" belong together.
                    completes = (deg and not current.get("degree") and not inst) or (
                        inst and not current.get("institution") and not deg
                    )
                    if completes:
                        fill(current)
                        continue
                    entries.append(current)

                current = {"degree": "", "title": "", "institution": "", "organization": "",
                           "dates": "", "location": "", "bullets": []}
                fill(current)
            elif current:
                if is_bullet:
                    degree_words = re.sub(r"[^a-z0-9]+", "", current.get("degree", "").casefold())
                    bullet_words = re.sub(r"[^a-z0-9]+", "", clean_line.casefold())
                    if bullet_words and bullet_words not in degree_words:
                        current["bullets"].append(clean_line)
                elif not current.get("institution"):
                    if re.match(r"^(?:in|of|with|for)\b", clean_line, re.I):
                        current["degree"] = f"{current['degree']} {clean_line}".strip()
                        current["title"] = current["degree"]
                    else:
                        current["institution"] = clean_line
                        current["organization"] = clean_line
                else:
                    current["bullets"].append(clean_line)

        if current:
            entries.append(current)

        return entries

    def _parse_projects(self, text: str) -> List[Dict[str, Any]]:
        """Parse project entries without mistaking short description lines for titles."""
        return self._parse_named_entries(text, "projects")

    def _parse_publications(self, text: str) -> List[Dict[str, Any]]:
        """Parse publication citations separately from project entries."""
        return self._parse_named_entries(text, "publications")

    @staticmethod
    def _looks_like_entry_title(text: str) -> bool:
        candidate = text.strip()
        words = re.findall(r"[A-Za-z0-9]+", candidate)
        return (
            2 <= len(candidate) <= 100
            and len(words) <= 14
            and not re.search(r"[.!?;]$", candidate)
            and bool(words)
            and all(word.isupper() or word[0].isupper() for word in words)
        )

    @staticmethod
    def _split_entry_heading(text: str) -> Optional[Tuple[str, str]]:
        for separator in (" | ", " — ", " – ", " - "):
            if separator in text:
                title, details = text.split(separator, 1)
                if title.strip() and details.strip():
                    return title.strip(), details.strip()
        if ":" in text:
            title, details = text.split(":", 1)
            if ResumeService._looks_like_entry_title(title) and details.strip():
                return title.strip(), details.strip()
        # "Fraud Dashboard, Personal project, 2023": only with a year, so a plain list such as
        # "React, FastAPI, PostgreSQL" is not mistaken for a heading.
        if "," in text:
            title, details = text.split(",", 1)
            if ResumeService._looks_like_entry_title(title) and re.search(r"\b(?:19|20)\d{2}\b", details):
                return title.strip(), details.strip(" ,")
        return None

    @staticmethod
    def _preamble_summary(preamble: str) -> str:
        """An unheaded profile paragraph under the name and contact lines.

        Many resumes open with a summary paragraph but no "Summary" heading. Only prose lines
        (several words, no contact details or separators) are taken, exactly as written.
        """
        prose: List[str] = []
        for line in (preamble or "").split("\n"):
            line = line.strip()
            is_prose = (
                len(line.split()) >= 6
                and not re.search(r"@|https?://|www\.|linkedin\.com|github\.com|\+?\d[\d\s()-]{7,}|\s\|\s", line, re.I)
            )
            if is_prose or (prose and line and not re.search(r"@|\|", line)):
                prose.append(line)
            elif prose and not line:
                break
        text = re.sub(r"\s+", " ", " ".join(prose)).strip()
        return text if len(text) >= 60 else ""

    @staticmethod
    def _join_wrapped(previous: str, continuation: str) -> str:
        """Join the second line of a wrapped bullet; 'in-' + 'formation' becomes 'information'."""
        previous = previous.rstrip()
        if previous.endswith("-") and continuation[:1].islower():
            return previous[:-1] + continuation
        return previous + " " + continuation

    def _parse_named_entries(self, text: str, section: str) -> List[Dict[str, Any]]:
        if not text:
            return []

        entries: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        last_was_bullet = False

        def finish() -> None:
            if current and any(
                current.get(key)
                for key in ("title", "organization", "description", "bullets")
            ):
                entries.append({k: v for k, v in current.items() if not k.startswith("_")})

        def start(title: str = "", organization: str = "", description: str = "") -> Dict[str, Any]:
            if section == "publications" and title and not organization:
                # "...Retail ExperienceICECA 2025, Nov 2025": PDFs often glue the venue to the title.
                glued = re.match(r"^(.*[a-z)])([A-Z]{2,}[A-Za-z0-9&-]*(?:\s+[A-Za-z0-9&-]+)*?\s+(?:19|20)\d{2})(?:\s*,\s*(.+))?$", title)
                if glued:
                    title, organization = glued.group(1).strip(), glued.group(2).strip()
                    if glued.group(3):
                        return {"title": title, "name": title, "organization": organization,
                                "dates": glued.group(3).strip(), "description": description, "bullets": []}
            dates = self._extract_year(organization)
            if dates and section == "projects":
                # "Personal project, 2023": the year goes to dates, not the organisation line.
                # A bare year ("Title | 2024") leaves no organisation at all.
                organization = re.sub(r"[,\s(|–-]*\b" + re.escape(dates) + r"\b[)\s]*$", "", organization).strip(" ,|–-")
            return {
                "title": title,
                "name": title,
                "organization": organization,
                "dates": dates,
                "description": description,
                "bullets": [],
            }

        project_date_pattern = re.compile(
            r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?"
            r"(?:19|20)\d{2}"
            r"(?:\s*(?:-|–|—|to)\s*"
            r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?"
            r"(?:(?:19|20)\d{2}|Present|Current))?",
            re.I,
        )

        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            bullet_match = re.match(r"^(?:[-*•·▪●]+|\d+[.)])\s*", line_str)
            is_bullet = bool(bullet_match)
            clean_line = line_str[bullet_match.end():].strip() if bullet_match else line_str
            if not clean_line:
                continue

            if is_bullet:
                # A bulleted list of papers: each bullet is a publication. Bullets under a
                # publication's own title line are details of that paper.
                if section == "publications" and current and not current.get("_titled"):
                    finish()
                    current = None
                if current is None:
                    current = start(
                        title=clean_line if section == "publications" else "",
                        description="" if section == "publications" else "",
                    )
                    if section == "publications":
                        last_was_bullet = True
                        continue
                current["bullets"].append(clean_line)
                last_was_bullet = True
                continue

            if last_was_bullet and current and current.get("bullets") and (
                clean_line[:1].islower() or not self._looks_like_entry_title(clean_line)
            ) and self._split_entry_heading(clean_line) is None:
                # The second line of a wrapped bullet, not a description of its own.
                current["bullets"][-1] = self._join_wrapped(current["bullets"][-1], clean_line)
                continue
            last_was_bullet = False

            if (
                section == "projects"
                and current
                and project_date_pattern.fullmatch(clean_line)
            ):
                current["dates"] = clean_line
                continue

            split_heading = self._split_entry_heading(clean_line)
            title_words = re.findall(r"[A-Za-z0-9]+", clean_line)
            has_project_body = bool(
                current
                and (
                    current.get("bullets")
                    or re.search(r"[.!?](?:\s|$)", current.get("description") or "")
                )
            )
            is_heading = split_heading is not None or (
                self._looks_like_entry_title(clean_line)
                and (
                    section == "publications"
                    or section != "projects"
                    and (not current or bool(current.get("description") or current.get("bullets")))
                    or section == "projects"
                    and (not current or has_project_body)
                )
                and (section == "publications" or len(title_words) > 1 or current is None)
            )
            if current is None:
                if split_heading:
                    title, organization = split_heading
                    current = start(title, organization)
                    current["_titled"] = True
                elif self._looks_like_entry_title(clean_line) or section == "publications":
                    current = start(title=clean_line)
                    current["_titled"] = True
                else:
                    current = start(description=clean_line)
            elif is_heading:
                finish()
                if split_heading:
                    title, organization = split_heading
                    current = start(title, organization)
                else:
                    current = start(title=clean_line)
                current["_titled"] = True
            else:
                if current.get("description"):
                    current["description"] += " " + clean_line
                elif not current.get("title"):
                    current["description"] = clean_line
                else:
                    current["description"] = clean_line

        finish()
        return entries

    @staticmethod
    def _extract_year(text: str) -> str:
        match = re.search(r"\b(?:19|20)\d{2}\b", text or "")
        return match.group(0) if match else ""

    @staticmethod
    def _parse_achievements(text: str) -> List[Dict[str, Any]]:
        if not text:
            return []
        entries: List[Dict[str, Any]] = []
        uses_bullets = bool(re.search(r"^\s*(?:[-*•·▪●]+|\d+[.)])", text, re.M))
        for line in text.split("\n"):
            line = line.strip()
            bullet_match = re.match(r"^(?:[-*•·▪●]+|\d+[.)])\s*", line)
            cleaned = line[bullet_match.end():].strip() if bullet_match else line
            if not cleaned:
                continue
            if uses_bullets and not bullet_match and entries:
                # A wrapped line continues the previous bullet; it is not a new achievement.
                entries[-1]["title"] = entries[-1]["name"] = f"{entries[-1]['title']} {cleaned}"
                continue
            entries.append({"title": cleaned, "name": cleaned, "dates": ""})
        return entries

    def _parse_certifications(self, text: str) -> List[Dict[str, Any]]:
        """Parses certification entries from certifications section text."""
        if not text:
            return []

        entries: List[Dict[str, Any]] = []
        # A year only counts as the date when it ends the line ("..., 2023" / "| 2023"), not when it
        # is part of the course name ("Data Analytics Masters 2026: ...").
        trailing_year = re.compile(r"[\s,|(–-]*\(?\b((?:19|20)\d{2})\)?\s*$")
        uses_bullets = bool(re.search(r"^\s*[-*•·▪●]", text, re.M))

        for line in text.split("\n"):
            line_str = line.strip()
            if not line_str:
                continue
            is_bullet = bool(re.match(r"^[\s\-\*•·▪●]+", line_str))
            clean_line = re.sub(r"^[\s\-\*•·▪●]+", "", line_str).strip()
            if uses_bullets and not is_bullet and entries:
                # Wrapped continuation of the previous certification line.
                entries[-1]["name"] = entries[-1]["title"] = f"{entries[-1]['name']} {clean_line}"
                continue
            dates = ""
            y_m = trailing_year.search(clean_line)
            if y_m:
                dates = y_m.group(1)
                clean_line = clean_line[:y_m.start()].strip()

            name = clean_line
            issuer = ""
            # "Course name – Udemy" / "Course | Coursera": the last short segment is the issuer.
            pieces = [p.strip() for p in re.split(r"\s+[-–—]\s+|\s*\|\s*", clean_line) if p.strip()]
            if len(pieces) >= 2 and len(pieces[-1].split()) <= 6:
                name = " – ".join(pieces[:-1])
                issuer = pieces[-1]

            entries.append({
                "name": name,
                "title": name,
                "issuer": issuer,
                "dates": dates,
            })

        return entries


@lru_cache(maxsize=8192)
def _extract_skills_cached(service: "ResumeService", text: str) -> Tuple[str, ...]:
    return service._extract_skills_uncached(text)

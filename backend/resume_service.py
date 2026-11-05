"""Parse uploaded resumes and extract structured candidate profile information.

Handles PDF/DOCX text extraction, section classification, skill normalization,
and conversion to the profile shape used by matching and editing features.
"""
import os
import re
import io
from typing import Dict, List, Any, Set, Optional, Tuple
import pypdf
import docx

try:
    from .profile_strength_service import evaluate_profile_strength
except ImportError:
    from profile_strength_service import evaluate_profile_strength

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
        "Snowflake", "Databricks", "Apache Spark", "Airflow", "dbt", "LLM",
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
from .skill_matching import text_has_skill
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
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
        return "\n".join(pages_text)

    def _read_docx(self, content_bytes: bytes) -> str:
        doc = docx.Document(io.BytesIO(content_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text])

    def analyze_text(self, text: str, filename: str = "Uploaded_Resume.pdf") -> Dict[str, Any]:

        # Contact Info strictly from resume (no fake fallbacks)
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        email = email_match.group(0) if email_match else ""

        phone_match = re.search(r"(\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,5}", text)
        phone = phone_match.group(0) if phone_match else ""

        linkedin_match = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9_.-]+)", text, re.IGNORECASE)
        github_match = re.search(r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_.-]+)", text, re.IGNORECASE)
        portfolio_match = re.search(r"(?:https?://)?([a-zA-Z0-9-]+\.)+(?:com|io|dev|app|me|net|org)(?:/[^\s]*)?", text, re.IGNORECASE)

        # Name heuristic
        candidate_name = self._detect_name(text, filename)

        sections = self._extract_sections(text)
        # A skill mention in a project or publication is not necessarily a listed skill.
        skills = self.extract_skills(sections.get("skills", ""))
        known = {k.lower() for k in skills}
        for listed in self._extract_listed_skills(sections.get("skills", "")):
            normalized = self._normalize(listed)
            if normalized.lower() not in known:
                known.add(normalized.lower())
                skills.append(normalized)
        skills = sorted(skills)

        # Group by category
        categorized: Dict[str, List[str]] = {}
        for cat, cat_skills in SKILL_TAXONOMY.items():
            cat_lower = {s.lower() for s in cat_skills}
            matches = [s for s in skills if s.lower() in cat_lower]
            if matches:
                categorized[cat] = matches
        uncategorized = [s for s in skills if not any(s in m for m in categorized.values())]
        if uncategorized:
            categorized["Other Skills"] = uncategorized

        # Experience & Seniority
        years, seniority = self._detect_experience(text)

        # Extract structured sections
        experience = self._parse_experience(sections.get("experience", ""))
        internships = self._parse_experience(sections.get("internships", ""))
        if not experience and internships:
            experience = list(internships)
        elif internships:
            exp_keys = {(e.get("title", "").lower(), (e.get("company") or e.get("organization") or "").lower()) for e in experience}
            for item in internships:
                key = (item.get("title", "").lower(), (item.get("company") or item.get("organization") or "").lower())
                if key not in exp_keys:
                    experience.append(item)
                    exp_keys.add(key)
        target_roles = self._detect_roles(text, experience)
        education = self._parse_education(sections.get("education", ""))
        projects = self._parse_projects(sections.get("projects", ""))
        publications = self._parse_publications(sections.get("publications", ""))
        achievements = self._parse_achievements(sections.get("achievements", ""))
        certifications = self._parse_certifications(sections.get("certifications", ""))

        # Only use a summary the résumé actually contains; never paste raw text in.
        summary = sections.get("summary", "").strip()

        result: Dict[str, Any] = {
            "filename": filename,
            "raw_text": text[:20000],
            "candidate_name": candidate_name,
            "email": email,
            "phone": phone,
            "linkedin": linkedin_match.group(1) if linkedin_match else "",
            "github": github_match.group(1) if github_match else "",
            "portfolio": portfolio_match.group(0) if portfolio_match else "",
            "skills": skills,
            "categorized_skills": categorized,
            "total_skills": len(skills),
            "years_of_experience": years,
            "seniority_level": seniority,
            "target_roles": target_roles,
            "summary": summary,
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
            if re.search(pat, lower_text):
                found.add(self._normalize(sk))

        # Standard canonical check
        for canonical in ALL_CANONICAL_SKILLS:
            if len(canonical) <= 2 and canonical not in ["Go", "R", "C"]:
                continue
            if text_has_skill(canonical, lower_text, loose=False):
                found.add(self._normalize(canonical))

        return sorted(list(found))

    def _normalize(self, skill: str) -> str:
        cleaned = skill.strip().lower()
        if cleaned in SKILL_ALIASES:
            return SKILL_ALIASES[cleaned]
        for canonical in ALL_CANONICAL_SKILLS:
            if canonical.lower() == cleaned:
                return canonical
        return skill.strip()

    def _detect_name(self, text: str, filename: str) -> str:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[:4]:
            words = line.split()
            if 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
                if line.lower() not in ["resume", "curriculum vitae", "contact information"]:
                    return line
        # No name detected in the document: leave it empty rather than guessing
        # from the filename or inventing a placeholder.
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
        for line in (skills_section or "").split("\n"):
            line = re.sub(r"^[\s\-\*•·▪●\d\.\)]+", "", line).strip()
            if ":" in line:
                line = line.split(":", 1)[1]
            for item in re.split(r"[,;|•·/]|\s{2,}|\s+&\s+(?=[A-Z])", line):
                item = item.strip(" .-–")
                words = item.split()
                if 2 <= len(item) <= 40 and 1 <= len(words) <= 4 and not re.search(r"\d{4}|@|http", item):
                    found.append(item)
        return found

    # ---------------- Section Parsers ----------------

    def _extract_sections(self, text: str) -> Dict[str, str]:
        """Segments resume text into named sections based on header patterns."""
        headers = {
            "summary": r"(?:professional\s+summary|executive\s+summary|professional\s+profile|career\s+(?:summary|profile|objective)|profile\s+summary|objective|summary|profile|about\s+me)",
            "skills": r"(?:key\s+skills|technical\s+skills|top\s+skills|areas\s+of\s+expertise|skills\s*(?:&|and)\s*technologies|core\s+competencies|skills)",
            "experience": r"(?:work\s+experience|professional\s+experience|employment\s+history|work\s+history|experience)",
            "internships": r"(?:internships?\s*(?:experience)?|intern\s+experience|internships?\s*&?\s*experience)",
            "education": r"(?:education|academic\s+background|qualifications)",
            "projects": r"(?:(?:technical|academic|personal|key|portfolio|course)\s+projects|projects)",
            "publications": r"(?:(?:research|selected)\s+publications?|publications?|research\s+papers?|papers?\s+published)",
            "certifications": r"(?:certifications?\s*(?:&|and)\s*licenses|certifications?|licenses|certificates)",
            "achievements": r"(?:achievements?\s*(?:&|and)\s*awards?|achievements?|accomplishments?|honors?\s*(?:&|and)\s*awards?|awards?)",
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
            r"(?:(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2}|Present|Current)",
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
            has_separator = ("|" in line_str or " - " in line_str or " — " in line_str or " at " in line_str.lower())

            if (d_match or has_separator) and not is_bullet and len(line_str) < 140:
                if current:
                    entries.append(current)

                dates = d_match.group(0).strip("()") if d_match else ""
                remainder = line_str[:d_match.start()] + line_str[d_match.end():] if d_match else line_str
                remainder = re.sub(r"[\(\)\[\]]", "", remainder).strip(" -|")

                parts = [p.strip() for p in re.split(r"\s*(?:\|| - | — |\s+at\s+)\s*", remainder) if p.strip()]
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
                    current["bullets"][-1] = current["bullets"][-1].rstrip() + " " + clean_line
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
        year_pat = re.compile(r"\b(?:19|20)\d{2}\s*(?:-|–|to)?\s*(?:(?:19|20)\d{2}|Present)?\b")

        lines = text.split("\n")
        current: Optional[Dict[str, Any]] = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            is_bullet = bool(re.match(r"^[\s\-\*•]+", line_str))
            clean_line = re.sub(r"^[\s\-\*•]+", "", line_str).strip()

            if (deg_pat.search(line_str) or "university" in line_str.lower() or "college" in line_str.lower()) and not is_bullet:
                if current:
                    entries.append(current)

                dates = ""
                y_match = year_pat.search(line_str)
                if y_match:
                    dates = y_match.group(0).strip("()")
                    remainder = line_str[:y_match.start()] + line_str[y_match.end():]
                else:
                    remainder = line_str

                if "|" in remainder:
                    parts = [p.strip() for p in remainder.split("|") if p.strip()]
                    deg = parts[0]
                    inst = parts[1] if len(parts) > 1 else ""
                elif " - " in remainder:
                    parts = [p.strip() for p in remainder.split(" - ") if p.strip()]
                    deg = parts[0]
                    inst = parts[1] if len(parts) > 1 else ""
                elif "," in remainder:
                    parts = [p.strip() for p in remainder.split(",") if p.strip()]
                    deg = parts[0]
                    inst = parts[1] if len(parts) > 1 else ""
                else:
                    deg = remainder.strip()
                    inst = ""

                current = {
                    "degree": deg.strip(),
                    "title": deg.strip(),
                    "institution": inst.strip(),
                    "organization": inst.strip(),
                    "dates": dates.strip(),
                    "bullets": [],
                }
            elif current:
                if is_bullet:
                    current["bullets"].append(clean_line)
                elif not current.get("institution"):
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

    def _parse_named_entries(self, text: str, section: str) -> List[Dict[str, Any]]:
        if not text:
            return []

        entries: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        def finish() -> None:
            if current and any(
                current.get(key)
                for key in ("title", "organization", "description", "bullets")
            ):
                entries.append(current.copy())

        def start(title: str = "", organization: str = "", description: str = "") -> Dict[str, Any]:
            dates = self._extract_year(organization)
            if dates and section == "projects":
                # "Personal project, 2023": the year goes to dates, not the organisation line.
                organization = re.sub(r"[,\s(|–-]*\b" + dates + r"\b[)\s]*$", "", organization).strip(" ,|") or organization
            return {
                "title": title,
                "name": title,
                "organization": organization,
                "dates": dates,
                "description": description,
                "bullets": [],
            }

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
                if section == "publications" and current:
                    finish()
                    current = None
                if current is None:
                    current = start(
                        title=clean_line if section == "publications" else "",
                        description="" if section == "publications" else "",
                    )
                if section != "publications":
                    current["bullets"].append(clean_line)
                continue

            split_heading = self._split_entry_heading(clean_line)
            is_heading = split_heading is not None or self._looks_like_entry_title(clean_line)
            if current is None:
                if split_heading:
                    title, organization = split_heading
                    current = start(title, organization)
                elif self._looks_like_entry_title(clean_line) or section == "publications":
                    current = start(title=clean_line)
                else:
                    current = start(description=clean_line)
            elif is_heading:
                finish()
                if split_heading:
                    title, organization = split_heading
                    current = start(title, organization)
                else:
                    current = start(title=clean_line)
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
        entries = []
        for line in text.split("\n"):
            line = line.strip()
            bullet_match = re.match(r"^(?:[-*•·▪●]+|\d+[.)])\s*", line)
            cleaned = line[bullet_match.end():].strip() if bullet_match else line
            if cleaned:
                entries.append({"title": cleaned, "name": cleaned, "dates": ""})
        return entries

    def _parse_certifications(self, text: str) -> List[Dict[str, Any]]:
        """Parses certification entries from certifications section text."""
        if not text:
            return []

        entries = []
        year_pat = re.compile(r"\b(?:19|20)\d{2}\b")

        for line in text.split("\n"):
            line_str = line.strip()
            if not line_str:
                continue
            clean_line = re.sub(r"^[\s\-\*•]+", "", line_str).strip()
            dates = ""
            y_m = year_pat.search(clean_line)
            if y_m:
                dates = y_m.group(0)

            name = clean_line
            issuer = ""
            if " - " in clean_line:
                parts = clean_line.split(" - ")
                name = parts[0].strip()
                issuer = parts[1].strip()
            elif "|" in clean_line:
                parts = clean_line.split("|")
                name = parts[0].strip()
                issuer = parts[1].strip()

            entries.append({
                "name": name,
                "title": name,
                "issuer": issuer,
                "dates": dates,
            })

        return entries

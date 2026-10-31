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
        pages_text = [page.extract_text() for page in reader.pages if page.extract_text()]
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

        # Skill Extraction: catalog skills found anywhere + skills the résumé lists itself
        skills = self.extract_skills(text)
        sections = self._extract_sections(text)
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
        target_roles = self._detect_roles(text, experience)
        education = self._parse_education(sections.get("education", ""))
        projects = self._parse_projects(sections.get("projects", ""))
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
            "education": education,
            "projects": projects,
            "certifications": certifications,
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
            "summary": re.compile(r"^(?:professional\s+summary|executive\s+summary|summary|profile|about\s+me)\b", re.I),
            "skills": re.compile(r"^(?:key\s+skills|technical\s+skills|top\s+skills|areas\s+of\s+expertise|skills\s*(?:&|and)\s*technologies|core\s+competencies|skills)\b", re.I),
            "experience": re.compile(r"^(?:work\s+experience|professional\s+experience|employment\s+history|experience)\b", re.I),
            "education": re.compile(r"^(?:education|academic\s+background|qualifications)\b", re.I),
            "projects": re.compile(r"^(?:technical\s+projects|key\s+projects|portfolio\s+projects|personal\s+projects|projects)\b", re.I),
            "certifications": re.compile(r"^(?:certifications\s*(?:&|and)\s*licenses|certifications|licenses|certificates)\b", re.I),
        }

        current_section = "preamble"
        section_lines: Dict[str, List[str]] = {k: [] for k in headers}
        section_lines["preamble"] = []

        lines = text.split("\n")
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Check if this line is a section header (usually short, <= 45 chars)
            matched_sec = None
            if len(trimmed) <= 45:
                # Strip leading/trailing hashes, asterisks or dashes
                clean_heading = re.sub(r"^[\s#\-\*•:]+|[\s#\-\*•:]+$", "", trimmed)
                for sec_key, pattern in headers.items():
                    if pattern.search(clean_heading):
                        matched_sec = sec_key
                        break

            if matched_sec:
                current_section = matched_sec
            else:
                section_lines[current_section].append(trimmed)

        return {k: "\n".join(v) for k, v in section_lines.items()}

    def _parse_experience(self, text: str) -> List[Dict[str, Any]]:
        """Parses job experience entries from experience section text."""
        if not text:
            return []

        entries = []
        current: Optional[Dict[str, Any]] = None

        date_pat = re.compile(r"(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?\b(?:19|20)\d{2}\s*(?:-|–|to)\s*(?:(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:19|20)\d{2}|Present|Current)", re.I)

        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            is_bullet = bool(re.match(r"^[\s\-\*•\d\.\)]+", line_str))
            clean_line = re.sub(r"^[\s\-\*•\d\.\)]+", "", line_str).strip()

            # Check if line looks like a job header: has '|' or ' - ' or dates
            has_dates = bool(date_pat.search(line_str))
            has_separator = ("|" in line_str or " - " in line_str or " at " in line_str.lower())

            if (has_dates or has_separator) and not is_bullet and len(line_str) < 120:
                if current:
                    entries.append(current)

                title = ""
                company = ""
                dates = ""

                # Extract dates if present
                d_match = date_pat.search(line_str)
                if d_match:
                    dates = d_match.group(0).strip("()")
                    remainder = line_str[:d_match.start()] + line_str[d_match.end():]
                else:
                    remainder = line_str

                # Split title and company
                if "|" in remainder:
                    parts = [p.strip() for p in remainder.split("|") if p.strip()]
                    title = parts[0]
                    company = parts[1] if len(parts) > 1 else ""
                elif " - " in remainder:
                    parts = [p.strip() for p in remainder.split(" - ") if p.strip()]
                    title = parts[0]
                    company = parts[1] if len(parts) > 1 else ""
                elif " at " in remainder.lower():
                    parts = re.split(r"\s+at\s+", remainder, flags=re.I)
                    title = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else ""
                else:
                    title = remainder.strip()

                current = {
                    "title": title.strip("()[] "),
                    "company": company.strip("()[] "),
                    "organization": company.strip("()[] "),
                    "dates": dates.strip(),
                    "location": "",
                    "description": "",
                    "bullets": [],
                }
            elif current:
                if is_bullet:
                    current["bullets"].append(clean_line)
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
        """Parses project entries from projects section text."""
        if not text:
            return []

        entries = []
        current: Optional[Dict[str, Any]] = None

        lines = text.split("\n")
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            is_bullet = bool(re.match(r"^[\s\-\*•]+", line_str))
            clean_line = re.sub(r"^[\s\-\*•]+", "", line_str).strip()

            if not is_bullet and ("|" in line_str or ":" in line_str or len(line_str) < 70):
                if current:
                    entries.append(current)
                title = line_str.split("|")[0].split(":")[0].strip()
                current = {
                    "title": title,
                    "name": title,
                    "description": line_str,
                    "bullets": [],
                    "dates": "",
                }
            elif current:
                if is_bullet:
                    current["bullets"].append(clean_line)
                else:
                    current["description"] += " " + clean_line

        if current:
            entries.append(current)

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

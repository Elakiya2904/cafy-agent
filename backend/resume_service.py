import os
import re
import io
from typing import Dict, List, Any, Set, Optional
import pypdf
import docx

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
    "rag": "RAG"
}

ALL_CANONICAL_SKILLS = []
for cat_skills in SKILL_TAXONOMY.values():
    ALL_CANONICAL_SKILLS.extend(cat_skills)
ALL_CANONICAL_SKILLS = sorted(list(set(ALL_CANONICAL_SKILLS)), key=lambda s: len(s), reverse=True)


class ResumeService:
    """
    Service responsible for extracting text, candidate metadata, and skills
    from uploaded resumes (PDF, DOCX, TXT).
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
        cleaned_text = re.sub(r"\s+", " ", text).strip()

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

        # Skill Extraction
        skills = self.extract_skills(text)

        # Group by category
        categorized: Dict[str, List[str]] = {}
        for cat, cat_skills in SKILL_TAXONOMY.items():
            cat_lower = {s.lower() for s in cat_skills}
            matches = [s for s in skills if s.lower() in cat_lower]
            if matches:
                categorized[cat] = matches

        # Experience & Seniority
        years, seniority = self._detect_experience(text)
        target_roles = self._detect_roles(text)

        return {
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
            "summary": cleaned_text[:350] + ("..." if len(cleaned_text) > 350 else "")
        }

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
            pat = rf"\b{re.escape(canonical.lower())}\b"
            if re.search(pat, lower_text):
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
        name_clean = re.sub(r"[_\W]+", " ", os.path.splitext(filename)[0]).strip().title()
        return name_clean or "Candidate"

    def _detect_experience(self, text: str) -> tuple[int, str]:
        matches = re.findall(r"(\d+)\+?\s*(?:years|yrs)(?:\s*of)?\s*(?:experience)?", text, re.IGNORECASE)
        years = 0
        if matches:
            nums = [int(m) for m in matches if int(m) < 40]
            if nums:
                years = max(nums)

        lower = text.lower()
        if "principal" in lower or "director" in lower:
            seniority = "Principal / Lead"
        elif "senior" in lower or years >= 5:
            seniority = "Senior"
        elif "lead" in lower:
            seniority = "Lead"
        elif "mid" in lower or (2 <= years < 5):
            seniority = "Mid-Level"
        elif "junior" in lower or "intern" in lower or years < 2:
            seniority = "Junior / Entry"
        else:
            seniority = "Mid-Level"

        return years, seniority

    def _detect_roles(self, text: str) -> List[str]:
        roles = [
            "Full Stack Engineer", "Software Engineer", "Frontend Engineer", "Backend Engineer",
            "DevOps Engineer", "Cloud Engineer", "Data Scientist", "Machine Learning Engineer",
            "AI Engineer", "Data Engineer", "Site Reliability Engineer"
        ]
        lower = text.lower()
        detected = [r for r in roles if r.lower() in lower]
        return detected if detected else ["Software Engineer"]

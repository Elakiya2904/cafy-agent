from __future__ import annotations
import math
import re
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
from .resume_service import ResumeService

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore
    SKLEARN_AVAILABLE = False


def _pure_python_cosine_similarities(query_text: str, doc_texts: List[str]) -> List[float]:
    """
    Computes TF-IDF cosine similarities between query_text and each document in doc_texts
    using only Python standard library (no external dependencies required).
    """
    if not doc_texts:
        return []

    def tokenize(text: str) -> List[str]:
        return [w for w in re.findall(r"[a-zA-Z0-9+#.-]+", (text or "").lower()) if len(w) > 1]

    query_tokens = tokenize(query_text)
    docs_tokens = [tokenize(d) for d in doc_texts]
    all_docs = [query_tokens] + docs_tokens
    num_docs = len(all_docs)

    # Document frequency
    df = Counter()
    for doc in all_docs:
        df.update(set(doc))

    # IDF with standard smoothing
    idf = {term: math.log((num_docs + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    def get_tfidf_vec(tokens: List[str]) -> Dict[str, float]:
        tf = Counter(tokens)
        total = len(tokens) or 1
        vec = {term: (count / total) * idf.get(term, 1.0) for term, count in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values()))
        if norm > 0:
            return {k: v / norm for k, v in vec.items()}
        return {}

    query_vec = get_tfidf_vec(query_tokens)
    if not query_vec:
        return [0.0] * len(doc_texts)

    results = []
    for doc_toks in docs_tokens:
        d_vec = get_tfidf_vec(doc_toks)
        if not d_vec:
            results.append(0.0)
            continue
        # Cosine similarity of unit vectors is their dot product
        score = sum(query_vec[term] * val for term, val in d_vec.items() if term in query_vec)
        results.append(max(0.0, min(1.0, float(score))))

    return results


EXPERIENCE_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:(?P<range_min>\d+)\s*(?:-|–|to)\s*(?P<range_max>\d+)"
    r"|(?P<minimum>\d+)\s*\+?"
    r"|(?:at least|minimum(?: of)?|no less than)\s+(?P<stated_minimum>\d+))"
    r"\s*(?:years?|yrs?)\s*(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience\b",
    re.IGNORECASE,
)


def _job_experience_requirement(job: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    text = f"{job.get('title', '')} {job.get('description', '')}"
    requirements = list(EXPERIENCE_REQUIREMENT_PATTERN.finditer(text))
    if not requirements:
        return None, None

    match = requirements[0]
    min_raw = match.group("range_min") or match.group("minimum") or match.group("stated_minimum")
    if not min_raw:
        return None, None
    minimum = int(min_raw)
    max_raw = match.group("range_max")
    maximum = int(max_raw) if max_raw else None
    return minimum, maximum


def _experience_level_matches(job: Dict[str, Any], candidate_years: int) -> bool:
    title = (job.get("title") or "").casefold()
    minimum_years, maximum_years = _job_experience_requirement(job)

    if minimum_years is not None and minimum_years > candidate_years:
        return False
    if maximum_years is not None and candidate_years > maximum_years:
        return False

    fresher_role = any(term in title for term in ("intern", "graduate", "new grad", "fresher"))
    junior_role = any(term in title for term in ("junior", "entry-level", "entry level"))
    senior_role = any(term in title for term in ("senior", "staff", "principal", "lead", "director"))

    if candidate_years <= 1:
        if senior_role:
            return False
        if minimum_years is not None and minimum_years > 1:
            return False
    elif fresher_role:
        return False
    elif candidate_years > 3 and junior_role:
        return False

    if senior_role and candidate_years < 5:
        return False
    return True


class RecommendationService:
    """
    Ranks verified stored jobs against candidate resume skills and experience.
    Provides explainable match percentages, aligned skills, missing skills,
    and direct application links. Never invents fake vacancies.
    """

    def __init__(self):
        self.resume_service = ResumeService()
        self.vectorizer = (
            TfidfVectorizer(stop_words="english")
            if SKLEARN_AVAILABLE and TfidfVectorizer is not None
            else None
        )

    def recommend_jobs(
        self,
        resume_data: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        min_score: int = 60,
        platform_filter: str = "all"
    ) -> List[Dict[str, Any]]:
        # Honour the caller's threshold exactly; no artificial floor.
        min_score = 60 if min_score is None else min_score

        # If no verified jobs exist in the database, return clean empty list
        if not jobs:
            return []

        candidate_skills = resume_data.get("skills", [])
        resume_skills_set = {s.lower() for s in candidate_skills}
        target_roles = [r.lower() for r in resume_data.get("target_roles", [])]
        seniority = (resume_data.get("seniority_level") or "").lower()
        raw_years = resume_data.get("years_of_experience")
        try:
            candidate_years = max(0, int(raw_years)) if raw_years is not None else 0
        except (TypeError, ValueError):
            candidate_years = 0
        # A manually supplied seniority level is useful when a resume does not
        # contain a numeric years-of-experience value.
        if raw_years is None:
            if any(level in seniority for level in ("principal", "lead")):
                candidate_years = 7
            elif "senior" in seniority:
                candidate_years = 5

        # Build candidate TF-IDF representation
        resume_corpus = (
            " ".join(resume_data.get("skills", [])) * 3 + " " +
            " ".join(resume_data.get("target_roles", [])) * 2 + " " +
            (resume_data.get("summary") or "")
        )

        job_texts = []
        filtered_jobs = []

        for j in jobs:
            if platform_filter and platform_filter != "all":
                if j.get("platform", "").lower() != platform_filter.lower():
                    continue

            # Ensure skills are present; extract from title+description if missing
            skills = j.get("extracted_skills") or []
            if not skills:
                skills = self.resume_service.extract_skills(f"{j.get('title', '')} {j.get('description', '')}")
                j["extracted_skills"] = skills

            filtered_jobs.append(j)
            job_texts.append(f"{j.get('title', '')} {' '.join(skills) * 2} {j.get('description', '')}")

        if not filtered_jobs:
            return []

        # Calculate TF-IDF cosine similarities
        tfidf_scores = [0.0] * len(filtered_jobs)
        try:
            if SKLEARN_AVAILABLE and self.vectorizer is not None and cosine_similarity is not None:
                corpus = [resume_corpus] + job_texts
                matrix = self.vectorizer.fit_transform(corpus)
                sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
                tfidf_scores = [float(s) for s in sims]
            else:
                tfidf_scores = _pure_python_cosine_similarities(resume_corpus, job_texts)
        except Exception:
            try:
                tfidf_scores = _pure_python_cosine_similarities(resume_corpus, job_texts)
            except Exception:
                tfidf_scores = [0.0] * len(filtered_jobs)

        recommendations = []

        for idx, job in enumerate(filtered_jobs):
            if not _experience_level_matches(job, candidate_years):
                continue

            job_skills = job.get("extracted_skills", [])
            job_skills_lower = {s.lower(): s for s in job_skills}

            # 1. Skill Overlap Calculation
            matched = []
            missing = []
            for s_lower, canonical in job_skills_lower.items():
                if s_lower in resume_skills_set:
                    matched.append(canonical)
                else:
                    missing.append(canonical)

            # Augment: scan title + description text for candidate skills not yet matched
            title_lower = (job.get("title") or "").lower()
            desc_lower = f"{title_lower} {job.get('description', '')}".lower()
            matched_lower = {m.lower() for m in matched}
            for c_skill in candidate_skills:
                c_lower = c_skill.lower()
                if c_lower not in matched_lower:
                    if len(c_lower) <= 3:
                        if re.search(r'\b' + re.escape(c_lower) + r'\b', desc_lower):
                            matched.append(c_skill)
                            matched_lower.add(c_lower)
                    else:
                        if c_lower in desc_lower:
                            matched.append(c_skill)
                            matched_lower.add(c_lower)

            # Only show high-confidence recommendations with four or more shared skills.
            if len(matched) < 4:
                continue

            # Skill score: candidate coverage & job coverage
            candidate_coverage = len(matched) / max(len(candidate_skills), 1)
            job_coverage = len(matched) / max(len(job_skills), 1) if job_skills else candidate_coverage
            skill_score = min(1.0, candidate_coverage * 0.4 + job_coverage * 0.6)

            # 2. Role Title & Domain Alignment
            title_lower = (job.get("title") or "").lower()
            is_role_match = False
            GENERIC_TITLE_WORDS = {"engineer", "developer", "lead", "senior", "manager", "director", "intern", "specialist", "associate", "consultant"}
            # Broader role matching: also match by domain keywords (e.g. "fullstack", "backend", "frontend")
            ROLE_DOMAIN_KEYWORDS = {
                "full stack": ["fullstack", "full stack", "full-stack"],
                "frontend": ["frontend", "front-end", "front end", "ui engineer"],
                "backend": ["backend", "back-end", "back end", "server-side"],
                "software engineer": ["software engineer", "software developer", "swe"],
                "devops": ["devops", "sre", "site reliability", "platform engineer", "infrastructure"],
                "machine learning": ["machine learning", "ml engineer", "ai engineer"],
                "data engineer": ["data engineer", "data platform"],
                "data scientist": ["data scientist", "data science"],
            }
            for r in target_roles:
                r_lower = r.lower().strip()
                if r_lower in title_lower:
                    is_role_match = True; break
                non_generic = [w for w in r_lower.split() if w not in GENERIC_TITLE_WORDS and len(w) > 2]
                if non_generic and all(tok in title_lower for tok in non_generic):
                    is_role_match = True; break
                # Check domain keyword synonyms
                for domain, synonyms in ROLE_DOMAIN_KEYWORDS.items():
                    if any(kw in r_lower for kw in synonyms) and any(kw in title_lower for kw in synonyms):
                        is_role_match = True; break
                if is_role_match:
                    break

            role_score = 1.0 if is_role_match else 0.0

            seniority_bonus = 0.0
            if "senior" in seniority and any(w in title_lower for w in ["senior", "staff", "principal", "lead"]):
                seniority_bonus = 0.05
            elif "lead" in seniority and any(w in title_lower for w in ["lead", "principal", "staff"]):
                seniority_bonus = 0.05
            elif "junior" in seniority and ("junior" in title_lower or "associate" in title_lower):
                seniority_bonus = 0.05

            # 3. Textual Content Similarity (TF-IDF)
            semantic = min(1.0, tfidf_scores[idx] * 3.0)

            # Honest score: weighted blend of the real signals computed above.
            raw_pct = 100.0 * (0.6 * skill_score + 0.25 * role_score + 0.15 * semantic)
            if seniority_bonus > 0:
                raw_pct += 3  # small bonus only when title seniority genuinely matches
            percentage = int(max(0, min(100, round(raw_pct))))

            if percentage >= 80:
                fit_level = "Strong Match"
            elif percentage >= 65:
                fit_level = "Good Match"
            elif percentage >= 50:
                fit_level = "Fair Match"
            else:
                fit_level = "Partial Match"

            # Explainable match reasons
            reasons = []
            if matched:
                reasons.append(f"Strong overlap on {', '.join(matched[:4])}")
            if role_score >= 0.8:
                reasons.append("Matches your target job title")
            if seniority_bonus > 0:
                reasons.append(f"Aligned with your {seniority.title()} seniority level")
            minimum_years, maximum_years = _job_experience_requirement(job)
            if minimum_years is not None:
                requirement = (
                    f"{minimum_years}-{maximum_years} years"
                    if maximum_years is not None
                    else f"{minimum_years}+ years"
                )
                reasons.append(f"Listing asks for {requirement} of experience")
            if job.get("is_remote"):
                reasons.append("Remote-friendly opportunity")

            rec_item = {
                **job,
                "match_score": percentage,
                "fit_level": fit_level,
                "matched_skills": matched,
                "missing_skills": missing,
                "match_reasons": reasons
            }

            if percentage >= min_score:
                recommendations.append(rec_item)

        # Sort descending by match score
        recommendations.sort(key=lambda x: x["match_score"], reverse=True)
        return recommendations

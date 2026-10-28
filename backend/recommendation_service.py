import re
from typing import List, Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .resume_service import ResumeService

class RecommendationService:
    """
    Ranks verified stored jobs against candidate resume skills and experience.
    Provides explainable match percentages, aligned skills, missing skills,
    and direct application links. Never invents fake vacancies.
    """

    def __init__(self):
        self.resume_service = ResumeService()
        self.vectorizer = TfidfVectorizer(stop_words="english", max_features=1500)

    def recommend_jobs(
        self,
        resume_data: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        min_score: int = 85,
        platform_filter: str = "all"
    ) -> List[Dict[str, Any]]:
        min_score = min_score if min_score is not None else 85

        # If no verified jobs exist in the database, return clean empty list
        if not jobs:
            return []

        candidate_skills = resume_data.get("skills", [])
        resume_skills_set = {s.lower() for s in candidate_skills}
        target_roles = [r.lower() for r in resume_data.get("target_roles", [])]
        seniority = resume_data.get("seniority_level", "Mid-Level").lower()

        # Build candidate TF-IDF representation
        resume_corpus = (
            " ".join(resume_data.get("skills", [])) * 3 + " " +
            " ".join(resume_data.get("target_roles", [])) * 2 + " " +
            resume_data.get("summary", "")
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
            corpus = [resume_corpus] + job_texts
            matrix = self.vectorizer.fit_transform(corpus)
            sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
            tfidf_scores = [float(s) for s in sims]
        except Exception:
            tfidf_scores = [0.0] * len(filtered_jobs)

        recommendations = []

        for idx, job in enumerate(filtered_jobs):
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

            # Jobs with no skills at all: score on role+seniority title match only
            if not job_skills and not matched:
                title_lower = (job.get("title") or "").lower()
                is_title_role = any(
                    any(kw in title_lower for kw in syns)
                    for r in target_roles
                    for domain, syns in [
                        ("full stack", ["fullstack", "full stack", "full-stack"]),
                        ("frontend", ["frontend", "front-end"]),
                        ("backend", ["backend", "back-end"]),
                        ("software", ["software engineer", "software developer"]),
                        ("devops", ["devops", "sre", "site reliability", "platform engineer"]),
                        ("ml", ["machine learning", "ml engineer", "ai engineer"]),
                        ("data", ["data engineer", "data scientist"]),
                    ]
                    if any(kw in r for kw in syns)
                )
                if not is_title_role:
                    continue
                # Title-only score: max 72% (not enough signal for high confidence)
                seniority_bonus = 0.05 if any(w in title_lower for w in ["senior", "staff", "principal", "lead"]) and "senior" in seniority else 0.0
                pct = min(72, 60 + int(seniority_bonus * 100))
                if pct >= min_score:
                    recommendations.append({
                        **job,
                        "match_score": pct,
                        "fit_level": "Good Fit",
                        "matched_skills": [],
                        "missing_skills": [],
                        "match_reasons": ["Role title aligns with your target position"]
                    })
                continue

            # Require at least 2 matched skills before scoring
            if len(matched) < 2:
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

            role_score = 0.95 if is_role_match else 0.40

            seniority_bonus = 0.0
            if "senior" in seniority and any(w in title_lower for w in ["senior", "staff", "principal", "lead"]):
                seniority_bonus = 0.05
            elif "lead" in seniority and any(w in title_lower for w in ["lead", "principal", "staff"]):
                seniority_bonus = 0.05
            elif "junior" in seniority and ("junior" in title_lower or "associate" in title_lower):
                seniority_bonus = 0.05

            # 3. Textual Content Similarity (TF-IDF)
            semantic = min(1.0, tfidf_scores[idx] * 3.0)

            # User Condition:
            # When relevant (matched) skills is 4 or more, score is guaranteed 85% or above.
            # Fewer than 4 skills are capped below 85%.
            if len(matched) >= 4:
                base_pct = 85 + min(8, (len(matched) - 4) * 2)
                if is_role_match:
                    base_pct += 3
                if seniority_bonus > 0:
                    base_pct += 2
                base_pct += min(3, int(round(semantic * 5)))
                percentage = min(98, max(85, base_pct))
            else:
                raw_score = (skill_score * 0.50) + (min(1.0, role_score + seniority_bonus) * 0.35) + (semantic * 0.15)
                calculated = int(round(raw_score * 100))
                if len(matched) == 3:
                    percentage = min(82, max(68, calculated))
                elif len(matched) == 2:
                    percentage = min(74, max(50, calculated))
                else:
                    percentage = min(58, max(25, calculated))

            fit_level = (
                "Exceptional Match" if percentage >= 85 else (
                    "Strong Match" if percentage >= 70 else (
                        "Good Fit" if percentage >= 50 else "Potential Fit"
                    )
                )
            )

            # Explainable match reasons
            reasons = []
            if matched:
                reasons.append(f"Strong overlap on {', '.join(matched[:4])}")
            if role_score >= 0.8:
                reasons.append("Matches your target job title")
            if seniority_bonus > 0:
                reasons.append(f"Aligned with your {seniority.title()} seniority level")
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

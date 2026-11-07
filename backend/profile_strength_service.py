"""Profile Strength & Completeness Evaluation Service for Cafy Agent.

Evaluates candidate profiles across 6 dimensions:
1. Contact & Summary (15%)
2. Technical Skills (25%)
3. Work Experience (25%)
4. Education (15%)
5. Projects (10%)
6. Certifications (10%)

Provides granular section scores, completeness statuses, identified gaps,
and prioritized action items to help candidates reach All-Star / ATS-ready status.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

try:
    from .resume_structure import full_time_years, split_internships
except ImportError:  # imported as a top-level module by older scripts
    from resume_structure import full_time_years, split_internships


METRIC_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?%|\$\s*\d+|\b\d+\s*(?:k|m|million|billion|users|clients|teams|services|microservices|servers|qps|rps|ms|percent|x)\b|"
    r"\b(?:reduced|increased|improved|boosted|optimized|accelerated|saved|scaled|cut|grown)\s+by\s+\d+)",
    re.IGNORECASE,
)


def evaluate_profile_strength(resume: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes overall profile completeness score (0-100), section-by-section breakdown,

    incomplete section flags, and prioritized actionable recommendations.
    """
    if not resume:
        return {
            "overall_score": 0,
            "strength_tier": "No Profile",
            "tier_badge_color": "slate",
            "sections": {
                "basics": {"name": "Contact & Summary", "score": 0, "status": "missing", "weight": 15, "details": "No contact information detected"},
                "skills": {"name": "Skills Taxonomy", "score": 0, "status": "missing", "weight": 25, "details": "No skills extracted"},
                "experience": {"name": "Work Experience", "score": 0, "status": "missing", "weight": 25, "details": "No experience recorded"},
                "education": {"name": "Education", "score": 0, "status": "missing", "weight": 15, "details": "No education listed"},
                "projects": {"name": "Projects", "score": 0, "status": "missing", "weight": 10, "details": "No projects added"},
                "certifications": {"name": "Certifications", "score": 0, "status": "missing", "weight": 10, "details": "No certifications listed"},
            },
            "incomplete_sections": ["basics", "skills", "experience", "education", "projects", "certifications"],
            "suggestions": [
                {
                    "id": "upload_resume",
                    "section": "basics",
                    "priority": "high",
                    "impact": None,
                    "text": "Upload your resume (PDF/DOCX) to begin.",
                }
            ],
            "total_suggestions_count": 1,
        }

    # 1. Evaluate Contact & Summary (15% weight)
    basics_score = 0
    basics_notes = []
    
    cand_name = (resume.get("candidate_name") or "").strip()
    if cand_name and cand_name.lower() not in ["candidate", "unknown", "uploaded_resume"]:
        basics_score += 25
    else:
        basics_notes.append("Add full name")

    email = (resume.get("email") or "").strip()
    if email and "@" in email:
        basics_score += 25
    else:
        basics_notes.append("Add professional email")

    phone = (resume.get("phone") or "").strip()
    if phone:
        basics_score += 15
    else:
        basics_notes.append("Add phone number")

    links_count = sum(1 for k in ["linkedin", "github", "portfolio", "website"] if (resume.get(k) or "").strip())
    if links_count >= 2:
        basics_score += 20
    elif links_count == 1:
        basics_score += 12
    else:
        basics_notes.append("Add LinkedIn or GitHub profile link")

    summary = (resume.get("summary") or "").strip()
    if len(summary) >= 60:
        basics_score += 15
    elif len(summary) >= 20:
        basics_score += 8
    else:
        basics_notes.append("Add a 2-3 sentence career summary")

    basics_score = min(100, basics_score)

    # 2. Evaluate Technical Skills (25% weight)
    skills = resume.get("skills") or resume.get("all_skills") or []
    categorized = resume.get("categorized_skills") or {}
    skills_score = 0
    skills_notes = []

    count = len(skills)
    if count >= 12:
        skills_score += 55
    elif count >= 6:
        skills_score += 45
    elif count >= 4:
        skills_score += 35
    elif count >= 2:
        skills_score += 20
    elif count >= 1:
        skills_score += 10
    else:
        skills_notes.append("List your key professional skills")

    if not categorized and skills:
        # Profiles edited by hand have no categories yet; group them the way the parser does.
        from .resume_service import SKILL_TAXONOMY  # local import: resume_service imports this module
        lowered = {str(s).lower() for s in skills}
        categorized = {
            cat: [s for s in cat_skills if s.lower() in lowered]
            for cat, cat_skills in SKILL_TAXONOMY.items()
        }
        uncategorized = lowered - {s.lower() for sks in categorized.values() for s in sks}
        if uncategorized:
            categorized["Other Skills"] = sorted(uncategorized)
    num_cats = len([c for c, sks in categorized.items() if len(sks) > 0])
    if num_cats >= 4:
        skills_score += 45
    elif num_cats >= 3:
        skills_score += 35
    elif num_cats >= 2:
        skills_score += 25
    elif num_cats >= 1:
        skills_score += 15

    if count < 6:
        skills_notes.append(f"Add {6 - count} more relevant skills across domains")

    skills_score = min(100, skills_score)

    # 3. Evaluate Work Experience (25% weight)
    raw_exp = resume.get("experience") or []
    raw_internships = resume.get("internships") or []
    # Full-time roles and internships both earn credit here; each role is counted once and
    # internships are never relabelled as full-time roles.
    full_time, internships = split_internships(
        [e for e in raw_exp if isinstance(e, dict)] if isinstance(raw_exp, list) else [],
        [e for e in raw_internships if isinstance(e, dict)] if isinstance(raw_internships, list) else [],
    )
    experience = full_time + internships
    raw_text = resume.get("raw_text") or ""
    exp_score = 0
    exp_notes = []

    # If experience array is empty, check if raw_text indicates experience
    try:
        years = float(resume.get("years_of_experience") or 0)
    except (TypeError, ValueError):
        years = 0.0
    # No stated figure: use the dates on full-time roles (internships never add years).
    years = years or full_time_years(full_time)
    has_raw_exp = bool(re.search(r"\b(?:experience|employment|work history|internship|internships)\b", raw_text, re.I))

    if experience and isinstance(experience, list) and len(experience) > 0:
        role_count = len(experience)
        if role_count >= 3:
            exp_score += 40
        elif role_count == 2:
            exp_score += 32
        elif role_count == 1:
            exp_score += 22

        # Inspect bullets and metrics
        total_bullets = 0
        has_metrics = 0
        has_dates = 0
        for exp in experience:
            bullets = exp.get("bullets") or []
            desc = exp.get("description") or ""
            if exp.get("dates"):
                has_dates += 1
            if bullets:
                total_bullets += len(bullets)
                for b in bullets:
                    if METRIC_PATTERN.search(str(b)):
                        has_metrics += 1
            elif desc and METRIC_PATTERN.search(desc):
                has_metrics += 1

        if total_bullets >= 6:
            exp_score += 25
        elif total_bullets >= 3:
            exp_score += 18
        elif total_bullets >= 1:
            exp_score += 10
        else:
            exp_notes.append("Add detailed bullet points for each role")

        if has_metrics >= 2:
            exp_score += 20
        elif has_metrics == 1:
            exp_score += 12
        else:
            exp_notes.append("Add quantifiable metrics (e.g. 'reduced latency by 35%')")

        if has_dates >= min(role_count, 2):
            exp_score += 15
        else:
            exp_notes.append("Ensure start and end dates are included")

    elif years > 0 or has_raw_exp:
        # Detected in resume text but unparsed into structured JSON
        exp_score = 45 if years >= 3 else 35
        exp_notes.append("Format work experience with clear company names, dates, and outcome bullets")
    else:
        exp_notes.append("Add your work history or professional experience")

    exp_score = min(100, exp_score)

    # 4. Evaluate Education (15% weight)
    education = resume.get("education") or []
    edu_score = 0
    edu_notes = []
    has_raw_edu = bool(re.search(r"\b(?:education|university|college|degree|bachelor|master|b\.?s|m\.?s|b\.?tech|m\.?tech|phd)\b", raw_text, re.I))

    if education and isinstance(education, list) and len(education) > 0:
        edu_score += 55
        item = education[0]
        deg = (item.get("degree") or item.get("title") or "").strip()
        inst = (item.get("institution") or item.get("organization") or "").strip()
        dates = (item.get("dates") or "").strip()

        if deg:
            edu_score += 20
        else:
            edu_notes.append("Specify degree or field of study")

        if inst:
            edu_score += 15
        else:
            edu_notes.append("Specify college or university name")

        if dates:
            edu_score += 10
    elif has_raw_edu:
        edu_score = 45
        edu_notes.append("Confirm degree title and graduation year")
    else:
        edu_notes.append("Add your degree, university, and graduation year")

    edu_score = min(100, edu_score)

    # 5. Evaluate Projects (10% standard weight)
    projects = resume.get("projects") or []
    proj_score = 0
    proj_notes = []
    has_raw_proj = bool(re.search(r"\b(?:projects|portfolio projects|key projects)\b", raw_text, re.I))
    is_senior = (years >= 5) or any(k in str(resume.get("seniority_level") or "").lower() for k in ["senior", "lead", "principal"])

    if projects and isinstance(projects, list) and len(projects) > 0:
        proj_count = len(projects)
        if proj_count >= 2:
            proj_score += 65
        else:
            proj_score += 45

        bullets_found = sum(len(p.get("bullets") or []) for p in projects if isinstance(p, dict))
        if bullets_found >= 3:
            proj_score += 35
        elif bullets_found >= 1:
            proj_score += 20
        else:
            proj_notes.append("Add technical details and outcomes for your projects")
    elif has_raw_proj:
        proj_score = 35
        proj_notes.append("Format projects with titles, technologies used, and outcomes")
    elif not is_senior:
        proj_notes.append("Add 1-2 highlight projects with tools used and links")

    proj_score = min(100, proj_score)

    # 6. Evaluate Certifications (10% standard weight)
    certs = resume.get("certifications") or []
    certs_score = 0
    certs_notes = []
    has_raw_certs = bool(re.search(r"\b(?:certified|certification|certifications|license|aws certified|ckad|cka|pmp|comptia)\b", raw_text, re.I))

    if certs and isinstance(certs, list) and len(certs) > 0:
        certs_score = 100 if len(certs) >= 2 else 75
    elif has_raw_certs:
        certs_score = 40
        certs_notes.append("Confirm certificate issuer and completion date")
    elif not is_senior:
        certs_notes.append("Add industry certifications (e.g., AWS, GCP, CKA, PMP) to boost recruiter match")

    certs_score = min(100, certs_score)

    # Calculate overall weighted score with transparent weight redistribution
    weights = {
        "skills": 0.25,
        "experience": 0.25,
        "education": 0.15,
        "basics": 0.15,
        "projects": 0.10,
        "certifications": 0.10,
    }

    scores = {
        "skills": skills_score, "experience": exp_score, "education": edu_score,
        "basics": basics_score, "projects": proj_score, "certifications": certs_score,
    }

    def weighted(w: Dict[str, float]) -> float:
        return sum(scores[k] * w[k] for k in w if w[k] > 0)

    def without(w: Dict[str, float], key: str, move_to: tuple) -> Dict[str, float]:
        moved = dict(w)
        for target in move_to:
            moved[target] += moved[key] / len(move_to)
        moved[key] = 0.0
        return moved

    # Optional sections only ever help: projects (for senior professionals, 5+ years stated or
    # shown by full-time role dates). Their weight moves to the core sections whenever that
    # gives the higher score, so leaving them out - or adding a modest one - never costs points.
    if is_senior:
        alt = without(weights, "projects", ("experience", "skills"))
        if not projects or weighted(alt) > weighted(weights):
            weights = alt
    # Certifications are a bonus on top (up to +5 points), never a weighted requirement.
    weights = without(weights, "certifications", ("experience", "basics"))
    certs_bonus = round(certs_score * 0.05, 1)

    overall = min(100.0, weighted(weights) + certs_bonus)
    overall_score = max(0, min(100, int(round(overall))))

    # Determine Tier & Color
    if overall_score >= 88:
        tier = "All-Star Profile"
        badge_color = "emerald"
    elif overall_score >= 72:
        tier = "Strong Profile"
        badge_color = "blue"
    elif overall_score >= 55:
        tier = "Competitive"
        badge_color = "amber"
    elif overall_score >= 35:
        tier = "Developing"
        badge_color = "orange"
    else:
        tier = "Needs Attention"
        badge_color = "rose"

    def status_for(score: int) -> str:
        if score >= 80:
            return "complete"
        if score >= 45:
            return "in_progress"
        return "incomplete"

    sections = {
        "skills": {
            "name": "Technical Skills",
            "score": skills_score,
            "status": status_for(skills_score),
            "weight": 25,
            "details": f"{count} skills across {num_cats} categories" if count > 0 else "No skills listed",
            "gaps": skills_notes,
        },
        "experience": {
            "name": "Work Experience",
            "score": exp_score,
            "status": status_for(exp_score),
            "weight": 25,
            "details": f"{len(experience)} roles documented" if experience else ("Experience mentioned" if exp_score > 0 else "No experience listed"),
            "gaps": exp_notes,
        },
        "education": {
            "name": "Education",
            "score": edu_score,
            "status": status_for(edu_score),
            "weight": 15,
            "details": f"{len(education)} qualification(s)" if education else ("Degree mentioned" if edu_score > 0 else "No education listed"),
            "gaps": edu_notes,
        },
        "basics": {
            "name": "Contact & Summary",
            "score": basics_score,
            "status": status_for(basics_score),
            "weight": 15,
            "details": f"{'Complete' if basics_score >= 85 else 'Partially filled'} ({links_count} links)",
            "gaps": basics_notes,
        },
        "projects": {
            "name": "Projects",
            "score": proj_score,
            "status": "optional" if weights["projects"] == 0 else status_for(proj_score),
            "weight": int(round(weights["projects"] * 100)),
            "details": "Optional for senior professionals; weight redistributed to Work Experience and Skills." if weights["projects"] == 0 else (f"{len(projects)} project(s) listed" if projects else ("Projects mentioned" if proj_score > 0 else "No projects added")),
            "gaps": [] if weights["projects"] == 0 else proj_notes,
        },
        "certifications": {
            "name": "Certifications",
            "score": certs_score,
            "status": status_for(certs_score) if certs_score else "optional",
            "weight": 0,
            "bonus_points": certs_bonus,
            "details": (f"{len(certs)} certificate(s): +{certs_bonus:g} bonus points" if certs else
                        "Certifications mentioned" if certs_score > 0 else
                        "Optional bonus (up to +5 points); not having any costs nothing."),
            "gaps": certs_notes,
        },
    }

    # Incomplete sections (score < 75% for active weighted sections)
    incomplete_keys = [k for k, sec in sections.items() if sec["score"] < 75 and weights[k] > 0]
    incomplete_keys.sort(key=lambda k: weights[k] * (100 - sections[k]["score"]), reverse=True)

    # Positive factors & missing info for explainability
    positive_factors = []
    if basics_score >= 80:
        positive_factors.append("Complete contact details and professional summary")
    if skills_score >= 80:
        positive_factors.append(f"Broad technical skillset spanning {num_cats} categories")
    if exp_score >= 80:
        positive_factors.append(f"Documented work history with measurable impact")
    elif exp_score >= 60:
        positive_factors.append("Consistent employment record")
    if edu_score >= 80:
        positive_factors.append("Verified degree and academic institution")
    if proj_score >= 80 and weights["projects"] > 0:
        positive_factors.append("Practical hands-on project accomplishments")
    elif weights["projects"] == 0:
        positive_factors.append("Senior career status: weight focused on verified commercial delivery")
    if certs_score >= 80 and certs:
        positive_factors.append("Verified industry certifications")

    missing_information = []
    for k in incomplete_keys:
        missing_information.extend(sections[k]["gaps"])

    explanations = {
        "skills": f"Contributes {int(round(skills_score * weights['skills']))} points ({weights['skills']*100:.0f}% weight) based on {count} skills across {num_cats} categories.",
        "experience": f"Contributes {int(round(exp_score * weights['experience']))} points ({weights['experience']*100:.0f}% weight) evaluating role progression, bullets, dates, and metrics.",
        "education": f"Contributes {int(round(edu_score * weights['education']))} points ({weights['education']*100:.0f}% weight) assessing degree, institution, and dates.",
        "basics": f"Contributes {int(round(basics_score * weights['basics']))} points ({weights['basics']*100:.0f}% weight) reflecting contact info, links, and summary.",
        "projects": f"Contributes {int(round(proj_score * weights['projects']))} points ({weights['projects']*100:.0f}% weight) for technical project evidence." if weights["projects"] > 0 else "Optional for senior professionals (0% weight); weight redistributed to Work Experience and Technical Skills.",
        "certifications": f"Optional bonus: adds {certs_bonus:g} of up to 5 points for industry credentials; never a penalty.",
    }

    # Generate prioritized suggestions
    suggestions = []
    
    # 1. Experience Gaps
    if exp_score < 75:
        if not experience:
            suggestions.append({
                "id": "add_experience",
                "section": "experience",
                "priority": "high",
                "impact": f"+{int(round(weights['experience'] * (80 - exp_score)))}%",
                "title": "Add Work Experience Entries",
                "text": "Add your recent jobs with company name, dates, and 2-3 outcome-oriented bullets.",
            })
        elif exp_notes:
            suggestions.append({
                "id": "quantify_experience",
                "section": "experience",
                "priority": "high",
                "impact": "+8%",
                "title": "Add Quantified Metrics to Roles",
                "text": "Include measurable metrics (e.g. '% efficiency gain', 'served 10k users', 'cut costs by 20%') to stand out to ATS filters.",
            })

    # 2. Skills Gaps
    if skills_score < 80:
        suggestions.append({
            "id": "expand_skills",
            "section": "skills",
            "priority": "high" if count < 6 else "medium",
            "impact": f"+{int(round(weights['skills'] * (85 - skills_score)))}%",
            "title": "Expand Core Technical Skills",
            "text": f"You have {count} skills. Aim for 12-15 skills covering languages, frameworks, cloud, and tools.",
        })

    # 3. Education Gaps
    if edu_score < 75:
        suggestions.append({
            "id": "add_education",
            "section": "education",
            "priority": "medium",
            "impact": f"+{int(round(weights['education'] * (85 - edu_score)))}%",
            "title": "Add Degree & University Details",
            "text": "Specify your university/college, degree title (e.g., B.Sc. Computer Science), and graduation year.",
        })

    # 4. Contact/Summary Gaps
    if basics_score < 80:
        if links_count == 0:
            suggestions.append({
                "id": "add_profile_links",
                "section": "basics",
                "priority": "medium",
                "impact": "+5%",
                "title": "Add LinkedIn or GitHub URL",
                "text": "Profiles with verified LinkedIn or GitHub links receive 40% higher response rates from hiring teams.",
            })
        if len(summary) < 50:
            suggestions.append({
                "id": "add_summary",
                "section": "basics",
                "priority": "medium",
                "impact": "+4%",
                "title": "Write a 2-3 Sentence Professional Summary",
                "text": "Summarize your core competencies, years of experience, and target impact.",
            })

    # 5. Project Gaps
    if proj_score < 75:
        suggestions.append({
            "id": "add_projects",
            "section": "projects",
            "priority": "medium" if count >= 8 else "low",
            "impact": f"+{int(round(weights['projects'] * (85 - proj_score)))}%",
            "title": "Add 1-2 Highlight Projects",
            "text": "Showcase technical projects detailing technologies used, architecture, and live links or repos.",
        })

    # 6. Certification Gaps
    if certs_score < 60:
        suggestions.append({
            "id": "add_certifications",
            "section": "certifications",
            "priority": "low",
            "impact": "+8%",
            "title": "Add Industry Certifications",
            "text": "Add relevant certificates or licences for your field (e.g., CPA, teaching licence, PMP, AWS).",
        })

    return {
        "overall_score": overall_score,
        "strength_tier": tier,
        "tier_badge_color": badge_color,
        "sections": sections,
        "category_scores": {k: sec["score"] for k, sec in sections.items()},
        "positive_factors": positive_factors,
        "missing_information": missing_information,
        "recommendations": suggestions,
        "explanations": explanations,
        "incomplete_sections": incomplete_keys,
        "suggestions": suggestions,
        "total_suggestions_count": len(suggestions),
    }


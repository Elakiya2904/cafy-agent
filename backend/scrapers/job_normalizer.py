import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

# Re-use our skills extraction logic from resume_service
from ..resume_service import ResumeService

_resume_svc = ResumeService()

class JobNormalizer:
    """
    Validates, sanitizes, and standardizes job records collected from any ATS platform.
    Ensures all jobs have verified URLs, clean descriptions, and extracted skills.
    Rejects malformed or incomplete records.
    """

    @staticmethod
    def normalize_job(raw: Dict[str, Any], platform: str, default_company: str = "") -> Optional[Dict[str, Any]]:
        # 1. Title validation
        title = (raw.get("title") or "").strip()
        if not title or len(title) < 2:
            return None

        # 2. Company validation
        company = (raw.get("company") or default_company).strip()
        if not company:
            return None

        # 3. Source identifier validation
        source_id = str(raw.get("source_id") or raw.get("id") or "").strip()
        if not source_id:
            return None

        # 4. URL validation
        url = (raw.get("url") or "").strip()
        if not url:
            return None
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ["http", "https"] or not parsed_url.netloc:
            return None

        # 5. Clean description from HTML / rich text
        raw_desc = raw.get("description") or ""
        clean_desc = JobNormalizer.clean_description(raw_desc)

        # 6. Location & Remote detection
        location = (raw.get("location") or "Remote").strip()
        is_remote = JobNormalizer.detect_remote(location, title, clean_desc, raw.get("is_remote"))

        # 7. Employment type & Department
        employment_type = (raw.get("employment_type") or "Full-time").strip()
        department = (raw.get("department") or "Engineering").strip()
        posted_at = raw.get("posted_at")

        # 8. Skill extraction from title + description
        combined_text = f"{title} {clean_desc}"
        extracted_skills = _resume_svc.extract_skills(combined_text)

        # 9. Standard Unique ID: {platform}_{company_slug}_{source_id}
        comp_slug = re.sub(r"[^\w]+", "_", company.lower()).strip("_")
        unique_id = f"{platform}_{comp_slug}_{source_id}"

        return {
            "id": unique_id,
            "source_job_id": source_id,
            "title": title,
            "company": company,
            "platform": platform,
            "location": location,
            "is_remote": is_remote,
            "url": url,
            "description": clean_desc,
            "department": department,
            "employment_type": employment_type,
            "posted_at": str(posted_at) if posted_at else None,
            "extracted_skills": extracted_skills
        }

    @staticmethod
    def clean_description(raw_html: str) -> str:
        if not raw_html:
            return ""
        try:
            soup = BeautifulSoup(raw_html, "html.parser")
            # Remove scripts, styles
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            text = soup.get_text(separator=" \n ")
            # Collapse excess whitespace
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            return "\n".join(lines)[:3500]
        except Exception:
            return re.sub(r"\s+", " ", raw_html).strip()[:3500]

    @staticmethod
    def detect_remote(location: str, title: str, description: str, explicit_remote: Optional[bool] = None) -> bool:
        if explicit_remote is True:
            return True
        loc_lower = location.lower()
        if "remote" in loc_lower or "anywhere" in loc_lower or "virtual" in loc_lower or "wfh" in loc_lower:
            return True
        if "remote" in title.lower():
            return True
        # Check first 200 chars of description
        if "100% remote" in description[:200].lower() or "fully remote" in description[:200].lower():
            return True
        return False

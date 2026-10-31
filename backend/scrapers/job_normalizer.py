import re
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

# Re-use our skills extraction logic from resume_service
from ..resume_service import ResumeService

_resume_svc = ResumeService()
UK_IRELAND_LOCATION_PATTERN = re.compile(
    r"\b(?:u\.?k\.?|united kingdom|great britain|britain|england|scotland|"
    r"wales|northern ireland|ireland|republic of ireland|eire)\b",
    re.IGNORECASE,
)
UK_IRELAND_CITY_PATTERN = re.compile(
    r"\b(?:aberdeen|belfast|birmingham|bradford|brighton|bristol|cambridge|"
    r"cardiff|cork|derry|dublin|dundee|edinburgh|exeter|galway|glasgow|"
    r"leeds|limerick|liverpool|london|manchester|newcastle|norwich|"
    r"nottingham|oxford|reading|sheffield|southampton|swansea|waterford|"
    r"york)\b",
    re.IGNORECASE,
)
NON_UK_IRELAND_COUNTRY_PATTERN = re.compile(
    r"\b(?:new[-\s]+york(?: city)?|san francisco|seattle|united states|u\.?s\.?a?\.?|canada|australia|india|singapore|"
    r"new zealand|netherlands|germany|france|spain|italy|japan|china|"
    r"taiwan|malaysia|mexico|romania|israel|poland|sweden|switzerland|"
    r"belgium|brazil|philippines|indonesia|south korea|thailand|vietnam|"
    r"portugal|denmark|norway|finland|austria|south africa|czech republic|"
    r"turkey|argentina|colombia|hong kong|united arab emirates|uae)\b",
    re.IGNORECASE,
)

class JobNormalizer:
    """
    Validates, sanitizes, and standardizes job records collected from any ATS platform.
    Ensures all jobs have verified URLs, clean descriptions, and extracted skills.
    Rejects malformed or incomplete records.
    """

    @staticmethod
    def is_uk_or_ireland_location(location: str) -> bool:
        """Return whether a location identifies a UK or Ireland role."""
        normalized_location = (location or "").strip()
        if not normalized_location:
            return False
        if NON_UK_IRELAND_COUNTRY_PATTERN.search(normalized_location):
            return False
        return bool(
            UK_IRELAND_LOCATION_PATTERN.search(normalized_location)
            or UK_IRELAND_CITY_PATTERN.search(normalized_location)
        )

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
        location = (raw.get("location") or "").strip()
        is_remote = JobNormalizer.detect_remote(location, title, clean_desc, raw.get("is_remote"))

        # 7. Employment type & Department
        employment_type = (raw.get("employment_type") or "").strip()
        department = (raw.get("department") or "").strip()
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
        # An unknown/empty location is NOT evidence of a remote role.
        loc_lower = (location or "").lower()
        if "remote" in loc_lower or "anywhere" in loc_lower or "virtual" in loc_lower or "wfh" in loc_lower:
            return True
        if "remote" in (title or "").lower():
            return True
        # Check first 200 chars of description
        if "100% remote" in (description or "")[:200].lower() or "fully remote" in (description or "")[:200].lower():
            return True
        return False

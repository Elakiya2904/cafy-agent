import csv
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Set, Tuple


REGISTER_FILENAME_PATTERN = "SP_-_Worker_and_Temporary_Worker_Web_Register_*.csv"
ORGANISATION_NAME_COLUMN = "Organisation Name"
TOWN_COLUMN = "Town/City"
COUNTY_COLUMN = "County"
SPONSOR_COUNTRY = "United Kingdom"
UK_CONFIRMED = "UK_CONFIRMED"
NON_UK = "NON_UK"
LOCATION_UNVERIFIED = "LOCATION_UNVERIFIED"
UK_LOCATION_PATTERN = re.compile(
    r"\b(?:uk(?:-wide)?|u\.?k\.?|united kingdom|great britain|britain|"
    r"england|scotland|wales|northern ireland)\b",
    re.IGNORECASE,
)
REMOTE_PATTERN = re.compile(r"\b(?:remote|remotely|work from home|work-from-home)\b", re.IGNORECASE)
UK_CITIES = {
    "aberdeen", "armagh", "bangor", "bath", "belfast", "birmingham", "bradford",
    "brighton", "bristol", "cambridge", "canterbury", "cardiff", "carlisle",
    "chelmsford", "chester", "chichester", "coventry", "derby", "derry", "dundee",
    "durham", "edinburgh", "ely", "exeter", "glasgow", "gloucester", "hereford",
    "inverness", "kingston upon hull", "lancaster", "leeds", "leicester", "lichfield",
    "lincoln", "lisburn", "liverpool", "london", "manchester", "newcastle upon tyne",
    "newport", "norwich", "nottingham", "oxford", "peterborough", "plymouth",
    "portsmouth", "preston", "ripon", "salford", "salisbury", "sheffield",
    "southampton", "southend on sea", "st albans", "st asaph", "st davids",
    "stirling", "stoke on trent", "sunderland", "swansea", "truro", "wakefield",
    "wells", "westminster", "winchester", "wolverhampton", "worcester", "york",
}
COMPANY_NAME_SUFFIXES = {
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "llp",
    "ltd",
    "plc",
    "uk",
}
COMPANY_NAME_ALIASES = {
    "cfc": {"cfc underwriting"},
    "github": {"github software"},
    "ramp": {"ramp business"},
}
NON_UK_COUNTRY_PATTERN = re.compile(
    r"\b(?:united states|u\.?s\.?a?\.?|canada|india|singapore|ireland|"
    r"australia|new zealand|netherlands|germany|france|spain|italy|japan|"
    r"china|taiwan|malaysia|mexico|romania|israel|poland|sweden|"
    r"switzerland|belgium|brazil|philippines|indonesia|south korea|"
    r"thailand|vietnam|portugal|denmark|norway|finland|austria|"
    r"south africa|czech republic|turkey|argentina|colombia|"
    r"hong kong|united arab emirates|uae)\b",
    re.IGNORECASE,
)
NON_UK_REGION_PATTERN = re.compile(
    r"(?:,\s*|\b)(?:al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|"
    r"ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|"
    r"oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy|dc|"
    r"ab|bc|mb|nb|nl|ns|nt|nu|on|pe|qc|sk|yt)\b",
    re.IGNORECASE,
)


def normalize_company_name(company: str) -> str:
    normalized = unicodedata.normalize("NFKC", company).casefold()
    return re.sub(r"[^\w]+", " ", normalized).strip()


def company_name_match_keys(company: str) -> Set[str]:
    normalized = normalize_company_name(company)
    if not normalized:
        return set()

    parts = normalized.split()
    keys = {normalized}
    while parts and parts[-1] in COMPANY_NAME_SUFFIXES:
        parts.pop()
        if parts:
            keys.add(" ".join(parts))

    for key in tuple(keys):
        keys.update(COMPANY_NAME_ALIASES.get(key, set()))
    return keys


class VisaSponsorRegistry:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        (
            self.companies,
            self.uk_places,
            self.company_names_by_key,
        ) = self._load_register()

    @classmethod
    def from_directory(cls, directory: Path) -> "VisaSponsorRegistry":
        registers = sorted(directory.glob(REGISTER_FILENAME_PATTERN)) if directory.exists() else []
        if not registers:
            instance = cls.__new__(cls)
            instance.csv_path = directory
            instance.companies = set()
            instance.uk_places = set()
            instance.company_names_by_key = {}
            return instance
        return cls(registers[-1])

    def _load_register(
        self,
    ) -> Tuple[Set[str], Set[str], Dict[str, Set[str]]]:
        with self.csv_path.open(encoding="utf-8-sig", newline="") as register:
            reader = csv.DictReader(register)
            if ORGANISATION_NAME_COLUMN not in (reader.fieldnames or []):
                raise ValueError(
                    f"{self.csv_path} is missing the "
                    f"{ORGANISATION_NAME_COLUMN!r} column"
                )
            companies = set()
            uk_places = set()
            company_names_by_key: Dict[str, Set[str]] = {}
            for row in reader:
                company = row.get(ORGANISATION_NAME_COLUMN, "").strip()
                if company:
                    match_keys = company_name_match_keys(company)
                    companies.update(match_keys)
                    for match_key in match_keys:
                        company_names_by_key.setdefault(match_key, set()).add(company)
                for column in (TOWN_COLUMN, COUNTY_COLUMN):
                    place = (row.get(column) or "").strip()
                    if place:
                        uk_places.add(normalize_company_name(place))
            return companies, uk_places, company_names_by_key

    def is_sponsored(self, company: str) -> bool:
        return bool(company_name_match_keys(company) & self.companies)

    def find_sponsor_names(self, company: str) -> List[str]:
        matched_names = set()
        for match_key in company_name_match_keys(company):
            matched_names.update(self.company_names_by_key.get(match_key, set()))
        return sorted(matched_names, key=str.casefold)

    def _contains_uk_place(self, text: str) -> bool:
        for part in re.split(r"[,;|•/]+", text or ""):
            normalized_part = normalize_company_name(part.replace("-", " "))
            normalized_part = re.sub(
                r"^(?:remote|remotely|hybrid|based in|in|from)\s+", "", normalized_part
            )
            if normalized_part in UK_CITIES or normalized_part in self.uk_places:
                return True
        return False

    def _description_confirms_uk_remote(self, description: str) -> bool:
        return any(
            REMOTE_PATTERN.search(sentence)
            and (
                UK_LOCATION_PATTERN.search(sentence)
                or self._contains_uk_place(sentence)
            )
            for sentence in re.split(r"[.!?;\n]+", description or "")
        )

    def job_location_status(
        self,
        location: str,
        description: str = "",
        is_remote: bool = False,
    ) -> str:
        location = (location or "").strip()
        if not location:
            if (is_remote or REMOTE_PATTERN.search(description or "")) and self._description_confirms_uk_remote(description):
                return UK_CONFIRMED
            return LOCATION_UNVERIFIED

        country_check_text = re.sub(r"\bnorthern ireland\b", "", location, flags=re.IGNORECASE)
        if (
            NON_UK_COUNTRY_PATTERN.search(country_check_text)
            or NON_UK_REGION_PATTERN.search(location)
        ):
            return NON_UK

        location_has_uk = bool(UK_LOCATION_PATTERN.search(location))
        remote_role = is_remote or bool(REMOTE_PATTERN.search(location))
        if remote_role:
            if location_has_uk or self._contains_uk_place(location):
                return UK_CONFIRMED
            if self._description_confirms_uk_remote(description):
                return UK_CONFIRMED
            return LOCATION_UNVERIFIED

        if location_has_uk:
            return UK_CONFIRMED
        if self._contains_uk_place(location):
            return UK_CONFIRMED

        return LOCATION_UNVERIFIED

    def is_job_in_sponsor_country(self, location: str) -> bool:
        return self.job_location_status(location) == UK_CONFIRMED

    def annotate_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """
        Annotates each job with UK sponsor register data.

        "UK Sponsor Listed" (visa_sponsored=True) is set ONLY when:
          1. The employer's legal entity matches the official UK register, AND
          2. The job location is explicitly UK-eligible (UK_CONFIRMED).

        Overseas jobs are never badged even if the employer has a UK entity.
        Remote/ambiguous locations without explicit UK eligibility are marked
        LOCATION_UNVERIFIED and are NOT badged.

        NOTE: Being on the sponsor register does NOT guarantee visa sponsorship
        for any specific vacancy. Candidates must verify with the employer.
        """
        annotated = []
        for job in jobs:
            sponsor_names = self.find_sponsor_names(job.get("company") or "")
            employer_is_registered = bool(sponsor_names)
            location_status = self.job_location_status(
                job.get("location") or "",
                job.get("description") or "",
                bool(job.get("is_remote")),
            )
            # Both conditions must hold: registered employer AND UK-confirmed location.
            # An overseas job for a registered employer is explicitly NOT badged.
            country_matches = employer_is_registered and location_status == UK_CONFIRMED
            visa_sponsored = country_matches
            annotated.append({
                **job,
                "visa_sponsor_registered": employer_is_registered,
                "visa_sponsor_registered_names": sponsor_names,
                "visa_sponsored": visa_sponsored,
                "visa_sponsor_country": (
                    SPONSOR_COUNTRY if visa_sponsored else None
                ),
                "visa_sponsored_country_match": country_matches,
                "visa_sponsor_location_status": location_status,
                # Explicit disclaimer: register listing ≠ sponsorship for this vacancy.
                "visa_sponsor_disclaimer": (
                    "Employer is listed on the UK Worker and Temporary Worker Sponsor "
                    "Register for this location. This does not guarantee visa sponsorship "
                    "for this specific vacancy. Verify directly with the employer."
                ) if visa_sponsored else None,
            })
        return annotated

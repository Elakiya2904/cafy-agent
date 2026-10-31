import csv
import re
from collections import defaultdict
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


REGISTER_FILENAME_PATTERN = "SP_-_Worker_and_Temporary_Worker_Web_Register_*.csv"
ORGANISATION_NAME_COLUMN = "Organisation Name"
TOWN_COLUMN = "Town/City"
COUNTY_COLUMN = "County"
SPONSOR_COUNTRY = "United Kingdom"
IRELAND_COUNTRY = "Ireland"
UK_CONFIRMED = "UK_CONFIRMED"
NON_UK = "NON_UK"
LOCATION_UNVERIFIED = "LOCATION_UNVERIFIED"
UK_LOCATION_PATTERN = re.compile(
    r"\b(?:uk(?:-wide)?|u\.?k\.?|united kingdom|great britain|britain|"
    r"england|scotland|wales|northern ireland)\b",
    re.IGNORECASE,
)
REMOTE_PATTERN = re.compile(r"\b(?:remote|remotely|work from home|work-from-home)\b", re.IGNORECASE)
IRELAND_LOCATION_PATTERN = re.compile(
    r"\b(?:republic of ireland|ireland|eire|éire|irl|dublin|cork|galway|limerick|waterford|kilkenny|"
    r"athlone|sligo|drogheda|dundalk|swords|maynooth|tallaght|dun laoghaire|blanchardstown|leopardstown|"
    r"sandyford|citywest|clonskeagh|ballsbridge)\b",
    re.IGNORECASE,
)
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
    "stripe": {"stripe payments"},
    "opentable": {"opentable international"},
    "tripactions": {"navan labs"},
    "navan": {"navan labs"},
    "scaleai": {"scale ai"},
    "snowflake": {"snowflake computing u k"},
    "carta": {"carta financial services"},
    "vanta": {"vanta technology"},
    "netflix": {"netflix studios", "netflix productions", "netflix services"},
    "datadog": {"datadog ireland"},
    "samsara": {"samsara networks"},
    "duffel": {"duffel technology"},
    "elevenlabs": {"eleven labs"},
    "kayak": {"kayak software"},
    "perplexity": {"perplexity ai"},
    "siteminder": {"siteminder distribution"},
    "robinhood": {"robinhood u k"},
    "asana": {"asana software"},
    "flexport": {"flexport international"},
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
# US state / Canadian province codes only count when written as ", CA" (upper-case, after a comma),
# so ordinary words such as "or", "in", "me" or "ma" in "London or Dublin" are never read as regions.
NON_UK_REGION_PATTERN = re.compile(
    r",\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|"
    r"NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC|"
    r"AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)\b"
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


IRELAND_NAME_SUFFIXES = COMPANY_NAME_SUFFIXES | {
    "ireland", "irl", "dac", "teoranta", "teo", "unlimited", "company", "designated", "activity",
    "europe", "emea", "international", "by", "guarantee",
}
# Brand -> legal-entity names as they appear in the Irish permit list (checked by hand against the files).
IRELAND_ALIASES = {
    "stripe": {"stripe payments", "stripe technology"},
    "notion": {"notion labs"},
    "okta": {"okta identity"},
    "vanta": {"vanta technology ireland i"},
    "snowflake": {"snowflake computing"},
    "dropbox": {"dropbox"},
    "toast": {"toasttab"},
}
IRELAND_REGISTER_PATTERN = "*employment-permits-issued-to-companies-*.xlsx"


def ireland_match_keys(company: str) -> Set[str]:
    parts = normalize_company_name(company).split()
    keys = set()
    while parts:
        keys.add(" ".join(parts))
        if parts[-1] not in IRELAND_NAME_SUFFIXES:
            break
        parts.pop()
    for key in tuple(keys):
        keys.update(IRELAND_ALIASES.get(key, set()))
    return keys


class IrelandPermitRegistry:
    """Employers that were issued Irish employment permits (Department of Enterprise, Trade and Employment).

    Ireland has no sponsor licence register like the UK's. This official list of permits issued to
    each company is the closest public evidence that an employer hires workers who need a permit.
    """

    def __init__(self, files: List[Path]):
        self.permits: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))  # entity name -> year -> permits
        self.names_by_key: Dict[str, Set[str]] = defaultdict(set)
        for file in files:
            self._load(file)
        for name in self.permits:
            for key in ireland_match_keys(name):
                self.names_by_key[key].add(name)

    @classmethod
    def from_directory(cls, directory: Path) -> "IrelandPermitRegistry":
        files = sorted(directory.glob(IRELAND_REGISTER_PATTERN)) if directory.exists() else []
        return cls(files)

    def _load(self, file: Path) -> None:
        import openpyxl  # imported lazily: only needed when the Irish files are present
        year_match = re.search(r"(20\d{2})", file.name)
        year = year_match.group(1) if year_match else "unknown"
        workbook = openpyxl.load_workbook(file, read_only=True, data_only=True)
        for row in workbook.worksheets[0].iter_rows(values_only=True):
            name = row[0] if row else None
            if not isinstance(name, str) or name.strip().casefold() in ("grand total", "employer name", ""):
                continue
            issued = sum(v for v in row[1:] if isinstance(v, (int, float)))
            if issued > 0:
                self.permits[name.strip()][year] += int(issued)
        workbook.close()

    def find(self, company: str) -> List[str]:
        names = set()
        for key in ireland_match_keys(company):
            names.update(self.names_by_key.get(key, set()))
        return sorted(names, key=str.casefold)

    def permits_for(self, names: List[str]) -> Dict[str, int]:
        totals: Dict[str, int] = defaultdict(int)
        for name in names:
            for year, count in self.permits[name].items():
                totals[year] += count
        return dict(sorted(totals.items()))


class VisaSponsorRegistry:
    def __init__(self, csv_path: Path, ireland: Optional["IrelandPermitRegistry"] = None):
        self.ireland = ireland
        self.csv_path = csv_path
        (
            self.companies,
            self.uk_places,
            self.company_names_by_key,
        ) = self._load_register()

    @classmethod
    def from_directory(cls, directory: Path, ireland_directory: Optional[Path] = None) -> "VisaSponsorRegistry":
        registers = sorted(directory.glob(REGISTER_FILENAME_PATTERN)) if directory.exists() else []
        ireland = IrelandPermitRegistry.from_directory(ireland_directory) if ireland_directory else None
        if not registers:
            instance = cls.__new__(cls)
            instance.ireland = ireland
            instance.csv_path = directory
            instance.companies = set()
            instance.uk_places = set()
            instance.company_names_by_key = {}
            return instance
        return cls(registers[-1], ireland)

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
        for part in re.split(r"[,;|•/&]+|\s+(?:or|and)\s+", text or "", flags=re.IGNORECASE):
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

    def job_in_ireland(self, location: str, description: str = "", is_remote: bool = False) -> bool:
        """True when the job's own location names Ireland or an Irish city (Northern Ireland is UK, not Ireland)."""
        text = re.sub(r"\bnorthern ireland\b", "", location or "", flags=re.IGNORECASE)
        if IRELAND_LOCATION_PATTERN.search(text):
            return True
        if not (location or "").strip() and (is_remote or REMOTE_PATTERN.search(description or "")):
            return any(
                REMOTE_PATTERN.search(sentence) and IRELAND_LOCATION_PATTERN.search(sentence)
                for sentence in re.split(r"[.!?;\n]+", description or "")
            )
        return False

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
            company = job.get("company") or ""
            location = job.get("location") or ""
            description = job.get("description") or ""
            is_remote = bool(job.get("is_remote"))
            sponsor_names = self.find_sponsor_names(company)
            employer_is_registered = bool(sponsor_names)
            location_status = self.job_location_status(location, description, is_remote)
            # Both conditions must hold: registered employer AND UK-confirmed location.
            # An overseas job for a registered employer is explicitly NOT badged.
            uk_sponsored = employer_is_registered and location_status == UK_CONFIRMED

            # Ireland: checked against the Irish employment-permit list, only for jobs located in Ireland.
            irish_names = self.ireland.find(company) if self.ireland else []
            job_is_irish = self.job_in_ireland(location, description, is_remote)
            permits = self.ireland.permits_for(irish_names) if irish_names else {}
            ie_sponsored = bool(irish_names) and job_is_irish

            visa_sponsored = uk_sponsored or ie_sponsored
            country = SPONSOR_COUNTRY if uk_sponsored else (IRELAND_COUNTRY if ie_sponsored else None)
            if uk_sponsored:
                disclaimer = (
                    "Employer is listed on the UK Worker and Temporary Worker Sponsor "
                    "Register for this location. This does not guarantee visa sponsorship "
                    "for this specific vacancy. Verify directly with the employer."
                )
            elif ie_sponsored:
                years = "–".join(sorted(permits)) if permits else ""
                disclaimer = (
                    f"Employer was issued {sum(permits.values()):,} Irish employment permits"
                    f"{f' in {years}' if years else ''} (Department of Enterprise, Trade and Employment). "
                    "Ireland has no sponsor licence register, so this shows the employer hires permit holders, "
                    "not that this vacancy is sponsored. Verify directly with the employer."
                )
            else:
                disclaimer = None
            annotated.append({
                **job,
                "visa_sponsor_registered": employer_is_registered,
                "visa_sponsor_registered_names": sponsor_names,
                "visa_sponsored": visa_sponsored,
                "visa_sponsor_country": country,
                "visa_sponsored_country_match": visa_sponsored,
                "visa_sponsor_location_status": location_status,
                "ireland_permit_registered": bool(irish_names),
                "ireland_permit_names": irish_names,
                "ireland_permits_issued": permits,
                "job_in_ireland": job_is_irish,
                # Explicit disclaimer: register listing != sponsorship for this vacancy.
                "visa_sponsor_disclaimer": disclaimer,
            })
        return annotated

"""Hiring-process discovery.

A stage is only ever created from a piece of evidence (a sentence in a real source).
No evidence → no stage. Confidence:

* officially_confirmed – stated by the job posting or an official company page;
* publicly_reported    – stated by a credible public report that matches this company and role family;
* estimated            – weaker evidence (company-level report for a different/unknown role, or outdated);
* unknown              – never produced for a stage (absence of evidence means no stage).
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from .fetcher import FetchResult, SafeFetcher, parse_page

OUTDATED_DAYS = 730
OFFICIAL, PUBLIC, ESTIMATED = "officially_confirmed", "publicly_reported", "estimated"
REVIEW_SITES = ("glassdoor.", "indeed.", "reddit.", "teamblind.", "levels.fyi", "leetcode.com", "ambitionbox.", "prepinsta.", "interviewing.io",
                "tryexponent.", "prepfully.", "medium.com", "geeksforgeeks.", "4dayweek.", "hackernoon.", "dev.to", "careercup.", "workable.com/interview",
                "wikijob.", "thestudentroom.", "jobtestprep.", "interviewquery.", "datalemur.", "hellointerview.", "igotanoffer.", "jointaro.", "linkedin.com/pulse")
SKIP_RESULT_SITES = ("youtube.", "youtu.be", "tiktok.", "facebook.", "instagram.", "pinterest.", "twitter.", "x.com")

# key, label, order, assessment_type, interview_format, regex
STAGES: List[Tuple[str, str, int, Optional[str], Optional[str], str]] = [
    ("application_screening", "Application and CV screening", 1, None, None,
     r"(application (?:review|screen\w*)|cv (?:review|screen\w*)|resume (?:review|screen\w*)|screen\w* (?:of )?(?:your )?(?:application|cv|resume)|review(?:ed)? (?:your )?(?:application|cv|resume))"),
    ("recruiter_screen", "Recruiter screening", 2, None, "Phone or video call",
     r"(recruiter (?:screen\w*|call|chat|conversation|interview)|initial (?:phone|video )?(?:screen\w*|call|chat)|phone screen|talent (?:acquisition|partner) (?:call|chat|screen\w*)|introductory call|screening call|(?:hr|recruiter|initial|first) (?:round|phone interview|interview)|phone interview|intro(?:ductory)? (?:call|chat|interview)|get[- ]to[- ]know[- ]you (?:call|chat))"),
    ("online_assessment", "Online assessment", 3, "Online assessment", "Online",
     r"(online (?:assessment|test)|aptitude test|numerical reasoning|verbal reasoning|logical reasoning|psychometric|hackerrank|codility|codesignal|testgorilla|situational judge?ment|coding (?:test|challenge|assessment)|(?:automated|pre-?employment|video) (?:assessment|interview)|one-?way video interview|hirevue|pymetrics|cognitive (?:test|assessment)|\bsjt\b)"),
    ("technical_assessment", "Technical assignment", 4, "Take-home / technical assignment", "Take-home or live exercise",
     r"(take-?home (?:\w+ )?(?:assignment|task|test|exercise|challenge|project)|technical (?:assignment|task|exercise|assessment)|case study|pair programming|live coding|design exercise|coding exercise|technical test|(?:programming|integration|debugging|bug[- ]?squash|bug[- ]?bash) (?:exercise|round|task)|bug[- ]?squash|homework (?:assignment|task)|work sample|practical (?:task|exercise|test)|case interview)"),
    ("technical_interview", "Technical interview", 5, None, "Video or on-site interview",
     r"(technical (?:interview|round|screen\w*|discussion|panel)|system design (?:interview|round)|coding interview|engineering interview|algorithms? (?:interview|round)|coding (?:round|screen\w*)|technical phone (?:screen|interview)|data structures? (?:and algorithms? )?(?:interview|round)|architecture (?:interview|round)|domain (?:interview|round)|sql (?:interview|round|test))"),
    ("hiring_manager", "Hiring manager interview", 6, None, "Video or on-site interview",
     r"(hiring manager (?:interview|call|round|chat|conversation)|meet(?:ing)? (?:with )?the hiring manager|manager (?:interview|round)|team (?:interview|fit|match)|team lead (?:interview|round)|managerial (?:interview|round)|(?:director|vp|skip[- ]level|senior leadership) (?:interview|round|chat)|meet (?:the|your) (?:future )?team)"),
    ("behavioural_interview", "Behavioural / values interview", 7, None, "Video or on-site interview",
     r"(behaviou?ral (?:interview|round|questions?)|values?[- ]based (?:interview|questions?)|competency[- ]based (?:interview|questions?)|culture (?:fit|interview|round)|leadership principles|cultural interview|bar[- ]raiser|values (?:interview|round|fit)|hr (?:interview|round)|star (?:method|format|stories))"),
    ("presentation", "Presentation round", 8, "Presentation", "Presentation to panel",
     r"(presentation (?:round|interview|to the panel|task)|present(?:ing)? (?:your|a) (?:work|project|case|solution)|portfolio (?:review|presentation)|case presentation|take-?home presentation)"),
    ("final_interview", "Final interview", 9, None, "Video or on-site interview",
     r"(final (?:interview|round|stage|panel)|on-?site (?:interview|round|loop)|virtual on-?site|interview loop|assessment cent(?:re|er)|super-?day|onsite|on-?site|panel (?:interview|round)|(?:last|closing) (?:interview|round))"),
    ("offer", "Offer", 10, None, None,
     r"(offer (?:stage|call|letter|is made|will be made|extended)|reference checks?|background checks?|we(?:'ll| will) (?:then )?(?:make|extend) (?:you )?an offer|offer (?:negotiation|discussion)|team matching|right[- ]to[- ]work checks?|pre-?employment (?:checks?|screening))"),
]
_CONTEXT = re.compile(r"(interview|assessment|process|stage|round|screen|step|test|application|hiring|recruit|candidate|assignment|exercise|challenge)", re.I)
_NEGATION = re.compile(r"\b(no|not|without|never|doesn'?t|don'?t|isn'?t|aren'?t|skip(?:s|ped)?)\b[^.]{0,40}$", re.I)
_STAGE_RX = {k: re.compile(rx, re.I) for k, _, _, _, _, rx in STAGES}
_STAGE_META = {k: (label, order, atype, fmt) for k, label, order, atype, fmt, _ in STAGES}
_ROLE_FAMILIES = {
    "engineering": r"(engineer|developer|software|devops|sre|backend|frontend|full[- ]?stack|platform|programmer|swe)",
    "data": r"(data|analytics|analyst|machine learning|\bml\b|scientist|bi\b)",
    "design": r"(designer|ux|ui\b|product design)",
    "product": r"(product manager|product owner)",
    "sales": r"(sales|account executive|business development)",
    "finance": r"(finance|accountant|audit|banking|analyst)",
}


def role_family(title: str) -> Optional[str]:
    for fam, rx in _ROLE_FAMILIES.items():
        if re.search(rx, title or "", re.I):
            return fam
    return None


def company_tokens(name: str) -> List[str]:
    stop = {"ltd", "limited", "inc", "plc", "llc", "group", "the", "uk", "co", "corp", "holdings", "technologies", "and"}
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 2 and t not in stop]


def mentions_company(text: str, name: str) -> bool:
    low = (text or "").lower()
    toks = company_tokens(name)
    return bool(toks) and all(t in low for t in toks[:2])


def root_domain(host: str) -> str:
    parts = (host or "").lower().split(":")[0].split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "gov", "ac") else ".".join(parts[-2:])


def sentences(text: str) -> List[str]:
    out = []
    for block in re.split(r"\n+", text or ""):
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", block) if s.strip())
    return out


def extract_stage_evidence(text: str) -> List[Dict[str, Any]]:
    """Sentences that explicitly describe a hiring stage. ``negated`` marks 'no X' statements."""
    found = []
    for s in sentences(text):
        if len(s) > 600 or not _CONTEXT.search(s):
            continue
        for key, rx in _STAGE_RX.items():
            m = rx.search(s)
            if not m:
                continue
            found.append({"stage": key, "evidence": s[:320], "negated": bool(_NEGATION.search(s[:m.start()])), "duration": extract_duration(s)})
    return found


_ROUND_LINE = re.compile(r"^\W{0,3}(?:(?:round|stage|step|phase|interview|call)\s*#?(\d{1,2})|(\d{1,2})[.)])\s*[:\-–—.)]?\s*(.{4,110}?)\s*$", re.I)
_ROUND_WORDS = re.compile(r"(interview|round|screen|call|chat|assessment|test|task|onsite|on-site|loop|presentation|exercise|challenge|review|check|offer|case|panel|pairing|assignment|discussion|session|quiz|project)", re.I)
_DURATION = re.compile(r"\b(\d{1,3})(?:\s*(?:-|–|to)\s*(\d{1,3}))?\s*(?:-|\s)?(min(?:ute)?s?|hours?|hrs?)\b", re.I)
_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_COUNT = re.compile(r"\b(\d{1,2}|three|four|five|six|seven|eight|nine|ten)[- ](?:\w+[- ]){0,2}(?:rounds?|stages?|steps?|phases?)\b", re.I)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48]


def match_canonical(text: str) -> Optional[str]:
    """Best-fitting known stage: the pattern matching the longest span wins (so 'technical phone screen' beats 'phone screen')."""
    best, best_len = None, 0
    for key, rx in _STAGE_RX.items():
        m = rx.search(text or "")
        if m and len(m.group(0)) > best_len:
            best, best_len = key, len(m.group(0))
    return best


def extract_rounds(text: str) -> List[Dict[str, Any]]:
    """Headings/list items such as ``Round 2: Bug squash`` or ``3. Hiring manager call``.

    Items that map onto a known stage are returned with that ``stage`` key; the rest become
    company-specific rounds (``stage`` is ``custom:<slug>``) so unusual steps are not lost.
    """
    out, seen, seen_keys = [], set(), {}
    for raw in (text or "").split("\n"):
        line = raw.strip()
        if not 8 <= len(line) <= 160:
            continue
        m = _ROUND_LINE.match(line)
        if not m:
            continue
        number, title = int(m.group(1) or m.group(2)), re.sub(r"\s+", " ", m.group(3)).strip(" :-–—.")
        if not _ROUND_WORDS.search(title) or len(title.split()) > 14:
            continue
        key, after = match_canonical(title), None
        label = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
        if key and key in seen_keys and seen_keys[key] != number:
            # the same kind of round again later in the process (e.g. "Second recruiter call"): keep it as its own round
            after, key = key, "custom:" + slug(label)
        elif not key:
            key = "custom:" + slug(label)
        if key.startswith("custom:") and (len(key) <= 7 or key in seen):
            continue
        if not key.startswith("custom:"):
            if (key, number) in seen:
                continue
            seen_keys[key] = number
        seen.add(key if key.startswith("custom:") else (key, number))
        out.append({"stage": key, "evidence": line[:320], "negated": False, "number": number, "after": after,
                    "label": title[:80] if key.startswith("custom:") else None})
    return out


def extract_duration(sentence: str) -> Optional[str]:
    m = _DURATION.search(sentence or "")
    if not m:
        return None
    unit = "min" if m.group(3).lower().startswith("min") else "h"
    return f"{m.group(1)}{'–' + m.group(2) if m.group(2) else ''} {unit}"


def extract_round_count(text: str) -> Optional[int]:
    counts = []
    for s in sentences(text):
        if not re.search(r"(interview|hiring|recruit|application|process)", s, re.I) or len(s) > 400:
            continue
        for m in _COUNT.finditer(s):
            v = m.group(1).lower()
            n = _NUM_WORDS.get(v) or (int(v) if v.isdigit() else 0)
            if 3 <= n <= 10:
                counts.append(n)
    return max(set(counts), key=counts.count) if counts else None


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class SearchProvider:
    """Interface: ``search(query, count)`` → [{url, title, snippet, published}]."""
    name = "none"

    def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        return []


class BraveSearch(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        r = requests.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": count},
                         headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"}, timeout=(4, 10))
        if r.status_code != 200:
            raise RuntimeError(f"search provider returned HTTP {r.status_code}")
        items = (r.json().get("web") or {}).get("results", [])
        return [{"url": i["url"], "title": i.get("title", ""), "snippet": re.sub(r"<[^>]+>", "", i.get("description", "")),
                 "published": (i.get("page_age") or "")[:10] or None} for i in items if i.get("url")]


class BraveHtmlSearch(SearchProvider):
    """Keyless fallback: reads the public Brave Search results page (no API key needed).

    Best effort only: the markup can change and heavy use may be rate-limited, in which case
    ``search`` raises and the caller records a note. ``BRAVE_SEARCH_API_KEY`` is more reliable.
    """
    name = "brave_html"
    UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

    def search(self, query: str, count: int = 6) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup
        r = requests.get("https://search.brave.com/search", params={"q": query, "source": "web"}, timeout=(4, 10),
                         headers={"User-Agent": self.UA, "Accept": "text/html", "Accept-Language": "en-GB,en;q=0.9"})
        if r.status_code != 200:
            raise RuntimeError(f"search page returned HTTP {r.status_code}")
        soup = BeautifulSoup(r.text, "html.parser")
        out = []
        for block in soup.select('div.snippet[data-type="web"]'):
            a = block.select_one("a[href^=http]")
            if not a:
                continue
            title = block.select_one(".search-snippet-title, .title")
            desc = block.select_one(".generic-snippet .content, .snippet-description, .content")
            text = desc.get_text(" ", strip=True) if desc else ""
            m = re.match(r"^(\d{1,2} \w+ \d{4}|\w+ \d{1,2}, \d{4})\s*[-–]\s*(.*)$", text)
            published = None
            if m:
                try:
                    published = datetime.strptime(m.group(1), "%d %B %Y" if m.group(1)[0].isdigit() else "%B %d, %Y").date().isoformat()
                except ValueError:
                    pass
                text = m.group(2)
            out.append({"url": a["href"], "title": title.get_text(" ", strip=True) if title else "", "snippet": text, "published": published})
            if len(out) >= count:
                break
        return out


def default_search() -> SearchProvider:
    key = os.getenv("BRAVE_SEARCH_API_KEY") or os.getenv("BRAVE_API_KEY")
    return BraveSearch(key) if key else BraveHtmlSearch()


CAREER_PATHS = ("/careers", "/jobs", "/careers/hiring-process", "/careers/interview-process", "/about/careers", "/join-us", "/how-we-hire")
LINK_HINT = re.compile(r"(hiring[- ]process|interview|how[- ]we[- ]hire|recruit|our[- ]process|application[- ]process|faq|early[- ]careers|graduate)", re.I)


class HiringResearcher:
    def __init__(self, fetcher: Optional[SafeFetcher] = None, search: Optional[SearchProvider] = None,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc), max_pages: int = 8, max_public: int = 14,
                 community: Optional[Callable[[str], List[Dict[str, Any]]]] = None):
        self.fetcher, self.search, self.now, self.max_pages, self.max_public = fetcher or SafeFetcher(), search or default_search(), now, max_pages, max_public
        self.community = community or self.community_threads

    # -------------------------------------------------------- company side
    def identify_website(self, company: str, known: Optional[str]) -> Tuple[Optional[str], Optional[FetchResult], List[str]]:
        """Verify the company's official site. A page that does not mention the company is rejected."""
        notes: List[str] = []
        candidates = [known] if known else []
        if not known:
            try:
                for r in self.search.search(f"{company} official website", 4):
                    h = (urlparse(r["url"]).hostname or "")
                    if any(t in h for t in company_tokens(company)[:1]) and not any(s in h for s in REVIEW_SITES):
                        candidates.append(f"https://{h}")
                        break
            except Exception as err:
                notes.append(f"Website search failed: {err}")
            toks = company_tokens(company)
            if toks and not candidates:
                candidates.append(f"https://www.{''.join(toks[:2])}.com")
        for url in candidates:
            res = self.fetcher.get(url)
            if res.ok and mentions_company(parse_page(res.html)["text"][:6000] + " " + (parse_page(res.html)["meta"]["title"]), company):
                fin = urlparse(res.final_url or url)
                return f"{fin.scheme}://{fin.netloc}", res, notes
            if known:
                notes.append(f"Official website {url} could not be verified ({res.link_status}).")
        if not candidates or not known:
            notes.append("The company's official website could not be identified with confidence.")
        return None, None, notes

    def company_pages(self, website: Optional[str], home: Optional[FetchResult]) -> List[FetchResult]:
        if not website:
            return []
        urls: List[str] = []
        if home and home.ok:
            for link in parse_page(home.html, home.final_url or website)["links"]:
                if root_domain(urlparse(link["url"]).hostname or "") == root_domain(urlparse(website).hostname or "") and \
                        (LINK_HINT.search(link["text"]) or LINK_HINT.search(urlparse(link["url"]).path) or re.search(r"career|jobs", urlparse(link["url"]).path, re.I)):
                    urls.append(link["url"].split("#")[0])
        base = website.rstrip("/")
        urls += [base + p for p in CAREER_PATHS]
        seen, ordered = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
        ordered = ordered[: self.max_pages]
        with ThreadPoolExecutor(max_workers=4) as ex:
            return list(ex.map(self.fetcher.get, ordered))

    # ----------------------------------------------------------- discovery
    def discover(self, company: str, job: Dict[str, Any], website: Optional[str], home: Optional[FetchResult]) -> Dict[str, Any]:  # noqa: C901
        title = job.get("title") or ""
        family = role_family(title)
        today = self.now().date()
        verified = today.isoformat()
        notes: List[str] = []
        checked: List[Dict[str, Any]] = []
        evidence: List[Dict[str, Any]] = []  # raw evidence rows

        def add(url, stype, official, text, published, link_status, role_match):
            if not any(c["url"] == url and c["type"] == stype for c in checked):
                checked.append({"url": url, "type": stype, "official": official, "status": link_status})
            for ev in extract_stage_evidence(text) + extract_rounds(text):
                evidence.append({**ev, "url": url, "source_type": stype, "official": official, "published": published,
                                 "link_status": link_status, "role_match": role_match})

        # 1. The job posting itself is the company's own statement about this role.
        if job.get("description"):
            add(job.get("url") or "job-posting", "job_posting", True, job["description"], job.get("posted_at"), "ok", True)
        else:
            notes.append("The job has no description text, so role-specific stages could not be read from the posting.")

        # 2. Official company pages.
        pages = self.company_pages(website, home)
        for res in pages:
            if not res.ok:
                if res.error not in (None, "blocked_by_robots") or res.status not in (404, 0):
                    checked.append({"url": res.url, "type": "official_page", "official": True, "status": res.link_status})
                continue
            parsed = parse_page(res.html, res.final_url)
            add(res.final_url or res.url, "official_page", True, parsed["text"], parsed["meta"]["published"], "ok", False)
        if website and not any(c["official"] and c["status"] == "ok" and c["type"] == "official_page" for c in checked):
            notes.append("No readable official hiring-process page was found on the company website.")

        # 3. Public candidate reports: search results, well-known interview-guide pages and community threads.
        round_counts: List[int] = []
        candidates = self.public_candidates(company, title, family, website, notes)

        def load(r):
            if r.get("text"):  # already-fetched content (e.g. API results)
                return r, None
            return r, self.fetcher.get(r["url"])
        with ThreadPoolExecutor(max_workers=4) as ex:
            for r, res in ex.map(load, candidates):
                text, published = (r.get("text") or "") + "\n" + r.get("snippet", "") + "\n" + r.get("title", ""), r.get("published")
                status = res.link_status if res else "ok"
                if res is not None:
                    if not res.ok:
                        if r.get("direct") and res.status in (0, 404, 403):
                            continue  # guessed guide URL that does not exist: not worth reporting
                        if not r.get("snippet"):
                            checked.append({"url": r["url"], "type": "public_article", "official": False, "status": status})
                            continue
                    else:
                        parsed = parse_page(res.html, res.final_url)
                        text = parsed["text"][:60000] + "\n" + text
                        published = parsed["meta"]["published"] or published
                if not mentions_company(text, company):
                    checked.append({"url": r["url"], "type": "rejected_wrong_company", "official": False, "status": status})
                    continue
                host = (urlparse(r["url"]).hostname or "").lower()
                stype = "candidate_experience" if any(s in host or s in r["url"] for s in REVIEW_SITES) else "public_article"
                match = bool(family and re.search(_ROLE_FAMILIES[family], text, re.I))
                add(r["url"], stype, False, text, published, status, match)
                n = extract_round_count(text)
                if n:
                    round_counts.append(n)
        if round_counts:
            common = max(set(round_counts), key=round_counts.count)
            notes.append(f"Public sources most often describe about {common} interview rounds in total ({len(round_counts)} source{'s' if len(round_counts) != 1 else ''} gave a count).")

        return {"stages": self._aggregate(evidence, family, today, verified), "notes": notes, "sources_checked": checked,
                "researched_at": self.now().isoformat()}

    GUIDE_SITES = ("interviewing.io/{c}-interview-questions", "prepfully.com/interview-guides/{c}-{r}", "www.tryexponent.com/guides/{c}-{r}-interview",
                   "4dayweek.io/interview-process/{c}-{r}", "www.tryexponent.com/guides/{c}-interview-process")
    FAMILY_SLUGS = {"engineering": ["software-engineer"], "data": ["data-scientist", "data-analyst"], "design": ["product-designer"],
                    "product": ["product-manager"], "sales": ["account-executive", "sales"], "finance": ["financial-analyst"]}

    def public_candidates(self, company: str, title: str, family: Optional[str], website: Optional[str], notes: List[str]) -> List[Dict[str, Any]]:
        """Pages that may describe the hiring process: search hits, guide-site pages, community threads."""
        official_root = root_domain(urlparse(website).hostname or "") if website else ""
        out: List[Dict[str, Any]] = []
        seen: set = set()

        def push(item):
            host = (urlparse(item["url"]).hostname or "").lower()
            if item["url"] in seen or any(x in host for x in SKIP_RESULT_SITES) or (official_root and root_domain(host) == official_root):
                return
            seen.add(item["url"])
            out.append(item)

        # a) direct pages on well-known interview-guide sites (no search engine needed)
        toks = company_tokens(company)
        cslug = "-".join(toks[:2]) if toks else ""
        if cslug:
            roles = [slug(title)] + self.FAMILY_SLUGS.get(family or "", [])
            for pattern in self.GUIDE_SITES:
                for r in ([None] if "{r}" not in pattern else dict.fromkeys(x for x in roles if x)):
                    push({"url": "https://" + pattern.format(c=cslug, r=r), "title": "", "snippet": "", "direct": True})

        # b) search engine results
        if self.search.name == "none":
            notes.append("Public interview reports were not searched because no search provider is configured (set BRAVE_SEARCH_API_KEY).")
        else:
            queries = [f"{company} {title} interview process", f"{company} {title} interview experience rounds",
                       f"{company} interview process stages", f"{company} hiring process how many rounds"]
            failures = 0
            for i, q in enumerate(queries):
                try:
                    for r in self.search.search(q, 8):
                        push(r)
                except Exception as err:
                    failures += 1
                    if failures == 1:
                        notes.append(f"Search engine lookup was limited ({err}); guide sites and community threads were still checked. "
                                     "Set BRAVE_SEARCH_API_KEY for more reliable search.")
                    if failures >= 2:
                        break
                if i < len(queries) - 1 and isinstance(self.search, BraveHtmlSearch):
                    time.sleep(0.6)

        # c) community threads (Hacker News)
        try:
            for r in self.community(company):
                push(r)
        except Exception as err:
            notes.append(f"Community thread lookup failed: {err}")

        def rank(r):
            host = r["url"]
            return (0 if r.get("direct") else 1 if any(x in host for x in REVIEW_SITES) else 2 if r.get("text") else 3)
        return sorted(out, key=rank)[: self.max_public]

    def community_threads(self, company: str) -> List[Dict[str, Any]]:
        """Hacker News posts/comments about interviewing at the company (official public API)."""
        res = requests.get("https://hn.algolia.com/api/v1/search", params={"query": f"{company} interview", "tags": "(story,comment)", "hitsPerPage": 25},
                           timeout=(4, 8))
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}")
        out = []
        for h in res.json().get("hits", []):
            text = re.sub(r"<[^>]+>", "\n", h.get("comment_text") or h.get("story_text") or "")
            text = re.sub(r"&#x27;|&#39;", "'", re.sub(r"&quot;", '"', re.sub(r"&amp;", "&", text)))
            if len(text) < 200 or not re.search(r"interview", text, re.I) or not mentions_company(text, company):
                continue
            out.append({"url": f"https://news.ycombinator.com/item?id={h['objectID']}", "title": h.get("story_title") or h.get("title") or "",
                        "snippet": "", "text": text, "published": (h.get("created_at") or "")[:10] or None})
        return out[:6]

    def _aggregate(self, evidence: List[Dict[str, Any]], family: Optional[str], today: date, verified: str) -> List[Dict[str, Any]]:
        by_stage: Dict[str, List[Dict[str, Any]]] = {}
        for ev in evidence:
            by_stage.setdefault(ev["stage"], []).append(ev)
        stages = []
        for key, evs in by_stage.items():
            positives = [e for e in evs if not e["negated"]]
            negatives = [e for e in evs if e["negated"]]
            if not positives:
                continue  # only "no X" statements: not a stage
            custom = key.startswith("custom:")
            if custom:
                label = positives[0]["label"] or key[7:].replace("-", " ").title()
                after = next((e["after"] for e in positives if e.get("after")), None)
                order = (_STAGE_META[after][1] + 0.5 if after else 5.5 + min(e.get("number") or 9 for e in positives) / 100)
                atype, fmt = (_STAGE_META[after][2], _STAGE_META[after][3]) if after else (None, None)
            else:
                label, order, atype, fmt = _STAGE_META[key]
            durations = [e["duration"] for e in positives if e.get("duration")]
            if durations:
                dur = max(set(durations), key=durations.count)
                fmt = f"{fmt} · reported {dur}" if fmt else f"Reported {dur}"
            status, scope, rank = ESTIMATED, "unknown", 0
            sources, seen_urls = [], set()
            for e in positives:
                pub = parse_date(e["published"])
                outdated = bool(pub and (today - pub).days > OUTDATED_DAYS)
                if e["official"] and not outdated:
                    s, sc, r = OFFICIAL, ("role_specific" if e["source_type"] == "job_posting" else "company_wide"), 3
                elif not e["official"] and e["role_match"] and not outdated:
                    s, sc, r = PUBLIC, "role_family", 2
                else:
                    s, sc, r = ESTIMATED, ("company_wide" if e["official"] else "unconfirmed_role"), 1
                if r > rank:
                    status, scope, rank = s, sc, r
                if (e["url"], e["evidence"]) in seen_urls:
                    continue
                seen_urls.add((e["url"], e["evidence"]))
                sources.append({"url": e["url"], "source_type": e["source_type"], "official": e["official"], "evidence": e["evidence"],
                                "published": e["published"], "last_verified": verified, "link_status": e["link_status"], "outdated": outdated})
            stages.append({"stage_key": key, "stage": label, "order": order, "custom": custom,
                           "description": "A round named by candidate reports or the company; not part of the standard process." if custom else None,
                           "reported_number": min((e.get("number") or 99) for e in positives) if custom else None,
                           "stage_key_": key, "assessment_type": atype, "interview_format": fmt,
                           "status": status, "scope": scope, "conflict": bool(negatives), "source_count": len({s["url"] for s in sources}),
                           "sources": sources[:6],
                           "note": ("Sources disagree: at least one source says this stage is not used." if negatives else None)})
        # Keep the most-evidenced company-specific rounds, then number everything in process order.
        extra = sorted((x for x in stages if x["custom"]), key=lambda x: -x["source_count"])[:6]
        stages = [x for x in stages if not x["custom"]] + extra
        stages.sort(key=lambda x: x["order"])
        for i, st in enumerate(stages, 1):
            st["order"] = i
            st.pop("stage_key_", None)
        return stages

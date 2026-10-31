"""Company facts (website, industry, headquarters, size, summary) from Wikidata / Wikipedia.

Both are public, keyless APIs. A candidate entity is only accepted when its name matches the
company and it looks like an organisation (it has a website, an industry or a headquarters), so
unrelated items that share a name are rejected. Every value is returned with its source URL.
"""
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "CafyResearchBot/1.0 (job research for candidates; respects robots.txt)"}
TIMEOUT = (4, 8)
SUFFIXES = {"inc", "ltd", "limited", "llc", "plc", "corp", "corporation", "group", "holdings", "co", "company", "the", "uk"}


def _norm(name: str) -> str:
    return " ".join(t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t and t not in SUFFIXES)


def _names_match(company: str, entity: Dict[str, Any]) -> bool:
    target = _norm(company)
    labels = [(entity.get("labels") or {}).get("en", {}).get("value", "")]
    labels += [a["value"] for a in (entity.get("aliases") or {}).get("en", [])]
    return bool(target) and any(_norm(l) == target or _norm(l).replace(" ", "") == target.replace(" ", "") for l in labels)


def _get(params: Dict[str, Any]) -> Dict[str, Any]:
    for attempt in range(4):
        r = requests.get(API, params={**params, "format": "json"}, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 429 and attempt < 3:
            time.sleep(min(float(r.headers.get("Retry-After") or 2 ** (attempt + 1)), 10))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


def _ids(claims: Dict[str, Any], prop: str) -> List[str]:
    return [c["mainsnak"]["datavalue"]["value"]["id"] for c in claims.get(prop, [])
            if c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")]


def _labels(ids: List[str]) -> Dict[str, str]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    ents = _get({"action": "wbgetentities", "ids": "|".join(ids[:40]), "props": "labels", "languages": "en"})["entities"]
    return {i: e.get("labels", {}).get("en", {}).get("value", "") for i, e in ents.items()}


def _latest_employees(claims: Dict[str, Any]) -> Optional[int]:
    best, best_date = None, ""
    for c in claims.get("P1128", []):
        try:
            raw = str(c["mainsnak"]["datavalue"]["value"]["amount"])
            # some entries wrongly use "." as a thousands separator ("+2.909" means 2,909)
            amount = int(raw.lstrip("+").replace(".", "")) if re.fullmatch(r"\+?\d{1,3}\.\d{3}", raw) else int(float(raw))
        except (KeyError, ValueError):
            continue
        when = ""
        for q in (c.get("qualifiers") or {}).get("P585", []):
            when = q.get("datavalue", {}).get("value", {}).get("time", "") or when
        if best is None or when > best_date:
            best, best_date = amount, when
    return best


def size_label(employees: Optional[int]) -> Optional[str]:
    if not employees:
        return None
    band = ("Small company" if employees < 50 else "Mid-sized company" if employees < 250 else "Large company" if employees < 5000 else "Enterprise")
    return f"{band} (about {employees:,} employees)"


def _summary(entity: Dict[str, Any]) -> Optional[str]:
    title = (entity.get("sitelinks") or {}).get("enwiki", {}).get("title")
    if not title:
        return None
    r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}", headers=HEADERS, timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    parts = re.split(r"(?<=[.!?])\s+", (r.json().get("extract") or "").strip())
    return " ".join(parts[:2]) or None


def _find_entity(company: str) -> Optional[Dict[str, Any]]:
    """First Wikidata item whose name matches and that looks like an organisation.

    A plain name search can bury the company under given names and people (searching "Okta" returns
    "Oktay" first), so a wider search is made, then "<name> Inc" and "<name> company" variants.
    """
    seen = set()
    for term in (company, f"{company} Inc", f"{company} company"):
        hits = _get({"action": "wbsearchentities", "search": term, "language": "en", "limit": 30, "type": "item"}).get("search", [])
        ids = [h["id"] for h in hits if h["id"] not in seen]
        seen.update(ids)
        if not ids:
            continue
        entities = _get({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels|aliases|sitelinks", "languages": "en"})["entities"]
        for item_id in ids:
            e = entities.get(item_id) or {}
            claims = e.get("claims") or {}
            if _names_match(company, e) and (claims.get("P856") or claims.get("P452") or claims.get("P159")):
                return e
    return None


def lookup_company(company: str) -> Optional[Dict[str, Any]]:
    """Facts for ``company`` or ``None`` when no matching organisation is found."""
    chosen = _find_entity(company)
    if not chosen:
        return None
    claims = chosen["claims"]
    website = next((c["mainsnak"]["datavalue"]["value"] for c in claims.get("P856", []) if c.get("mainsnak", {}).get("datavalue")), None)
    hq_ids, industry_ids = _ids(claims, "P159"), _ids(claims, "P452")
    hq = None
    if hq_ids:
        hq_entity = _get({"action": "wbgetentities", "ids": hq_ids[0], "props": "claims|labels", "languages": "en"})["entities"][hq_ids[0]]
        country_ids = _ids(hq_entity.get("claims") or {}, "P17")
        names = _labels([hq_ids[0]] + country_ids[:1])
        hq = ", ".join(n for n in (names.get(hq_ids[0]), names.get(country_ids[0]) if country_ids else None) if n) or None
    industries = [v for v in _labels(industry_ids[:4]).values() if v]
    industries = [v for v in industries if not any(v != o and v.lower() in o.lower() for o in industries)]  # drop "tourism" when "tourism industry" is present
    return {
        "name": chosen.get("labels", {}).get("en", {}).get("value"),
        "website": website.rstrip("/") if website else None,
        "industry": ", ".join(i.capitalize() if i.islower() else i for i in industries) or None,
        "headquarters": hq,
        "company_size": size_label(_latest_employees(claims)),
        "overview": _summary(chosen),
        "source_url": f"https://www.wikidata.org/wiki/{chosen['id']}",
    }

#!/usr/bin/env python3
"""
Discover which UK visa-sponsor employers run a public ATS job board, and how many
UK jobs each one has. Built to run unattended overnight.

How it works
  1. Read the Home Office sponsor register (backend/sponsor-data/*.csv).
  2. Turn every organisation name into candidate board slugs ("Trading 212 UK Ltd" -> trading212).
  3. Probe the public job-board APIs of Greenhouse, Lever, Ashby, SmartRecruiters and Workable.
  4. Keep boards that exist and count their UK jobs with the project's own location filter.
  5. Merge boards that have UK jobs into backend/scrapers/sources.yaml.

Usage
  pip install aiohttp pyyaml truststore
  python discover_employers.py                       # full register, 1000 requests/sec, resumable
  python discover_employers.py --rate 400            # gentler if you see lots of 429s
  python discover_employers.py --limit 500 --no-merge   # quick smoke test
  python discover_employers.py --merge-only          # just merge results found so far

Results land in discovery_output/ (hits.jsonl, state.json, summary.json). Re-running resumes
where it stopped. Ctrl-C is safe: progress is flushed first.

Note: 1000 req/s is the *target*. The script slows itself down automatically when a host
answers 429 / 5xx, so the real speed depends on what the ATS providers tolerate.
"""
import argparse
import asyncio
import csv
import glob
import json
import logging
import os
import re
import shutil
import signal
import ssl
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    from backend.scrapers.job_normalizer import JobNormalizer

    is_uk = JobNormalizer.is_uk_location
except Exception:  # standalone fallback so the script still works on its own
    _UK = re.compile(
        r"\b(?:u\.?k\.?|united kingdom|great britain|britain|england|scotland|wales|northern ireland|"
        r"london|edinburgh|manchester|glasgow|belfast|cardiff|"
        r"bristol|birmingham|leeds|cambridge|oxford)\b",
        re.I,
    )

    def is_uk(loc: str) -> bool:
        return bool(loc and _UK.search(loc))


log = logging.getLogger("discover")

LEGAL_NOISE = re.compile(
    r"\b(limited|ltd|plc|llp|llc|lp|inc|incorporated|corp|corporation|unlimited|uk|u\.k\.|gb|ireland|emea|group|"
    r"holdings|the|company|co|services|international|europe|european|london|trading|as)\b"
)
# "Toasttab UK Limited T/A Toast": the trading name is usually what the job board is called.
TRADING_AS = re.compile(r"\b(?:t\s*/\s*as?|trading\s+as)\b\.?", re.I)
# Words that describe the business rather than name it. Job boards almost always use the bare brand
# ("Monzo Bank" -> monzo, "Palantir Technologies" -> palantir, "Deliveroo Hop" -> deliveroo).
DESCRIPTORS = {
    "bank", "payments", "payment", "technologies", "technology", "tech", "software", "solutions", "systems",
    "innovation", "innovations", "labs", "lab", "digital", "financial", "finance", "consulting", "hop", "ai",
    "platforms", "platform", "networks", "studios", "ventures", "operations", "management", "research",
}
MIN_UNVERIFIED_BRAND_LEN = 5


def _tokens(name: str):
    t = re.sub(r"\(.*?\)", " ", name.lower())
    t = t.replace("&", " and ")
    t = re.sub(r"[']", "", t)
    t = LEGAL_NOISE.sub(" ", t)
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", t).split() if len(w) > 1]  # drops "l"/"p" from "L.P."


def _join(tokens):
    return {"".join(tokens), "-".join(tokens)}


def _valid(slug: str) -> bool:
    return 3 <= len(slug) <= 40 and not slug.isdigit()


def slug_candidates(name: str):
    """``{slug: kind}`` where kind is ``exact`` (the whole cleaned name) or ``brand`` (a shortened guess
    that must be verified before it is trusted, because it can collide with another company's board)."""
    legal, *trading = TRADING_AS.split(name)
    out = {}
    for part in [legal, *trading]:
        tokens = _tokens(part)
        if not tokens:
            continue
        for s in _join(tokens):
            out[s] = "exact"
        brand = list(tokens)
        while len(brand) > 1 and brand[-1] in DESCRIPTORS:
            brand.pop()
        if brand != tokens:
            for s in _join(brand):
                out.setdefault(s, "brand")
    return {s: k for s, k in out.items() if _valid(s)}


def slugs_for(name: str):
    return sorted(slug_candidates(name))


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def board_name_matches(board_name: str, slug: str) -> bool:
    """A shortened slug is trusted only when the board's own company name reduces to that same brand
    ("Palantir Technologies" -> palantir matches; "Wise Owl Media" does not match "wise")."""
    tokens = _tokens(board_name or "")
    while len(tokens) > 1 and tokens[-1] in DESCRIPTORS:
        tokens.pop()
    return bool(tokens) and "".join(tokens) == _norm(slug)


# --------------------------------------------------------------------------- platforms
# Each probe returns a list of location strings (one per job) or None when the board
# does not exist / is empty.

class Locations(list):
    """Job locations of a board, plus the board's own company name when the platform reports one."""
    board_name = None


async def board_name(platform, fetch, slug, locs):
    """The company name a board reports about itself, or None where the platform has no such field."""
    if platform == "greenhouse":
        d = await fetch(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
        return d.get("name") if isinstance(d, dict) else None
    return getattr(locs, "board_name", None)


async def p_greenhouse(fetch, slug):
    d = await fetch(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    jobs = d.get("jobs") if isinstance(d, dict) else None
    return [(j.get("location") or {}).get("name", "") for j in jobs] if jobs else None


async def p_lever(fetch, slug):
    d = await fetch(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if isinstance(d, list) and d:
        return [(j.get("categories") or {}).get("location") or "" for j in d]
    return None


async def p_ashby(fetch, slug):
    d = await fetch(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = d.get("jobs") if isinstance(d, dict) else None
    if not jobs:
        return None
    out = []
    for j in jobs:
        locs = [j.get("location") or ""] + [
            (x or {}).get("location") or "" for x in (j.get("secondaryLocations") or [])
        ]
        out.append("; ".join(l for l in locs if l))
    return out


async def p_smartrecruiters(fetch, slug):
    d = await fetch(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    if not isinstance(d, dict) or not d.get("content"):
        return None
    out = Locations()
    out.board_name = ((d["content"][0].get("company") or {}).get("name"))
    for j in d["content"]:
        loc = j.get("location") or {}
        country = {"gb": "United Kingdom", "uk": "United Kingdom", "ie": "Ireland"}.get(
            (loc.get("country") or "").lower(), loc.get("country") or ""
        )
        out.append(f"{loc.get('city', '')}, {country}")
    # extra pages only for boards that exist (rare), so the cost is negligible
    total = d.get("totalFound", 0)
    offset = 100
    while offset < min(total, 1000):
        more = await fetch(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
        )
        if not isinstance(more, dict) or not more.get("content"):
            break
        for j in more["content"]:
            loc = j.get("location") or {}
            country = {"gb": "United Kingdom", "uk": "United Kingdom", "ie": "Ireland"}.get(
                (loc.get("country") or "").lower(), loc.get("country") or ""
            )
            out.append(f"{loc.get('city', '')}, {country}")
        offset += 100
    return out


async def p_workable(fetch, slug):
    d = await fetch(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    jobs = d.get("jobs") if isinstance(d, dict) else None
    if not jobs or (str(d.get("name", "")).strip().lower() == "workable" and slug != "workable"):
        return None  # Workable answers unknown names with its own board
    return [f"{j.get('city', '')}, {j.get('state', '')}, {j.get('country', '')}" for j in jobs]


PLATFORMS = {
    "greenhouse": p_greenhouse,
    "lever": p_lever,
    "ashby": p_ashby,
    "smartrecruiters": p_smartrecruiters,
    "workable": p_workable,
}
# Board names on these platforms are plain letters/digits ("wppmedia", "BoschGroup"); hyphenated guesses never exist.
NO_HYPHEN_PLATFORMS = {"greenhouse", "smartrecruiters"}
HOST_OF = {
    "greenhouse": "boards-api.greenhouse.io",
    "lever": "api.lever.co",
    "ashby": "api.ashbyhq.com",
    "smartrecruiters": "api.smartrecruiters.com",
    "workable": "apply.workable.com",
}


# --------------------------------------------------------------------------- rate control
class HostLimiter:
    """Token bucket per ATS host. Backs off when the host pushes back, creeps back up when calm."""

    def __init__(self, rate: float, floor: float = 5.0):
        self.max_rate = rate
        self.rate = rate
        self.floor = floor
        self.tokens = rate
        self.stamp = time.monotonic()
        self.lock = asyncio.Lock()
        self.pushback = 0
        self.calm = 0

    async def acquire(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.rate, self.tokens + (now - self.stamp) * self.rate)
                self.stamp = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)

    def report(self, status: int):
        if status == 429 or status >= 500:
            self.pushback += 1
            self.calm = 0
            if self.pushback >= 5:
                self.rate = max(self.floor, self.rate * 0.7)
                self.pushback = 0
        else:
            self.calm += 1
            if self.calm >= 500 and self.rate < self.max_rate:
                self.rate = min(self.max_rate, self.rate * 1.15)
                self.calm = 0


# Sector presets: match on the organisation name (the register has no industry column).
SECTOR_PATTERNS = {
    "education": r"\b(school|academy|academies|college|university|nursery|education|learning|tutor|training|institute)\b",
    "health": r"\b(hospital|nhs|health|healthcare|care|clinic|medical|dental|pharma|pharmacy|therapy|nursing|surgery|hospice)\b",
    "finance": r"\b(accountan\w*|audit|capital|bank|banking|financ\w*|insurance|invest\w*|wealth|asset|advisory|tax|payments|credit|lending|mortgage)\b",
    "engineering": r"\b(engineering|engineers|manufactur\w*|electronics|electrical|mechanical|automotive|aerospace|construction|robotics|semiconductor|devices|instruments|systems|technologies)\b",
    "legal": r"\b(law|legal|solicitors|chambers|barristers)\b",
    "marketing": r"\b(marketing|media|creative|design|agency|communications|advertising|studio|publishing)\b",
    "operations": r"\b(logistics|supply|freight|retail|hospitality|hotel|foods|energy|utilities|facilities|recruitment|staffing|consulting)\b",
}


# --------------------------------------------------------------------------- main run
class Runner:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.hits_path = self.out / "hits.jsonl"
        self.state_path = self.out / "state.json"
        self.stop = False
        self.stats = Counter()
        self.limiters = {}
        self.session = None
        self.hits_fh = None

    # ---- input
    def load_orgs(self):
        files = glob.glob(str(ROOT / "backend" / "sponsor-data" / "*.csv"))
        if not files:
            sys.exit("No CSV found in sponsor-data/")
        names = set()
        with open(sorted(files)[-1], encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if "Skilled Worker" in (row.get("Route") or ""):
                    names.add(row["Organisation Name"].strip())
        sectors = [x.strip() for x in (getattr(self.args, "sectors", "") or "").split(",") if x.strip()]
        if sectors:
            keys = list(SECTOR_PATTERNS) if "all" in sectors else sectors
            unknown = [k for k in keys if k not in SECTOR_PATTERNS]
            if unknown:
                sys.exit(f"unknown sector(s) {unknown}; choose from {list(SECTOR_PATTERNS)} or 'all'")
            pat = re.compile("|".join(SECTOR_PATTERNS[k] for k in keys), re.I)
            names = {n for n in names if pat.search(n)}
            log.info("sector filter %s kept %d orgs", keys, len(names))
        slug_orgs = defaultdict(list)  # slug -> [(organisation, "exact" | "brand"), ...]
        for n in sorted(names):
            for s, kind in slug_candidates(n).items():
                slug_orgs[s].append((n, kind))
        log.info("%d sponsor orgs -> %d unique slugs", len(names), len(slug_orgs))
        return slug_orgs

    def load_state(self):
        self.done = {p: set() for p in PLATFORMS}
        if self.state_path.exists():
            st = json.loads(self.state_path.read_text())
            for p, v in st.get("done", {}).items():
                self.done.setdefault(p, set()).update(v)
        log.info("resuming: %s", {p: len(v) for p, v in self.done.items() if v})

    def save_state(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"done": {p: sorted(v) for p, v in self.done.items()}}))
        tmp.replace(self.state_path)

    # ---- http
    async def fetch(self, platform, url):
        lim = self.limiters[platform]
        for attempt in range(3):
            await lim.acquire()
            try:
                async with self.session.get(url) as r:
                    lim.report(r.status)
                    self.stats["requests"] += 1
                    if r.status == 200:
                        return await r.json(content_type=None)
                    if r.status in (404, 400, 403, 410, 422):
                        return None
                    if r.status == 429 or r.status >= 500:
                        self.stats["pushback"] += 1
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    return None
            except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError):
                self.stats["errors"] += 1
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def probe_slug(self, platform, slug, orgs):
        async def f(url):
            return await self.fetch(platform, url)

        try:
            locs = await PLATFORMS[platform](f, slug)
        except Exception as e:  # never let one odd payload kill the run
            log.debug("probe error %s/%s: %s", platform, slug, e)
            locs = None
        org, kind = None, None
        if locs:
            org, kind = await self.accept(platform, f, slug, orgs, locs)
        if org:
            uk = sum(1 for l in locs if is_uk(l))
            self.hits_fh.write(json.dumps({
                "platform": platform, "slug": slug, "org": org, "total": len(locs), "uk_ie": uk, "kind": kind,
            }) + "\n")
            self.hits_fh.flush()
            self.stats["boards"] += 1
            self.stats["uk_ie_jobs"] += uk
            if uk:
                self.stats["boards_with_uk"] += 1
        self.done[platform].add(slug)
        self.stats["slugs_done"] += 1

    async def accept(self, platform, fetch, slug, entries, locs):
        """Decide whether a found board really belongs to the register employer. Returns (org, kind) or (None, None)."""
        exact = [o for o, k in entries if k == "exact"]
        if exact:
            return exact[0], "exact"
        orgs = sorted({o for o, _ in entries})
        try:
            name = await board_name(platform, fetch, slug, locs)
        except Exception:
            name = None
        if name is not None:  # the platform tells us who owns the board
            if board_name_matches(name, slug):
                return orgs[0], "brand-verified"
        elif len(orgs) == 1 and len(slug.replace("-", "")) >= MIN_UNVERIFIED_BRAND_LEN:
            return orgs[0], "brand-unique"  # no name to check: only an unambiguous, distinctive brand
        self.stats["brand_rejected"] += 1
        return None, None

    async def worker(self, queue, platform):
        while True:
            item = await queue.get()
            if item is None:
                return
            if self.stop:
                continue  # drain quickly so shutdown never blocks on a full queue
            await self.probe_slug(platform, *item)

    async def reporter(self, platform, total, started):
        last_req, last_t = 0, time.monotonic()
        while True:
            await asyncio.sleep(10)
            now = time.monotonic()
            rps = (self.stats["requests"] - last_req) / (now - last_t)
            last_req, last_t = self.stats["requests"], now
            done = self.stats["slugs_done"]
            eta = (total - done) / (done / (now - started)) / 60 if done else float("inf")
            log.info(
                "[%s] %d/%d | %.0f req/s (limit %.0f) | boards %d, with UK %d, UK jobs %d | "
                "429/5xx %d | err %d | ETA %.0f min",
                platform, done, total, rps, self.limiters[platform].rate, self.stats["boards"],
                self.stats["boards_with_uk"], self.stats["uk_ie_jobs"], self.stats["pushback"],
                self.stats["errors"], eta,
            )
            self.save_state()

    async def run_platform(self, platform, slug_orgs):
        todo = [(s, o) for s, o in slug_orgs.items() if s not in self.done[platform]]
        if platform in NO_HYPHEN_PLATFORMS:
            todo = [(s, o) for s, o in todo if "-" not in s]
        if getattr(self.args, "only_brand", False):
            todo = [(s, o) for s, o in todo if all(k == "brand" for _, k in o)]
        if self.args.limit:
            todo = todo[: self.args.limit]
        if not todo:
            log.info("[%s] nothing left to probe", platform)
            return
        log.info("[%s] probing %d slugs at up to %.0f req/s", platform, len(todo), self.args.rate)
        self.limiters[platform] = HostLimiter(self.args.rate)
        self.stats["slugs_done"] = 0
        started = time.monotonic()
        queue = asyncio.Queue(maxsize=self.args.concurrency * 2)
        workers = [asyncio.create_task(self.worker(queue, platform)) for _ in range(self.args.concurrency)]
        rep = asyncio.create_task(self.reporter(platform, len(todo), started))
        try:
            for item in todo:
                if self.stop:
                    break
                await queue.put(item)
        finally:
            for _ in workers:
                await queue.put(None)
            await asyncio.gather(*workers)
            rep.cancel()
            self.save_state()
        log.info("[%s] finished: %s", platform, dict(self.stats))

    async def run(self):
        args = self.args
        platforms = [p for p in args.platforms.split(",") if p in PLATFORMS]
        slug_orgs = self.load_orgs()
        self.load_state()
        try:
            import truststore

            ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except Exception:
            ctx = ssl.create_default_context()
        conn = aiohttp.TCPConnector(
            limit=args.concurrency, limit_per_host=args.concurrency, ttl_dns_cache=600, ssl=ctx,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=20, connect=8)
        headers = {"User-Agent": "cafy-agent-discovery/1.0 (+job board indexing)", "Accept": "application/json"}
        self.hits_fh = open(self.hits_path, "a")
        try:
            async with aiohttp.ClientSession(connector=conn, timeout=timeout, headers=headers) as self.session:
                # one platform at a time: each gets the full request budget and a slow or
                # throttling provider can never drag the others down
                for platform in platforms:
                    if self.stop:
                        break
                    await self.run_platform(platform, slug_orgs)
        finally:
            self.hits_fh.close()


# --------------------------------------------------------------------------- merge
def read_hits(path):
    best = {}
    if not Path(path).exists():
        return []
    with open(path) as fh:
        for line in fh:
            try:
                h = json.loads(line)
            except Exception:
                continue
            best[(h["platform"], h["slug"])] = h
    return list(best.values())


def merge_into_sources(out_dir, min_uk=1, include_brand=False, exclude=()):
    """Add boards with UK jobs to sources.yaml.

    Brand-name guesses ("Monzo Bank Ltd" -> monzo) are skipped unless ``include_brand`` is set: a shared word can
    point at a different company (e.g. "Philo Consulting" vs the Philo TV board), so review them first and pass the
    rejects as ``exclude`` ("platform:slug").
    """
    import yaml

    skip = {e.strip() for e in exclude if e.strip()}
    hits = [h for h in read_hits(Path(out_dir) / "hits.jsonl")
            if h["uk_ie"] >= min_uk
            and (include_brand or not str(h.get("kind", "exact")).startswith("brand"))
            and f"{h['platform']}:{h['slug']}" not in skip]
    path = ROOT / "backend" / "scrapers" / "sources.yaml"
    cfg = yaml.safe_load(path.read_text())
    plats = cfg["platforms"]
    shutil.copy(path, path.with_suffix(f".yaml.bak-{int(time.time())}"))
    added = Counter()
    for h in sorted(hits, key=lambda x: -x["uk_ie"]):
        p = h["platform"]
        if p not in plats:
            plats[p] = {"name": p.title(), "color": "#64748B", "companies": []}
        have = {c.get("token") for c in plats[p].get("companies", [])}
        if h["slug"] in have:
            continue
        plats[p].setdefault("companies", []).append({"token": h["slug"], "name": h["org"]})
        added[p] += 1
    path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=200))
    summary = {
        "boards_found": len(read_hits(Path(out_dir) / "hits.jsonl")),
        "boards_with_uk_ie_jobs": len(hits),
        "uk_ie_jobs_total": sum(h["uk_ie"] for h in hits),
        "added_to_sources_yaml": dict(added),
        "top_20": sorted(hits, key=lambda h: -h["uk_ie"])[:20],
    }
    (Path(out_dir) / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "top_20"}, indent=2))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rate", type=float, default=1000, help="target requests/sec per platform (default 1000)")
    ap.add_argument("--concurrency", type=int, default=500, help="parallel connections (default 500)")
    ap.add_argument("--platforms", default="greenhouse,ashby,lever,smartrecruiters",
                    help="comma list from: " + ",".join(PLATFORMS) + " (workable throttles hard, so it is opt-in)")
    ap.add_argument("--sectors", default="",
                    help="only probe employers whose name suggests these sectors: "
                         + ",".join(SECTOR_PATTERNS) + " or 'all' (non-tech coverage: schools, health, finance, ...)")
    ap.add_argument("--limit", type=int, default=0, help="only probe the first N slugs (testing)")
    ap.add_argument("--only-brand", action="store_true",
                    help="only probe shortened brand guesses (\"Monzo Bank Ltd\" -> monzo): the cheapest, highest-yield pass")
    ap.add_argument("--out", default=str(ROOT / "discovery_output"))
    ap.add_argument("--no-merge", action="store_true", help="do not touch sources.yaml at the end")
    ap.add_argument("--merge-only", action="store_true", help="skip discovery, just merge hits.jsonl")
    ap.add_argument("--include-brand", action="store_true",
                    help="also merge brand-name guesses (review them first; see merge_into_sources)")
    ap.add_argument("--exclude", default="", help="comma list of platform:slug boards never to merge (rejected in review)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    if args.merge_only:
        merge_into_sources(args.out, include_brand=args.include_brand, exclude=args.exclude.split(","))
        return

    # macOS/Linux default of 256 open files would cap us far below 1000 connections
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = min(hard if hard != resource.RLIM_INFINITY else 65536, args.concurrency * 2 + 256)
        if soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except Exception as e:
        log.warning("could not raise open-file limit: %s", e)

    runner = Runner(args)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _stop(*_):
        log.warning("stop requested - flushing progress, finishing in-flight requests...")
        runner.stop = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass
    try:
        loop.run_until_complete(runner.run())
    finally:
        loop.close()
    if not args.no_merge:
        merge_into_sources(args.out, include_brand=args.include_brand, exclude=args.exclude.split(","))
    print(f"\nDone. Results in {args.out}/ . Restart the app and run a scrape to load the new jobs.")


if __name__ == "__main__":
    main()

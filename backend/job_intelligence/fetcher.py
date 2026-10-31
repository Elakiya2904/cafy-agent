"""Guarded HTTP fetching for company research.

* only http(s); redirects are followed manually and re-validated;
* hosts resolving to private/loopback/link-local addresses are refused (SSRF);
* robots.txt is honoured; responses are size- and time-limited;
* failures are returned as data (``error``), never raised, so broken links are reportable.
"""
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

USER_AGENT = "CafyResearchBot/1.0 (+job research for candidates; respects robots.txt)"
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3


@dataclass
class FetchResult:
    url: str
    final_url: str = ""
    status: int = 0
    html: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300 and bool(self.html)

    @property
    def link_status(self) -> str:
        return "ok" if self.ok else (self.error or f"http_{self.status}")


def host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


class SafeFetcher:
    def __init__(self, timeout=(4, 8)):
        self.timeout = timeout
        self._robots: Dict[str, Optional[RobotFileParser]] = {}

    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = requests.get(base + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=self.timeout)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[base] = rp
                else:
                    self._robots[base] = None  # no robots file: allowed
            except requests.RequestException:
                self._robots[base] = None
        rp = self._robots[base]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> FetchResult:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            p = urlparse(current)
            if p.scheme not in ("http", "https") or not p.hostname:
                return FetchResult(url, error="invalid_url")
            if not host_is_public(p.hostname):
                return FetchResult(url, error="blocked_host")
            if not self._allowed(current):
                return FetchResult(url, error="blocked_by_robots")
            try:
                r = requests.get(current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                                 timeout=self.timeout, allow_redirects=False, stream=True)
            except requests.Timeout:
                return FetchResult(url, error="timeout")
            except requests.RequestException:
                return FetchResult(url, error="unreachable")
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                current = urljoin(current, r.headers["Location"])
                r.close()
                continue
            if "html" not in (r.headers.get("Content-Type") or "").lower() and r.status_code == 200:
                r.close()
                return FetchResult(url, current, r.status_code, error="not_html")
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    break
            r.close()
            return FetchResult(url, current, r.status_code, body.decode(r.encoding or "utf-8", "replace"))
        return FetchResult(url, error="too_many_redirects")


def parse_page(html: str, base_url: str = "") -> Dict[str, Any]:
    """Text + metadata + links from an HTML page."""
    soup = BeautifulSoup(html or "", "html.parser")
    meta: Dict[str, Any] = {"title": (soup.title.string or "").strip() if soup.title and soup.title.string else "", "description": None,
                            "published": None, "org": {}}
    for tag in soup.find_all("meta"):
        key = (tag.get("property") or tag.get("name") or "").lower()
        if key in ("description", "og:description") and not meta["description"]:
            meta["description"] = (tag.get("content") or "").strip() or None
        if key in ("article:published_time", "datepublished", "date", "og:updated_time", "article:modified_time") and not meta["published"]:
            meta["published"] = (tag.get("content") or "")[:10] or None
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if not isinstance(item, dict):
                continue
            if item.get("datePublished") and not meta["published"]:
                meta["published"] = str(item["datePublished"])[:10]
            if item.get("@type") in ("Organization", "Corporation", "LocalBusiness") and not meta["org"]:
                addr = item.get("address") or {}
                meta["org"] = {"name": item.get("name"), "description": item.get("description"),
                               "address": ", ".join(str(addr.get(k)) for k in ("addressLocality", "addressCountry") if isinstance(addr, dict) and addr.get(k))}
    if not meta["published"]:
        t = soup.find("time", attrs={"datetime": True})
        if t:
            meta["published"] = t["datetime"][:10]
    links = [{"url": urljoin(base_url, a["href"]), "text": a.get_text(" ", strip=True)} for a in soup.find_all("a", href=True)]
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "svg", "form"]):
        tag.decompose()
    text = re.sub(r"[ \t\r\f\v]+", " ", soup.get_text("\n"))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return {"text": text, "meta": meta, "links": links}

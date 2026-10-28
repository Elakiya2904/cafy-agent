import time
import logging
from typing import Dict, Any, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("cafy.scrapers.base")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

class BaseScraper:
    """
    Base scraper providing robust HTTP handling with exponential backoff retries,
    rate limiting, timeout controls, and structured error logging.
    Strictly returns real job listings or empty lists (no synthetic fallbacks).
    """

    platform_name: str = "base"

    def __init__(self, timeout: int = 15, max_retries: int = 3, backoff_factor: float = 0.5, delay_between_requests: float = 0.2):
        self.timeout = timeout
        self.delay_between_requests = delay_between_requests
        self.session = requests.Session()

        # Exponential backoff retry strategy for transient errors (429, 500, 502, 503, 504)
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "HEAD"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9"
        })

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        """Performs a rate-limited GET request with error handling."""
        if self.delay_between_requests > 0:
            time.sleep(self.delay_between_requests)
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            logger.warning(f"[{self.platform_name}] HTTP error {e.response.status_code} requesting {url}: {e}")
        except requests.exceptions.Timeout:
            logger.warning(f"[{self.platform_name}] Request timed out after {self.timeout}s for {url}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"[{self.platform_name}] Network error requesting {url}: {e}")
        return None

    def post(self, url: str, json: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[requests.Response]:
        """Performs a rate-limited POST request with error handling."""
        if self.delay_between_requests > 0:
            time.sleep(self.delay_between_requests)
        try:
            resp = self.session.post(url, json=json, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            logger.warning(f"[{self.platform_name}] HTTP error {e.response.status_code} posting to {url}: {e}")
        except requests.exceptions.Timeout:
            logger.warning(f"[{self.platform_name}] POST timed out after {self.timeout}s for {url}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"[{self.platform_name}] Network error posting to {url}: {e}")
        return None

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scrape jobs for a single company board. Must be implemented by subclasses."""
        raise NotImplementedError

    def scrape_all(self, companies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Scrape jobs across all configured companies for this platform."""
        all_jobs = []
        for comp in companies:
            try:
                jobs = self.scrape_company(comp)
                all_jobs.extend(jobs)
            except Exception as e:
                logger.error(f"[{self.platform_name}] Unexpected error scraping {comp.get('name', 'unknown')}: {e}")
        return all_jobs

import logging
from typing import List, Dict, Any
from .base_scraper import BaseScraper
from .job_normalizer import JobNormalizer

logger = logging.getLogger("cafy.scrapers.oracle_cloud")

class OracleCloudScraper(BaseScraper):
    platform_name = "oracle_cloud"

    def scrape_company(self, company_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        token = company_config.get("token", "").strip()
        name = company_config.get("name", token.title()).strip()
        host = company_config.get("host", "").strip()
        site_id = company_config.get("site_id", "CX")

        if not host:
            logger.warning(f"[OracleCloud] No host specified for company '{name}'")
            return []

        url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
        items = []
        offset = 0
        page_size = 200
        total_count = None

        while total_count is None or offset < total_count:
            params = {
                "onlyData": "true",
                "expand": "all",
                "finder": (
                    f"findReqs;siteNumber={site_id},"
                    f"limit={page_size},offset={offset}"
                )
            }
            resp = self.get(url, params=params)
            if not resp:
                if offset == 0:
                    logger.info(f"[OracleCloud] No response received from host '{host}'")
                    return []
                logger.warning(
                    f"[OracleCloud] Stopped pagination at offset {offset} for '{host}'"
                )
                break

            try:
                data = resp.json()
            except Exception as e:
                logger.error(f"[OracleCloud] JSON parse error for {host}: {e}")
                if offset == 0:
                    return []
                break

            response_items = data.get("items", [])
            if (
                len(response_items) == 1
                and isinstance(response_items[0].get("requisitionList"), list)
            ):
                search_results = response_items[0]
                page_items = search_results["requisitionList"]
                total_count = int(search_results.get("TotalJobsCount") or 0)
            else:
                page_items = response_items
                total_count = len(page_items)

            items.extend(page_items)
            if not page_items:
                break
            offset += len(page_items)

        logger.info(f"[OracleCloud] Fetched {len(items)} requisitions from {host} ({name})")

        normalized_jobs = []
        for item in items:
            req_id = str(item.get("Id") or "").strip()
            if not req_id:
                continue

            loc = item.get("PrimaryLocation") or "United States"
            workplace = item.get("WorkplaceType") or item.get("WorkplaceTypeCode") or ""
            is_remote = (
                bool(item.get("RemoteFlag"))
                or "remote" in loc.lower()
                or "remote" in str(workplace).lower()
            )
            careers_url = company_config.get("careers_url")
            if careers_url:
                job_url = f"{careers_url.rstrip('/')}/job/{req_id}"
            else:
                job_url = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site_id}/job/{req_id}"

            raw_job = {
                "source_id": req_id,
                "title": item.get("Title"),
                "company": name,
                "location": loc,
                "is_remote": is_remote,
                "url": job_url,
                "description": (
                    item.get("ExternalDescriptionStr")
                    or item.get("ShortDescriptionStr")
                    or ""
                ),
                "department": item.get("Department") or "Cloud & Technology",
                "posted_at": item.get("PostedDate")
            }

            norm = JobNormalizer.normalize_job(raw_job, self.platform_name, default_company=name)
            if norm:
                normalized_jobs.append(norm)

        return normalized_jobs

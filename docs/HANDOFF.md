# Cafy Agent: handoff, 5 Nov 2026

Where the work stands and what to pick up next. Nothing in this file has been committed. All changes are in the working tree (`git status` shows about 125 entries, mostly from the folder restructure).

---

## 1. Do these first

| # | Action | Why |
|---|--------|-----|
| 1 | **Rotate the Supabase Postgres password** (project `tgeuiemybetiiwblhdbr`). | It was hardcoded in `backend/dbcore.py` and is still in git history. The code no longer contains it. |
| 2 | **Check that database for leftover `t_<hash>` schemas** and drop them. | Earlier full test runs used the old default URL. The test suite creates throwaway schemas named `t_` plus 12 hex characters. Real tables (`public`) were not touched, but the junk schemas may exist. |
| 3 | **Never run without `DATABASE_URL` set if you mean Postgres.** | There is no built-in default any more. With `DATABASE_URL` unset, the app uses local SQLite (`backend/cafy_jobs.db`). |
| 4 | **Commit the work** (suggested split in section 7). | Nothing is committed. |

---

## 2. How to run

```bash
cd cafy-agent
uv sync                                # Python 3.13 + packages from uv.lock (macOS and Windows)
npm --prefix frontend install

uv run backend/run.py                  # API + built UI on http://127.0.0.1:8000
npm --prefix frontend run dev          # dev UI on http://127.0.0.1:5173 (proxies /api to :8000)
```

Settings in `.env` (see `.env.example`):

- **`JWT_SECRET_KEY`**: optional in development, where a temporary key is used and sessions end on restart. Required in production (32+ characters).
- **`ENABLE_GUEST_MODE`**: guest login defaults to on in development and is always off in production.
- **`DATABASE_URL`**: leave unset for local SQLite.

Tests:

```bash
uv run pytest                            # 331 pass, 5 known failures (section 6)
npm --prefix frontend test               # 60 pass
```

---


## 3. Done this session

### Project layout
- **Top level:** `frontend/`, `backend/`, `docs/`, `api/` and `README.md`. `vercel.json` and `requirements.txt` stay at the root because Vercel needs them there.
- **Paths updated:** `run.py`, alembic, scripts, tests and `vercel.json` (`includeFiles: backend/**`).
- **Still to delete:** `package.json`, `package-lock.json` and the empty `scripts/` folder at the root are redundant. Deleting them was blocked during the session.

### Scraping (`backend/scrapers/`)
- **Ashby:** read field names the API doesn't send (`locationName`, `departmentName`), so locations came back blank. It now reads `location`, `department`, `secondaryLocations` and the address country.
- **Lever:** asked for only 50 jobs per company (`limit=50`); it now pages through everything and reads `allLocations`.
- **Workday:**
  - **UK filter:** missed nested UK facets such as NVIDIA's, so it pulled 2000 global jobs; it now finds them.
  - **Job links:** every saved link was invalid (the tenant was in the path, and Workday shows "The URL you have provided is invalid"); links now work.
  - **Existing links repaired:** `database.repair_workday_url` runs when the database opens and fixes links already stored (SQLite and Postgres). Checked in a real browser: the old link shows Workday's invalid-URL page, and the repaired one opens the job.
  - **Detail data:** it now fetches real locations and descriptions.
  - **Made-up descriptions:** it no longer writes "Position: … at …" text.
- **Pinpoint, BreezyHR, Workable:** now record full locations, including country and every site.
- **New SmartRecruiters scraper:** ported from careerops (Apache-2.0).
- **Multi-location jobs:** kept if any site is in the UK, and stored with only the UK sites (`JobNormalizer.uk_only_location`).
- **`sources.yaml`:**
  - **Removed:** 7 Ashby boards that duplicated Greenhouse or returned 404, and Workday "Target" (no UK jobs).
  - **Added:** 97 sponsor employers found by discovery (below), for 258 boards in total.

### Job count ("why so few jobs?")
- **Before:** 246 active jobs at 11 companies, last scraped 28 Oct, before the scraper fixes.
- **Re-scrape of the original 161 boards (on a copy of the database):** 1,831 active jobs at 115 companies.
- **Discovery (`backend/scripts/discover_employers.py`):** it now also tries brand names ("Monzo Bank Ltd" → `monzo`, "T/A Toast" → `toast`).
  - **Shortened names are verified:** Greenhouse, SmartRecruiters and Ashby are checked against the board's own company name, using Ashby's public organisation lookup.
  - **Brand matches need review:** they are not merged unless you pass `--include-brand`, and `--exclude platform:slug` skips rejected boards.
  - **This run:** a brand-only pass at 20 requests per second. Of 124 brand matches, 101 were merged. 12 were wrong companies (philo, artemis, proton, grey…) and 11 couldn't be proven.
- **Result: 2,765 active UK jobs at 211 companies**, up from 246 at 11. Scraped into `backend/cafy_jobs.db` on 5 Nov at 00:42 (2,502 new, 234 updated).
  - By platform: Greenhouse 1,340, Ashby 880, Lever 168, SmartRecruiters 161, Workday 132, Pinpoint 50, Oracle 34.
- **Cafy (cafy.careers)** scans the whole sponsor register (140k+ sponsors) through its own API. Its job preview sits behind a bot check, so we did not pull its exact numbers.

### Accounts and sign-in (Supabase removed)
- **Backend:** `backend/auth_service.py` (logic), `auth_api.py` (`/api/auth/signup|login|refresh|logout|me|config`) and `auth.py` (middleware).
  - Passwords are hashed with Argon2id.
  - A session is a 15-minute access token plus a refresh token in an HttpOnly, SameSite=Strict cookie, rotated on every use. Replaying an old refresh token deletes all of that user's sessions.
  - Failed sign-ins are rate-limited, and logins for unknown emails take the same time as real ones.
- **Frontend:** `auth.js` (session kept in memory, silent refresh, one retry on 401, token never sent to other websites) and `AuthGate.jsx`.
- **Guest login:** the "Continue as Guest" button shows only when `/api/auth/config` says guest mode is on, which is never in production. All guests share one account.
- **Removed:** `@supabase/supabase-js`, the hardcoded anon key and Supabase project URL, and the old `X-Candidate-Id` / unauthenticated dev bypass.

### Data quality
- **Employment types:** normalised to Full-time, Part-time, Contract, Temporary, Fixed-term or Internship (`job_normalizer.normalize_employment_type`). It previously showed raw values like "FullTime" or "Permanent - Full Time", and departments such as "Engineering". This runs when jobs are saved and when they're read, so stored rows display cleanly without a re-scrape.

### UI
- **Sidebar:** "Companies" removed (the page code still exists in `App.jsx`, but nothing links to it).
- **Job detail panel (Company details / Job info / Job Intelligence):**
  - **Sponsor badge:** now reads "Licensed UK visa sponsor · Listed on the Home Office Register of Licensed Sponsors as <legal name>", with a note that a licence doesn't guarantee this role sponsors. This also fixes the bug where the API's `"United Kingdom"` didn't match `"UK"`.
  - **Company details:**
    - **Careers pages:** learning, education and product pages are never used as careers pages (it previously showed `trailhead.salesforce.com`).
    - **Hiring locations:** UK only, without "4 Locations" placeholders. This is cleaned on read, so cached research is fixed too.
    - **Notes:** provenance and diagnostic notes are no longer shown.
  - **Job info:** placeholder descriptions are hidden, with a link to the employer's advert instead.
  - **Job Intelligence:** rebuilt as About the role, Hiring process, How you match, and a collapsed Sources list.
    - **Teaching content removed:** topics to study, LeetCode and System Design links, practice questions, per-stage "how to prepare".
    - **Also removed:** the duplicate company block, A–F lettering, explainer paragraphs, and internal errors such as "HTTP 429 / set BRAVE_SEARCH_API_KEY".
    - **Hiring evidence:** education and product pages are no longer accepted as evidence (`research.is_hiring_page`).

---

## State at handoff
- **Backend:** running from `backend/run.py` on :8000 against local SQLite, with the scheduler on (scrapes every 6 hours).
- **Frontend dev server:** may still be running on :5173.
- **Tests:** backend 331 pass with 5 known failures; frontend 60 of 60 pass.

## 4. Next steps (in priority order)

1. **Spot-check new employers** in Find Jobs (Monzo, SumUp, Wayve, Lendable, Shawbrook). A Harvey AI job was checked end to end in the browser: sponsor badge, UK location, real description, structured insights, and an apply link that opens the live advert.
2. **Closed postings never expire.** `JobDatabase.save_or_update_jobs` only adds or updates. A job removed from a board stays `active` forever. Add "mark inactive if not seen in this platform's latest successful run". This matters more now that there are 10× more jobs.
3. **More coverage (discovery):**
   - **Lever brand pass:** stopped at 8,601 of 11,297 because Lever throttled it. Resume with `uv run backend/scripts/discover_employers.py --platforms lever --only-brand --rate 8 --concurrency 8 --no-merge --out <dir>`.
   - **SmartRecruiters full-name pass** (~118k slugs) has never run. It takes about 1.5 hours at `--rate 20`. Review brand hits before `--include-brand`.
   - **Workday** hosts most big UK employers (banks, pharma, retail) but can't be discovered by guessing. It needs a curated tenant list (host + site).
   - **Never run the script at its default `--rate 1000`** from a personal IP.
4. **Job detail panel, what's left:**
   - **Skill extraction:** tags "Account Executive" with **Accounting** (`backend/skill_catalog.py` / `resume_service.extract_skills`).
   - **Unused API data:** the backend still builds `interview_preparation` and diagnostic `notes`, which the UI no longer shows. Remove them from `job_intelligence/service.py` to save work.
   - **Role details:** responsibilities and requirements often come back empty (`job_intelligence/analysis.py`).
5. **Account features not built:** password reset and email verification (need an email service), change password, delete account, and a shared rate limiter for multiple instances (Vercel).
6. **Vercel:**
   - **Environment variables:** set `JWT_SECRET_KEY`, `DATABASE_URL`, `EMAIL_AGENT_SECRET` and `APP_ENV=production`.
   - **Cron path:** `vercel.json` schedules `/api/cron`, but that route doesn't exist (only `/api/cron/scrape?platform=…`).
7. **Docs:** the PDFs in `docs/` still describe Supabase.

---

## 5. Key files

| Area | Files |
|---|---|
| Accounts | `backend/auth_service.py`, `backend/auth_api.py`, `backend/auth.py`, `frontend/src/auth.js`, `frontend/src/AuthGate.jsx` |
| Scrapers | `backend/scrapers/*.py`, `backend/scrapers/sources.yaml` |
| Sponsor matching | `backend/sponsor_service.py`, `backend/sponsor-data/` |
| Employer discovery | `backend/scripts/discover_employers.py` |
| Data normalisation | `backend/scrapers/job_normalizer.py` (UK filter, multi-site, employment type), `backend/database.py` (`repair_workday_url`) |
| Job detail panel | `frontend/src/App.jsx` (`JobDetailPane`, `getVisaState`), `frontend/src/JobIntelligence.jsx`, `backend/job_intelligence/` |
| Database | `backend/dbcore.py` (SQLite/Postgres), `backend/database.py` (schema) |

---

## 6. Known test failures (5, not caused by this session's changes)

These also fail on a clean copy of the last commit:
- `test_auth_isolation::test_cron_scrape_all_requires_secret`: expects a `/api/cron` route that doesn't exist (see Vercel above).
- `test_auth_isolation::test_tailored_resumes_and_downloads_are_private`: `/api/resumes/versions` returns nothing until a résumé profile exists, and the test never sets one.
- `test_resume_section_extraction::test_all_sections_are_classified_and_keep_separate_publications`: a résumé parser count.
- `test_resume_versions_export::test_backfill_from_existing_tailored_resumes`
- `test_resume_versions_export::test_latest_upload_is_kept_and_downloadable`

---

## 7. Suggested commits

1. `chore: restructure into frontend/backend/docs/api` (moves and path fixes)
2. `fix(scrapers): Ashby/Lever/Workday/Pinpoint/Workable fixes, UK-only multi-site, SmartRecruiters scraper`
3. `feat(discovery): brand-name slugs with identity checks; add 97 reviewed sponsor boards`
4. `feat(auth): built-in accounts replace Supabase; guest login for development`
5. `fix(security): remove hardcoded database URL and Supabase keys`
6. `feat(ui): job detail panel cleanup; remove Companies from the sidebar`

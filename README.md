# Cafy Agent

An intelligent ATS scraper, automated job recommendation engine, and AI career assistant with real-time matching and career chat intelligence.

## Features
- **ATS Scraper Support**: Integrations with Greenhouse, Ashby, Lever, Workday, Workable, Oracle Cloud, BreezyHR, and Pinpoint. Scraping is restricted to jobs located in the United Kingdom or Ireland; ambiguous or overseas locations are excluded.
- **Precision Matching**: Match scores dynamically calibrated against candidate profiles (>=85% for 4+ matching skills).
- **Cafy Agent Chatbot**: Career chat dock powered by Groq and grounded intelligence for job prioritisation, skill gap analysis, and application strategy.
- **UK Sponsor Verification**: Verification against the official UK Home Office Register.
- **Fullstack Web UI**: Built with React and modern responsive CSS design.

- **Email Agent (Pipeline 3)**: Gmail/Outlook OAuth, job-email detection, classification, application status updates, interview extraction, calendar availability, human-approved replies and follow-ups. See `pipeline-3.md`; code in `backend/email_agent/`.

- **Application Automation (Pipeline 2)**: Apply starts a tracked application (duplicate-checked); the Chrome extension in `extension/` detects the ATS form, autofills from your profile, drafts grounded answers, uploads your résumé with permission, and only submits after you approve. Submissions are verified, tracked in **My Applications**, and handed to the Email Agent. See `pipeline_2.md`; code in `backend/job_applications/`.

- **Job Intelligence (Pipeline 4)**: the **Job Intelligence** tab on any job explains the company and role, discovers the hiring process only from cited evidence (job posting, official company pages, optional public reports) with confidence labels, compares your profile to the role and builds a preparation plan. See `pipeline_4.md`; code in `backend/job_intelligence/`. Set `BRAVE_SEARCH_API_KEY` to also search public candidate reports; without it only the job posting and official pages are used.

## Browser extension
Load `extension/` as an unpacked extension (chrome://extensions → Developer mode). Open its options to set the Cafy server URL and candidate ID. Supported ATS pages activate automatically; on any other site click the toolbar button. Extension logic tests: `cd frontend && npx vitest run --environment jsdom --root .. extension/tests`.

## Email Agent setup
Set these in `.env` (register an OAuth app with each provider; redirect URI is `<host>/api/email-agent/oauth/<gmail|outlook>/callback`):
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `EMAIL_AGENT_SECRET` (signs OAuth state).
Redirect URIs to register: `http://127.0.0.1:8000/api/email-agent/oauth/gmail/callback` and `.../outlook/callback`.
Google scopes requested: gmail.readonly, gmail.compose, gmail.send, calendar.freebusy, calendar.events (enable the Gmail and Calendar APIs). Microsoft: offline_access, User.Read, Mail.Read, Mail.ReadWrite, Mail.Send, Calendars.ReadWrite.
A background monitor syncs connected inboxes every `EMAIL_AGENT_POLL_MINUTES` (default 5) and drafts follow-ups; nothing is sent without your approval.
Records are scoped by the `X-Candidate-Id` header (default `local`) until the app has real login.

## Quickstart
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the server:
   ```bash
   python run.py
   ```
3. Open `http://127.0.0.1:8000` in your browser.

## Production setup (Supabase)

Copy `.env.example` to `.env` and fill it in. With `DATABASE_URL` set the app uses Supabase Postgres; without it, it falls back to the local SQLite file (development only). `APP_ENV=production` makes the server refuse to start with a missing database, sign-in, or secret.

1. **Database** – put the Supabase *Session pooler* connection string in `DATABASE_URL`. Tables are created automatically on first start (guarded by an advisory lock, safe with several instances).
2. **Sign-in** – enable Email auth in Supabase, then set `SUPABASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (and `SUPABASE_JWT_SECRET` only if the project still uses legacy HS256 keys). Every `/api` call except `/api/health`, the Google OAuth callback and cron endpoints needs a valid token; each user only ever sees their own rows.
3. **Move existing data** (jobs, résumés, applications, connected Gmail) once, assigning the old single-user rows to your Supabase user id:
   ```
   python scripts/migrate_sqlite_to_postgres.py --owner <your-supabase-user-uuid> --dry-run
   python scripts/migrate_sqlite_to_postgres.py --owner <your-supabase-user-uuid>
   ```
   It is idempotent, encrypts plain-text email tokens, and compares row counts per table.
4. **Google OAuth** – add `PUBLIC_BASE_URL + /api/email-agent/oauth/gmail/callback` as an authorised redirect URI. Gmail tokens are encrypted at rest (`TOKEN_ENCRYPTION_KEY`, or derived from `EMAIL_AGENT_SECRET`).
5. **Background work** – on a normal server the scheduler and the inbox monitor run in-process. On serverless (Vercel) they are driven by the crons in `vercel.json`, which call `/api/email-agent/cron/poll` and `/api/cron/scrape?platform=…` with `Authorization: Bearer $CRON_SECRET` (Vercel sends this automatically when `CRON_SECRET` is set). Sub-daily crons need a Vercel Pro plan.

### Tests
```
python -m pytest tests                                   # SQLite
DATABASE_URL=postgresql://localhost/cafy_test python -m pytest tests   # real Postgres (local only)
```
The suite redirects the app to a throw-away database and refuses to run against a remote `DATABASE_URL`.

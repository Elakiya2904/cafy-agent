# Cafy Agent

**UK job search, resume tailoring and application tracking in one place.**

Cafy Agent pulls live UK vacancies from employer applicant tracking systems, matches them to your resume,
tailors a one-page resume for each role without inventing anything, and keeps track of recruiter emails,
interviews and follow-ups.

- **Live app:** https://cafy-agent-mu.vercel.app
- **Stack:** FastAPI (Python 3.13) · React 18 + Vite 5 · PostgreSQL · Groq LLMs · Docker

---

## Features

### Find jobs
- **UK job feed from 9 ATS platforms:** Greenhouse, Lever, Ashby, Workday, Workable, Oracle Cloud, BreezyHR,
  Pinpoint and SmartRecruiters. A scheduler scrapes them every day at 08:00 UK time; you can also trigger a run.
- **UK-only listings:** non-UK and Irish roles are filtered out (Workday is queried for UK jobs only), and
  descriptions and salaries are cleaned up.
- **Visa sponsorship check:** employers are matched against the UK Home Office register of licensed sponsors.
- **Search and filters:** role and company or location search; filters for experience level, date posted, work
  mode (remote, hybrid, on-site), job type (full-time, part-time, contract, internship), salary range with
  currency, and include/exclude skills with Any/All matching and suggested skills. Active filters show as
  removable chips.
- **Job details:** company details, job info and **Job Intelligence** (company research, hiring process and
  interview stages gathered from public sources).

### Match and tailor your resume
- **Resume parsing** for PDF and DOCX: contact details, summary, experience and internships, education, skills
  (normalised against a 700+ skill catalogue), projects and certifications.
- **Profile strength** score out of 100 (skills 25%, experience 25%, education 15%, basic info 15%, projects 10%,
  certifications 10%) with tiers *All-Star* (88+), *Strong* (72+), *Competitive* (55+) and *Developing* (35+).
- **Job match score** per vacancy: skill coverage 50%, job title 20%, seniority 15%, evidence of the skills in
  your experience 15%, with matched and missing skills listed.
- **Apply with autofill:** review the job and its description, add optional instructions, then
  **Generate Tailored Resume**.
- **AI tailoring without invented facts:** Groq (`openai/gpt-oss-20b` by default) rewrites the summary,
  experience and project text for the role. Every rewritten line is checked against your original resume;
  any line that adds a number, tool or skill you didn't list is rejected. Only job keywords your resume already
  supports are added to the skills list.
- **Resume editor:** section tabs, drag-to-reorder entries and bullets, *Improve with AI* per section or bullet,
  writing tips, undo/redo, autosave, a live job-match score card, and a live A4 preview with font, size,
  spacing and theme controls plus *Auto-fit to 1 page*.
- **Downloads:** PDF (rendered in the browser), DOCX, and LaTeX. Server-side PDF compilation is available when
  LaTeX is installed.
- **My Resumes:** your uploaded original and every tailored version, with preview, download, delete, search
  and side-by-side comparison (page view and a list of changes).

### Track applications and recruiter email
- **Applied To:** the applications you have started, with status, filters and quick links to each posting.
- **Email Agent:**
  - Connect Gmail and Google Calendar (through Nango) or Microsoft Outlook.
  - Recruiter emails are matched to your applications and classified: application received, under review,
    assessment invitation, interview invitation, interview rescheduling, additional information, rejection,
    offer.
  - Application statuses update from those emails, and interview details are extracted. Free calendar slots can
    be offered, or an interview confirmed and added to your calendar.
  - Follow-ups are drafted after 7 days without a reply, at most 2 per application.
  - **Nothing is sent without your approval:** every reply is a draft you can edit, approve or reject.
- **Career Analyst chat:** a side panel that answers questions about your matches, skill gaps and the UK job
  market, grounded in your resume and the stored job data.
- **Analytics:** job-market and skill insights across all stored listings.
- **My Files:** export your resumes, profile and application data as a ZIP.
- **Chrome extension** (`frontend/extension`): *Cafy Application Assistant* autofills application forms from
  your profile; you review everything before submitting.
- *Job Alerts* has a placeholder page; alerts are not available yet.

### Accounts
- **Email and password accounts:** Argon2id password hashing, 15-minute access tokens kept in memory, and a
  rotating `HttpOnly`, `SameSite=Strict` refresh cookie. Reusing an old refresh token ends all of that user's
  sessions, and failed sign-ins are rate-limited. Every API request only sees the signed-in user's data.
- **Continue as Guest:** each guest gets a private, temporary account (12 hours) with no password. On by default
  in development; in production only when `ENABLE_GUEST_MODE=true`.
- Password reset and email verification are not available yet.

---

## Getting started (local)

### Prerequisites
- Python 3.13 (3.10+ works)
- Node.js 18+ and npm
- PostgreSQL (recommended) or nothing at all for a local SQLite file
- A Groq API key (`GROQ_API_KEY`) for AI tailoring and the chat
- Optional: LaTeX (`pdflatex` or `xelatex`) for server-side PDF compilation

### 1. Clone and install
```powershell
git clone https://github.com/Elakiya2904/cafy-agent.git
cd cafy-agent

python -m venv .venv
.\.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

npm --prefix frontend install
```

### 2. Configure `.env`
Copy `.env.example` to `.env` and fill in at least:

```ini
GROQ_API_KEY=gsk_...
APP_ENV=development
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/cafy_agent   # omit for local SQLite
JWT_SECRET_KEY=          # required in production; python -c "import secrets; print(secrets.token_urlsafe(48))"
ENABLE_GUEST_MODE=true
```

Integrations are optional: `NANGO_SECRET_KEY` (Gmail and Google Calendar), `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET`, `EMAIL_AGENT_SECRET` and `TOKEN_ENCRYPTION_KEY` (email agent). `.env.example` lists
every setting.

With PostgreSQL, create the `cafy_agent` database and apply migrations:
```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
```

### 3. Run
```powershell
# Backend API + built frontend on one port
.\.venv\Scripts\python.exe backend\run.py        # http://127.0.0.1:8000  (API docs: /docs)

# Optional: frontend with hot reload, in a second terminal
npm --prefix frontend run dev                    # http://localhost:5173
```

### Docker (backend + PostgreSQL)
```powershell
docker compose up -d
```
[docs/DOCKER.md](docs/DOCKER.md) covers setup, migrating an existing database, backups, rollback, publishing the
backend and database images to Docker Hub, and connecting the Vercel frontend.

---

## Deployment
- **Vercel:** builds the frontend (`frontend/dist`) and serves the API from `api/index.py` (a serverless wrapper
  around `backend.main:app`). Pushing to `main` deploys. Set `DATABASE_URL` (hosted PostgreSQL),
  `JWT_SECRET_KEY`, `EMAIL_AGENT_SECRET`, `GROQ_API_KEY` and, for guest access, `ENABLE_GUEST_MODE=true` in the
  Vercel project settings.
- **Production checks:** the API refuses to start in production without a PostgreSQL `DATABASE_URL`, a strong
  `JWT_SECRET_KEY` and `EMAIL_AGENT_SECRET`.
- **Docker:** the same backend as a container image; see [docs/DOCKER.md](docs/DOCKER.md).

---

## Testing
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests     # backend: parsing, matching, tailoring guardrails, auth isolation, email agent, scrapers
npm --prefix frontend test                             # frontend: Vitest + Testing Library
.\.venv\Scripts\python.exe docker\smoke_test.py        # end-to-end check against a running backend
```

---

## Repository structure
```
cafy-agent/
├── backend/
│   ├── main.py                       # FastAPI app: jobs, resumes, tailoring, chat, export, scrapers
│   ├── auth_api.py, auth_service.py  # Accounts, sessions, guest access
│   ├── custom_auth.py, auth.py       # Guest tokens, auth middleware
│   ├── scrapers/                     # 9 ATS scrapers, UK location filter, scraper manager
│   ├── email_agent/                  # Gmail/Outlook providers, classifier, monitor, drafts
│   ├── job_applications/             # Application tracking and form autofill
│   ├── job_intelligence/             # Company research and hiring-process analysis
│   ├── resume_service.py             # PDF/DOCX parsing and skill extraction
│   ├── resume_generation_service.py  # AI tailoring, fact guard, DOCX/LaTeX/PDF output
│   ├── recommendation_service.py     # Job match scoring
│   ├── profile_strength_service.py   # Profile strength score
│   ├── job_match_analysis_service.py # Section-by-section match analysis
│   ├── career_chat_service.py        # Career Analyst chat
│   ├── sponsor_service.py            # UK licensed sponsor register
│   ├── nango_api.py, nango_service.py # Nango integrations
│   ├── alembic/                      # Database migrations
│   ├── templates/                    # LaTeX resume template
│   └── tests/                        # pytest suite
├── frontend/
│   ├── src/                          # React app (App.jsx, ResumeEditor, EmailAgentDashboard, JobFilterPanel, ...)
│   ├── extension/                    # Chrome extension: Cafy Application Assistant
│   └── dist/                         # Built frontend (served by the backend and Vercel)
├── api/index.py                      # Vercel serverless entry point
├── docker/                           # Docker entrypoint, DB backup/restore/compare scripts, DB image
├── docs/                             # DOCKER.md, handoff notes, feature and backend PDFs
├── Dockerfile, docker-compose.yml    # Container setup
├── vercel.json                       # Vercel build and routing
└── requirements.txt                  # Python dependencies
```

## Documentation
- [docs/DOCKER.md](docs/DOCKER.md): running with Docker, database migration, backups, Docker Hub, Vercel
- [docs/HANDOFF.md](docs/HANDOFF.md): project handoff notes
- [docs/cafy-agent-up-to-date-features-and-pipelines.pdf](docs/cafy-agent-up-to-date-features-and-pipelines.pdf): features and pipelines overview
- [docs/backend-complete-logic-with-diagrams.pdf](docs/backend-complete-logic-with-diagrams.pdf): backend logic with diagrams

## License
Proprietary software developed for Cafy Agent. All rights reserved.

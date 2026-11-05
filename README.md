# Cafy Agent • UK Enterprise Career Intelligence & ATS Automation Platform

An enterprise-grade ATS automation and career intelligence platform engineered specifically for the United Kingdom employment market. Built on a high-throughput **FastAPI** backend and an interactive **React + Vite** frontend, Cafy Agent unifies real-time UK job ingestion, structured resume parsing, zero-hallucination AI document tailoring, an evidence-grounded career chatbot, and an autonomous recruiter email agent.

---

## 🌟 Platform Capabilities & Architecture

### 1. Strict UK Job Ingestion & Normalization (Pipeline 1)
- **Multi-Source ATS Support**: Polls 9 enterprise Applicant Tracking Systems: **Greenhouse**, **Lever**, **Ashby**, **Workday**, **Workable**, **Oracle Cloud**, **BreezyHR**, **Pinpoint**, and **SmartRecruiters**.
- **Upstream Network Faceting**: Queries Workday dynamic tenant facets to request only UK job listings, eliminating non-UK enterprise vacancies before payload download.
- **Strict UK Geographic Containment**: Employs a negative country and Ireland guard (`NON_UK_COUNTRY_PATTERN`, `IRELAND_LOCATION_PATTERN`, and US state suffixes) to explicitly reject overseas and Irish roles. Positive regex matches 25+ UK municipal hubs (*London, Manchester, Birmingham, Leeds, Edinburgh, Glasgow, Belfast, Bristol, Cambridge, Oxford, etc.*) and UK-wide remote roles.
- **Home Office Visa Sponsorship Verification**: Automatically cross-references hiring employers against the official UK Home Office *Worker and Temporary Worker Register of Licensed Sponsors*, annotating verified Skilled Worker (A-Rating) sponsorship eligibility.
- **Content Sanitization**: Strips HTML entities, standardizes descriptions, and parses compensation into formatted annual GBP ranges (£).

### 2. Structured Resume Intelligence & Studio (Pipeline 2)
- **6-Section Document Parser**: Extracts structured profiles from PDF and DOCX files using heuristic segmentation:
  - *Basic Contact*: Name, email, phone, location, LinkedIn/GitHub links.
  - *Professional Summary*: Career objectives and summary statements.
  - *Work History & Internships*: Seamlessly captures single-term dates (`June 2025`, `Summer 2026`) and date ranges, role vs. company disambiguation, city/state extraction, and wrapped multi-line bullet merging. Full career credit is awarded for student internships.
  - *Education*: Degrees, academic institutions, and graduation years.
  - *Technical Skills*: Extracted and normalized against a 500+ tech taxonomy.
  - *Projects & Certifications*: Architecture descriptions, tech stacks, and accredited credentials.
- **100-Point Profile Strength Scoring**: Calibrated multi-factor formula evaluating Skills (25%), Work Experience (25%), Education (15%), Basic Info (15%), Projects (10%), and Certifications (10%) across 4 readiness tiers: *All-Star* (85–100%), *Strong* (70–84%), *Moderate* (50–69%), and *Needs Improvement* (<50%).
- **Hybrid Job Matching**: Matches candidate profiles against UK vacancies combining skill overlap (50%), title & seniority alignment (30%), and location/sponsorship feasibility (20%).
- **Zero-Hallucination AI Resume Tailoring**: Powered by Groq LLM (`openai/gpt-oss-20b` with automated fallback to `llama-3.3-70b-versatile`). Features an invariant factual guardrail and metric verifier that prohibits inventing unlisted claims, employers, or metrics.
- **Dual Publication Compilers**: Outputs ATS-optimized single-page PDFs via **XeLaTeX** and editable Microsoft Word documents via **python-docx**.
- **Version Control & Rollback**: Every tailoring generation creates an immutable snapshot in `tailored_resume_versions` for side-by-side textual diffing and instant rollback.

### 3. Autonomous Recruiter Email Agent (Pipeline 3)
- **Inbox Integration**: Connects via secure IMAP or OAuth2 (Gmail, Microsoft Outlook).
- **6-Class Recruiter Communication Classifier**: Distinguishes between:
  1. *Interview Invitations*: Automatically advances application state to **Interviewing** and pre-drafts an availability response.
  2. *Technical Assessments*: Parses take-home test deadlines and schedules high-priority calendar alerts.
  3. *Acknowledgments*: Marks application as received and starts inactivity timer.
  4. *Job Offers*: Promotes status to **Offer Received** and parses compensation terms.
  5. *Rejection Notices*: Updates candidate pipeline statistics.
  6. *General Correspondence*.
- **Inactivity Cadence Automation**: Flags applications with no recruiter reply after 7 to 10 business days and queues professional status inquiry drafts.
- **Human-in-the-Loop Safeguard**: No email is ever sent autonomously; candidates review, edit, and approve pre-drafted replies with a single click.

### 4. Cafy Agent • AI Career Analyst & Copilot (Chatbot)
- **Conversational Career Assistant**: Accessible via an expandable slide-out dock on all screens (`/api/career-chat`).
- **Evidence-Grounded Intelligence**: Analyzes candidate resume facts against real-time UK market evidence (`database_summary`, `top_skill_gaps`, `recommended_cards_summary`). Strictly bound to prevent hallucinations.
- **Core Analytical Intents**:
  - *Strategy & Prioritization*: Recommends which UK roles to apply to first based on match quality and visa viability.
  - *Match Explanation*: Breaks down why a role scored 94% vs. 82%, identifying exact matched vs. missing skills.
  - *Skill Gap Roadmaps*: Highlights high-ROI technical skills recurring across active UK vacancies.
  - *UK Hiring Analytics*: Details sponsoring employers and salary distributions across UK municipal corridors.
- **Interactive In-Chat Job Cards**: Renders interactive, clickable job recommendation cards directly in the chat thread with one-click **Tailor Resume** navigation.

### 5. Candidate Application Pipeline & Stage Management
- **Interactive Kanban Board**: Manages application progression across 5 stages: *Applied* → *Screening* → *Assessment* → *Interviewing* → *Offer*.
- **Deadline Countdown Timers**: Visual urgency badges for take-home coding challenges.
- **Chrome Extension Companion (`extension/`)**: Detects ATS application forms on candidate career portals, autofills verified profile information, and uploads tailored documents upon confirmation.

### 6. Official UK Home Office Licensed Sponsor Directory
- **Authoritative Database**: Searchable register cross-referenced against the UK Home Office Worker Register.
- **Multi-Field Validation**: Matches employer legal name, trading identity, and town/county to eliminate false-positive entity matches.
- **Direct Vacancy Linkage**: Connects each registered sponsor directly to live open UK engineering, data, and product jobs.

---

## 🏗️ Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI** (Python 3.13) | Asynchronous, high-throughput REST API with Pydantic validation |
| **Frontend Framework** | **React 18** + **Vite 5** | Responsive single-page application with modern UI styling |
| **Database** | **PostgreSQL** / **SQLite** | Multi-user relational persistence; local SQLite unless `DATABASE_URL` is set |
| **Inference Engine** | **Groq API** | Ultra-fast inference with fallback cascade (`gpt-oss-20b`, `llama-3.3-70b`) |
| **Document Rendering** | **XeLaTeX** & **python-docx** | Publication-grade single-page PDFs and editable DOCX files |
| **Authentication** | **Built-in accounts** (Argon2id + JWT) | Email/password sign-up and sign-in, short-lived access tokens, rotating HttpOnly refresh cookie |
| **Testing** | **pytest** & **vitest** | Comprehensive unit, integration, and UI test coverage |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+ (Python 3.13 recommended)
- Node.js 18+ and npm
- Groq Cloud API Key (`GROQ_API_KEY`)
- *(Optional)* XeLaTeX installation (for local PDF rendering)

### 1. Clone the Repository
```bash
git clone https://github.com/vlelakkiya29/cafy.git
cd cafy
```

### 2. Backend Setup
Create and activate a virtual environment, then install dependencies:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Local PostgreSQL development
Docker is not required for local development. Install PostgreSQL for Windows,
create a database named `cafy_agent`, and set the local URL in `.env`:

```ini
DATABASE_URL=postgresql+psycopg://postgres:<PASSWORD>@localhost:5432/cafy_agent
```

The SQLAlchemy/Alembic migration foundation is now present. Once PostgreSQL is
running, verify connectivity and apply migrations with:

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import load_dotenv; load_dotenv(); from sqlalchemy import text; from backend.sqlalchemy_db import build_engine; e=build_engine(); print(e.connect().execute(text('SELECT 1')).scalar())"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

The existing runtime database adapter remains active until application tables
are mapped and the PostgreSQL migration has been validated. Do not delete the
existing database during this transition.

### 3. Environment Configuration
Copy `.env.example` to `.env` in the project root:
```bash
cp .env.example .env
```
Fill in the essential configuration parameters:
```ini
# Core LLM API
GROQ_API_KEY=gsk_your_groq_api_key_here

# App Environment (development / production)
APP_ENV=development
PUBLIC_BASE_URL=http://127.0.0.1:8000
CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:5173

# Database (leave unset for local SQLite; there is no built-in default database)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Authentication: signs user sessions. Required in production (32+ characters).
# Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(48))"
# In development it may be left unset (a temporary key is used and sessions end on restart).
JWT_SECRET_KEY=

# Guest login for testing: on by default in development (set false to hide it); never available in production
ENABLE_GUEST_MODE=true
```

### 4. Frontend Setup
```bash
npm --prefix frontend install
```

### 5. Running the Application

**Option A: Unified Server (Development & Production)**
```bash
python backend/run.py
```
* Backend API: `http://127.0.0.1:8000`
* API Documentation (Swagger): `http://127.0.0.1:8000/docs`

**Option B: Separate Frontend Dev Server (Hot Module Reload)**
```bash
# Terminal 1: Backend
python backend/run.py

# Terminal 2: Vite Dev Server
npm --prefix frontend run dev
```
* Frontend Web App: `http://localhost:5173/`

---

## 🔒 Authentication & Guest Mode

- **Accounts**: Email and password sign-up/sign-in are served by the backend (`/api/auth/signup`, `/login`, `/refresh`, `/logout`, `/me`). Passwords are hashed with Argon2id. A session is a 15-minute access token (held only in browser memory) plus a rotating refresh token in an `HttpOnly`, `SameSite=Strict` cookie; replaying a used refresh token ends all of that user's sessions. Failed sign-ins are rate-limited. Every request to `/api` is scoped to the authenticated user's ID.
- **Production**: the server refuses to start without `DATABASE_URL`, a strong `JWT_SECRET_KEY` and `EMAIL_AGENT_SECRET`. Password reset and email verification are not available yet (they need an outbound email service).
- **Guest Mode**: A **Continue as Guest** button for testing, on by default in development and turned off with `ENABLE_GUEST_MODE=false`. The server tells the UI whether to show it (`GET /api/auth/config`) and refuses guests in production. All guests share one anonymous account, so never keep real data in it. Provides a clean, centered **Continue as Guest** button on the auth screen. Guest sessions start with a clean slate (no pre-loaded resumes) and persist across page refreshes via `sessionStorage`.

---

## 🧪 Testing

### Backend Test Suite (Python)
```bash
python -m pytest backend/tests
```
Runs 80+ unit and integration tests covering:
- Strict UK location normalizer & negative regex filters (`backend/tests/test_normalizer.py`)
- Resume section parser, date ranges, and internship extraction (`backend/tests/test_resume_section_extraction.py`)
- Zero-hallucination factual guardrails & compilation (`backend/tests/test_resume_generation.py`)
- Profile strength 100-point formula & recommendation rankings (`backend/tests/test_recommendations.py`)
- Auth token verification and tenant data isolation (`backend/tests/test_auth_isolation.py`)

### Frontend Test Suite (React / Vitest)
```bash
npm --prefix frontend test
```
Verifies React components, state transitions, match scoring, and resume editors.

---

## 📁 Repository Structure

```
cafy/
├── backend/
│   ├── email_agent/             # Recruiter email monitor, IMAP/OAuth2 & 6-class classifier
│   ├── job_applications/        # Application lifecycle service & auto-fill engine
│   ├── job_intelligence/        # Company research, interview formats & evidence parsing
│   ├── scrapers/                # 8 ATS scrapers (Greenhouse, Workday, Lever, Ashby, etc.)
│   │   ├── job_normalizer.py    # Strict UK geofilter & negative country guardrails
│   │   ├── scraper_manager.py   # Rate limiting, deduplication & ingestion gate
│   │   └── workday.py           # Network-level UK country facet filtering
│   ├── templates/               # Jinja2 XeLaTeX templates for ATS-optimized PDFs
│   ├── career_chat_service.py   # Evidence-grounded conversational AI chatbot engine
│   ├── profile_strength_service.py # 100-point profile strength evaluation formula
│   ├── recommendation_service.py   # Hybrid TF-IDF & skill overlap matching engine
│   ├── resume_generation_service.py # AI resume tailoring & factual guardrail verifier
│   ├── resume_service.py        # Structured 6-section document parser (PDF & DOCX)
│   ├── sponsor_service.py       # UK Home Office Licensed Sponsor register matching
│   ├── user_store.py            # Per-user database persistence & context isolation
│   └── main.py                  # FastAPI unified application entrypoint
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main React SPA (Directory, Tracker, Resume Studio)
│   │   ├── AuthGate.jsx         # Sign in, Sign up, and Continue as Guest workflow
│   │   ├── EmailAgentDashboard.jsx # Recruiter inbox sync & follow-up approval hub
│   │   ├── JobIntelligence.jsx  # Interview stages & company research UI
│   │   ├── MyApplications.jsx   # 5-stage Kanban application pipeline
│   │   ├── ResumeEditor.jsx     # Live resume editor with real-time XeLaTeX preview
│   │   └── auth.js              # Token management & guest mode session handling
│   ├── css/                     # Enterprise design system & responsive styling
│   └── extension/               # Chrome extension for automated ATS form filling
├── api/                         # Vercel serverless entrypoint (api/index.py -> backend.main:app)
├── docs/                        # PDFs, doc_assets/, notes, and doc generators
├── vercel.json                  # Deployment config (must live at repo root)
└── requirements.txt             # Python dependencies
```

---


## ⚖️ License
Proprietary enterprise software developed for Cafy Agent. All rights reserved.

### 3. Environment Configuration
Copy `.env.example` to `.env` in the project root:
```bash
cp .env.example .env
```
Fill in the essential configuration parameters:
```ini
# Core LLM API
GROQ_API_KEY=gsk_your_groq_api_key_here

# App Environment (development / production)
APP_ENV=development
PUBLIC_BASE_URL=http://127.0.0.1:8000
CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:5173

# Database (leave unset for local SQLite; there is no built-in default database)
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Authentication: signs user sessions. Required in production (32+ characters).
# Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(48))"
# In development it may be left unset (a temporary key is used and sessions end on restart).
JWT_SECRET_KEY=

# Guest login for testing: on by default in development (set false to hide it); never available in production
ENABLE_GUEST_MODE=true
```

### 4. Frontend Setup
```bash
npm --prefix frontend install
```

### 5. Running the Application

**Option A: Unified Server (Development & Production)**
```bash
python backend/run.py
```
* Backend API: `http://127.0.0.1:8000`
* API Documentation (Swagger): `http://127.0.0.1:8000/docs`

**Option B: Separate Frontend Dev Server (Hot Module Reload)**
```bash
# Terminal 1: Backend
python backend/run.py

# Terminal 2: Vite Dev Server
npm --prefix frontend run dev
```
* Frontend Web App: `http://localhost:5173/`

---

## 🔒 Authentication & Guest Mode

- **Accounts**: Email and password sign-up/sign-in are served by the backend (`/api/auth/signup`, `/login`, `/refresh`, `/logout`, `/me`). Passwords are hashed with Argon2id. A session is a 15-minute access token (held only in browser memory) plus a rotating refresh token in an `HttpOnly`, `SameSite=Strict` cookie; replaying a used refresh token ends all of that user's sessions. Failed sign-ins are rate-limited. Every request to `/api` is scoped to the authenticated user's ID.
- **Production**: the server refuses to start without `DATABASE_URL`, a strong `JWT_SECRET_KEY` and `EMAIL_AGENT_SECRET`. Password reset and email verification are not available yet (they need an outbound email service).
- **Guest Mode**: A **Continue as Guest** button for testing, on by default in development and turned off with `ENABLE_GUEST_MODE=false`. The server tells the UI whether to show it (`GET /api/auth/config`) and refuses guests in production. All guests share one anonymous account, so never keep real data in it. Provides a clean, centered **Continue as Guest** button on the auth screen. Guest sessions start with a clean slate (no pre-loaded resumes) and persist across page refreshes via `sessionStorage`.

---

## 🧪 Testing

### Backend Test Suite (Python)
```bash
python -m pytest backend/tests
```
Runs 80+ unit and integration tests covering:
- Strict UK location normalizer & negative regex filters (`backend/tests/test_normalizer.py`)
- Resume section parser, date ranges, and internship extraction (`backend/tests/test_resume_section_extraction.py`)
- Zero-hallucination factual guardrails & compilation (`backend/tests/test_resume_generation.py`)
- Profile strength 100-point formula & recommendation rankings (`backend/tests/test_recommendations.py`)
- Auth token verification and tenant data isolation (`backend/tests/test_auth_isolation.py`)

### Frontend Test Suite (React / Vitest)
```bash
npm --prefix frontend test
```
Verifies React components, state transitions, match scoring, and resume editors.

---

## 📁 Repository Structure

```
cafy/
├── backend/
│   ├── email_agent/             # Recruiter email monitor, IMAP/OAuth2 & 6-class classifier
│   ├── job_applications/        # Application lifecycle service & auto-fill engine
│   ├── job_intelligence/        # Company research, interview formats & evidence parsing
│   ├── scrapers/                # 8 ATS scrapers (Greenhouse, Workday, Lever, Ashby, etc.)
│   │   ├── job_normalizer.py    # Strict UK geofilter & negative country guardrails
│   │   ├── scraper_manager.py   # Rate limiting, deduplication & ingestion gate
│   │   └── workday.py           # Network-level UK country facet filtering
│   ├── templates/               # Jinja2 XeLaTeX templates for ATS-optimized PDFs
│   ├── career_chat_service.py   # Evidence-grounded conversational AI chatbot engine
│   ├── profile_strength_service.py # 100-point profile strength evaluation formula
│   ├── recommendation_service.py   # Hybrid TF-IDF & skill overlap matching engine
│   ├── resume_generation_service.py # AI resume tailoring & factual guardrail verifier
│   ├── resume_service.py        # Structured 6-section document parser (PDF & DOCX)
│   ├── sponsor_service.py       # UK Home Office Licensed Sponsor register matching
│   ├── user_store.py            # Per-user database persistence & context isolation
│   └── main.py                  # FastAPI unified application entrypoint
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main React SPA (Directory, Tracker, Resume Studio)
│   │   ├── AuthGate.jsx         # Sign in, Sign up, and Continue as Guest workflow
│   │   ├── EmailAgentDashboard.jsx # Recruiter inbox sync & follow-up approval hub
│   │   ├── JobIntelligence.jsx  # Interview stages & company research UI
│   │   ├── MyApplications.jsx   # 5-stage Kanban application pipeline
│   │   ├── ResumeEditor.jsx     # Live resume editor with real-time XeLaTeX preview
│   │   └── auth.js              # Token management & guest mode session handling
│   ├── css/                     # Enterprise design system & responsive styling
│   └── extension/               # Chrome extension for automated ATS form filling
├── api/                         # Vercel serverless entrypoint (api/index.py -> backend.main:app)
├── docs/                        # PDFs, doc_assets/, notes, and doc generators
├── vercel.json                  # Deployment config (must live at repo root)
└── requirements.txt             # Python dependencies
```

---

## 📄 Client Documentation & Architecture Reports

Comprehensive documentation artifacts are maintained in the repository:
- **[Complete Backend Logic & Systems Manual](file:///C:/Users/vlela/.gemini/antigravity/brain/75d067f9-1e31-4512-b557-ebd599b1d95c/complete-backend-logic-manual.md)**: Conceptual walkthrough of every decision tree, formula, and state machine with Mermaid diagrams.
- **[Features, Pipelines & UI Specification](file:///C:/Users/vlela/.gemini/antigravity/brain/75d067f9-1e31-4512-b557-ebd599b1d95c/cafy-agent-features-and-pipelines-specification.md)**: Complete client specification with embedded live UI screens for all 6 features.
- **[UK Job Scraping & Geographic Containment Architecture](file:///C:/Users/vlela/.gemini/antigravity/brain/75d067f9-1e31-4512-b557-ebd599b1d95c/uk-ireland-scraping-architecture.md)**: 4-tier defensive isolation model guaranteeing strict UK-only vacancy containment.
- **Compiled 7-Page Client Presentation PDF**: [`docs/cafy-agent-up-to-date-features-and-pipelines.pdf`](docs/cafy-agent-up-to-date-features-and-pipelines.pdf).

---

## ⚖️ License
Proprietary enterprise software developed for Cafy Agent. All rights reserved.

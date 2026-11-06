# Running the Cafy Agent backend with Docker (Windows PowerShell)

The backend (FastAPI) and PostgreSQL run in Docker; the React frontend stays on Vercel.

```
Vercel (React app)  --/api/*-->  cafy-agent api container :8000  --private network-->  db container (PostgreSQL 18)
                                  volume: generated_resumes                              volume: pgdata
```

| File | Purpose |
|---|---|
| `Dockerfile` | Backend image: Python 3.13 slim, non-root user, migrations on start, serves `frontend/dist` too |
| `docker-compose.yml` | `db` (postgres:18 + health check + `pgdata` volume) and `api` (+ `generated_resumes` volume) |
| `.dockerignore` | Keeps `.env`, databases, backups, tests and sources out of the image |
| `.env.example` | All settings, including the Docker section |
| `docker/entrypoint.sh` | Runs `alembic upgrade head`, then Uvicorn |
| `docker/backup-local-db.ps1` | Backs up an existing PostgreSQL database (read-only on the source) |
| `docker/restore-into-docker.ps1` | Restores a backup into the Docker database; refuses to overwrite data |
| `docker/compare_databases.py` | Verifies a migration table by table (row counts + content checksums) |
| `docker/smoke_test.py` | End-to-end check of a running backend |
| `docker/certs/` | Optional extra root certificates (antivirus / corporate HTTPS inspection) |

Secrets are never copied into the image: Compose passes `.env` to the container at runtime.
Uploaded resumes are stored inside PostgreSQL; generated resume files live in the `generated_resumes` volume
(and are re-created from the database if missing).

---

## 1. Prerequisites

- Docker Desktop (WSL 2 engine). Start it and wait until `docker info` works.
- PostgreSQL client tools for the backup step (installed with PostgreSQL, e.g. `C:\Program Files\PostgreSQL\18\bin`).
- The project's Python environment (`.venv`) for the verification scripts.

**Antivirus / proxy that inspects HTTPS (AVG, Avast, Kaspersky, corporate proxy).** If `docker compose build`
fails with `CERTIFICATE_VERIFY_FAILED`, export that root certificate into `docker\certs\` (see
`docker\certs\README.md`) and build again. On this machine it was needed for AVG Web/Mail Shield.

## 2. Configure `.env`

Copy `.env.example` to `.env` if you don't have one, then make sure the Docker section is filled in:

```powershell
# A password with letters and digits only (it is used inside a connection URL)
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(24))"
```

```ini
POSTGRES_DB=cafy_agent
POSTGRES_USER=cafy
POSTGRES_PASSWORD=<the value printed above>
POSTGRES_HOST_PORT=5433      # PostgreSQL on 127.0.0.1:5433 (5432 is your local server)
API_HOST_PORT=8000
API_BIND=127.0.0.1           # 0.0.0.0 to expose the API on your network
```

The container ignores `DATABASE_URL` from `.env` and connects to the `db` container instead, so your local
(non-Docker) setup keeps working unchanged. Everything else (`JWT_SECRET_KEY`, `GROQ_API_KEY`,
`NANGO_SECRET_KEY`, `EMAIL_AGENT_SECRET`, `TOKEN_ENCRYPTION_KEY`, Google OAuth, scraper schedule...) is read from
`.env` as before. `APP_ENV` inside the container follows `DOCKER_APP_ENV`, falling back to `APP_ENV`.

## 3. Migrate your existing PostgreSQL data (first time only)

Run from the project folder. Your original database is only ever read.

```powershell
# 1) Back up the existing database (pg_dump, custom format) -> backups\cafy_agent_<timestamp>.dump (+ .sha256)
.\docker\backup-local-db.ps1

# 2) Start PostgreSQL in Docker and restore the newest backup into it.
#    Refuses to run if the Docker database already has tables; the restore is a single transaction.
.\docker\restore-into-docker.ps1

# 3) Verify: every table's row count, the alembic revision, and exact content of every public table
.\.venv\Scripts\python.exe docker\compare_databases.py
```

Expected end of step 3: `All tables match (row counts, and exact content for every public table).`
The `backups\` folder is git-ignored; it contains personal data, so keep it private.

Starting without existing data? Skip this section: on first start the container creates the schema
(`alembic upgrade head` plus the app's own tables).

## 4. Run

```powershell
docker compose up -d                 # build (first time) and start db + api
docker compose ps                    # both should show (healthy)
docker compose logs -f api           # follow backend logs (Ctrl+C to stop following)
.\.venv\Scripts\python.exe docker\smoke_test.py   # health, DB, auth, resume upload, matching, jobs, Nango
```

- API: http://localhost:8000/api/health
- The image also serves the built frontend, so http://localhost:8000 works locally.
- PostgreSQL for tools (pgAdmin, psql): `127.0.0.1:5433`, user/password from `.env`.

Everyday commands:

```powershell
docker compose restart api                          # after changing .env
docker compose up -d --build                        # after changing code
docker compose down                                 # stop; data stays in the volumes
docker compose exec db psql -U cafy -d cafy_agent   # SQL shell
```

**Never run `docker compose down -v`** unless you intend to delete the Docker database and generated files.

## 5. Backing up the Docker database

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = Get-Date -Format yyyyMMdd_HHmmss
docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/backup.dump'
docker compose cp db:/tmp/backup.dump "backups\docker_cafy_agent_$stamp.dump"
docker compose exec -T db rm -f /tmp/backup.dump
```

## 6. Rollback

The original database was never modified, so rolling back only means using it again:

```powershell
docker compose down                  # stop the containers (volumes are kept)
.\.venv\Scripts\python.exe backend\run.py   # local backend; .env DATABASE_URL still points at localhost:5432
```

To restart the Docker migration from scratch later, back up the Docker database first (section 5), then remove
only its volume deliberately and repeat section 3:

```powershell
docker compose down
docker volume rm cafy-agent_pgdata   # deletes the Docker copy only, never your original database
.\docker\restore-into-docker.ps1
```

If something goes wrong with your original database itself, it can be restored from the step-3 backup into a
new, empty database:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" -U postgres cafy_agent_restored
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" -U postgres -d cafy_agent_restored --no-owner backups\cafy_agent_<timestamp>.dump
```

## 7. Publish the backend image to Docker Hub

```powershell
docker login                                        # your Docker Hub account
$user = "yourdockerhubuser"                         # replace
$version = "1.0.0"

docker build --build-arg VERSION=$version -t cafy-agent-backend:$version .
docker tag cafy-agent-backend:$version "$user/cafy-agent-backend:$version"
docker tag cafy-agent-backend:$version "$user/cafy-agent-backend:latest"
docker push "$user/cafy-agent-backend:$version"
docker push "$user/cafy-agent-backend:latest"
```

Before pushing an image built on a machine with `docker\certs\*.crt`, decide whether that certificate should be
in the published image. It is a public certificate (no secret), but it is specific to this machine; to publish
without it, move the `.crt` files out of `docker\certs\` and rebuild.

On another machine, pull and run with the same compose file:

```powershell
docker pull yourdockerhubuser/cafy-agent-backend:1.0.0
# in .env:  BACKEND_IMAGE=yourdockerhubuser/cafy-agent-backend:1.0.0
docker compose up -d --no-build
```

That machine needs its own `.env` (copy `.env.example`); secrets never travel inside the image.

### Database image (`cafy-agent-db`)

`docker/postgres/Dockerfile` is the official `postgres:18` image plus a seed that runs on first start: the full
schema and the scraped job listings. It contains **no** users, sign-in tokens, profiles, resumes,
applications or email data, so it is safe to publish.

```powershell
.\docker\postgres\build-seed.ps1                     # regenerate the seed from your database (read-only)
docker build -t cafy-agent-db:1.0.0 docker\postgres
docker tag cafy-agent-db:1.0.0 "$user/cafy-agent-db:1.0.0"
docker tag cafy-agent-db:1.0.0 "$user/cafy-agent-db:latest"
docker push "$user/cafy-agent-db:1.0.0"
docker push "$user/cafy-agent-db:latest"
```

Use it on a new machine by setting `DB_IMAGE=yourdockerhubuser/cafy-agent-db:1.0.0` in `.env` before the first
`docker compose up -d`. The seed only runs when the `pgdata` volume is empty, so an existing database is never
changed.

### Full database image (private)

A second variant contains **everything** in the `public` schema: users (Argon2id password hashes), sign-in
tokens (stored as SHA-256 hashes, not usable to sign in), profiles, uploaded and tailored resumes, applications,
email data (OAuth tokens stay encrypted; the key is in `.env`, not in the image) and job listings.

```powershell
.\docker\postgres\build-seed.ps1 -Full               # -> docker\postgres\initdb-full (git-ignored)
docker build --build-arg SEED_DIR=initdb-full --build-arg SEED_KIND=full-private -t cafy-agent-db:full docker\postgres
```

It holds personal data, so:
- Publish it only to a **private** repository with its own name (Docker Hub privacy is per repository, not per
  tag). Create `cafy-agent-db-private` as *Private* on Docker Hub **before** pushing:

  ```powershell
  docker tag cafy-agent-db:full "$user/cafy-agent-db-private:1.0.0"
  docker push "$user/cafy-agent-db-private:1.0.0"
  ```

- Never push it to the public `cafy-agent-db` repository.
- Anyone who can pull it can read every resume and account in it. Prefer backups (sections 3 and 5) for moving
  your own data when possible.
- Users can sign in with their existing passwords on any server that uses the image; existing browser sessions
  do not carry over.

## 8. Connect the Vercel frontend to this backend

The frontend calls the API with relative URLs (`/api/...`) and keeps its sign-in refresh cookie first-party
(`SameSite=Strict`). The simplest setup is therefore to let Vercel **proxy** `/api/*` to the Docker backend,
so the browser only ever talks to your Vercel domain and no CORS or cookie changes are needed.

1. **Give the backend a public HTTPS URL.** A container on your PC is not reachable from the internet. Options:
   - a small cloud VM running this same `docker compose up -d` behind a reverse proxy with HTTPS (Caddy, Nginx), or
   - a tunnel from this PC, e.g. Cloudflare Tunnel: `cloudflared tunnel --url http://localhost:8000`
     (quick tunnels change URL on every start; use a named tunnel for a fixed hostname).
2. **Point Vercel at it.** In `vercel.json`, replace the API rewrite that targets the serverless function:

   ```json
   { "source": "/api/(.*)", "destination": "https://api.your-domain.example/api/$1" }
   ```

   Keep the `/(.*) -> /index.html` rewrite. The `functions` and `crons` entries for `api/index.py` are then
   unused; move the daily jobs to the backend (its built-in scheduler already runs the scrape daily).
3. **Backend settings (`.env` on the server):**

   ```ini
   DOCKER_APP_ENV=production
   PUBLIC_BASE_URL=https://cafy-agent-mu.vercel.app   # OAuth callbacks come back through the Vercel proxy
   CORS_ORIGINS=https://cafy-agent-mu.vercel.app
   ENABLE_GUEST_MODE=true                             # only if you want "Continue as Guest"
   ```

   Update the Google OAuth and Nango redirect URLs if they point anywhere else.
4. Deploy the frontend (push to `main`) and check `https://cafy-agent-mu.vercel.app/api/health`.

Until you change `vercel.json`, the live site keeps using its current serverless backend, unaffected by Docker.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Start Docker Desktop and wait until `docker info` works |
| Build: `CERTIFICATE_VERIFY_FAILED` | Add your antivirus/proxy root certificate to `docker\certs\` (section 1) |
| `Set POSTGRES_PASSWORD in .env` | Fill in the Docker section of `.env` (section 2) |
| api restarts: `server does not support SSL, but SSL was required` | `DATABASE_URL` in compose must end with `?sslmode=disable` (it does by default) |
| Port 8000 or 5433 already in use | Change `API_HOST_PORT` / `POSTGRES_HOST_PORT` in `.env` |
| Resume PDF download unavailable | Expected without LaTeX; the editor exports PDF itself. For server PDFs: `INSTALL_LATEX=true` then `docker compose up -d --build` |
| Restore refuses: database already has tables | It never overwrites data; see Rollback to start over deliberately |

Notes:
- One Uvicorn worker on purpose: the daily scraper and the email monitor run inside the API process.
- Inside Docker the API connects to PostgreSQL without TLS; that connection never leaves the private Docker
  network. External managed databases still get `sslmode=require` automatically.

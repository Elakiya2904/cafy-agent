# syntax=docker/dockerfile:1.7
# Cafy Agent backend: FastAPI + Uvicorn. Also serves the prebuilt React app (frontend/dist) at "/".
#
#   docker build -t cafy-agent-backend:local .
#   docker build --build-arg INSTALL_LATEX=true -t cafy-agent-backend:latex .   # server-side PDF compilation
#
# No secrets are baked into the image: configuration comes from the environment at runtime (.env via compose).

ARG PYTHON_VERSION=3.13

# ---------------------------------------------------------------- builder: install Python dependencies
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

# uv installs exactly what uv.lock pins, into /opt/venv, using this image's Python (no download).
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_SYSTEM_CERTS=1

# Extra root CAs (docker/certs/*.crt), e.g. an antivirus or corporate proxy that re-signs HTTPS traffic.
# The folder may be empty; public certificates only, never private keys.
COPY docker/certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates

WORKDIR /build
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project --python /usr/local/bin/python

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

# LaTeX is only needed to compile resume PDFs on the server (the editor renders its own PDF in the browser).
# It adds several hundred MB, so it is off by default.
ARG INSTALL_LATEX=false
ARG VERSION=dev

LABEL org.opencontainers.image.title="cafy-agent-backend" \
      org.opencontainers.image.description="Cafy Agent API: FastAPI backend with ATS scrapers, resume tailoring and job matching" \
      org.opencontainers.image.source="https://github.com/Elakiya2904/cafy-agent" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    APP_ENV=production \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tini \
 && if [ "$INSTALL_LATEX" = "true" ]; then \
      apt-get install -y --no-install-recommends \
        texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended lmodern; \
    fi \
 && rm -rf /var/lib/apt/lists/*

# Same extra root CAs as the builder, so outbound HTTPS (Groq, Nango, job boards) verifies at runtime too.
COPY docker/certs/ /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates

RUN groupadd --system --gid 10001 cafy \
 && useradd --system --uid 10001 --gid cafy --home-dir /app --shell /usr/sbin/nologin cafy

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=cafy:cafy backend ./backend
COPY --chown=cafy:cafy frontend/dist ./frontend/dist
COPY --chown=cafy:cafy docker/entrypoint.sh /usr/local/bin/cafy-entrypoint

# Strip CRLF in case the script was checked out on Windows; create the generated-files directory
# (mounted as a volume) with the right owner so the non-root user can write to it.
RUN sed -i 's/\r$//' /usr/local/bin/cafy-entrypoint \
 && chmod 0755 /usr/local/bin/cafy-entrypoint \
 && mkdir -p /app/backend/generated_resumes \
 && chown -R cafy:cafy /app/backend/generated_resumes

USER cafy

EXPOSE 8000

# /api/health queries the database, so a healthy container also means a working DB connection.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8).status == 200 else 1)"

ENTRYPOINT ["tini", "--", "cafy-entrypoint"]
# One worker on purpose: the daily scraper and email monitor run as in-process background threads,
# so several workers would run them several times.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

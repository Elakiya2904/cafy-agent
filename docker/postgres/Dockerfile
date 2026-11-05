# Cafy Agent database image: official PostgreSQL 18 + a seed that runs on first start.
#
# The seed (docker/postgres/initdb, made by build-seed.ps1) creates the full schema and loads the scraped job
# listings only. It contains no users, sign-in tokens, profiles, resumes, applications or email data.
#
#   .\docker\postgres\build-seed.ps1
#   docker build -t cafy-agent-db:local docker\postgres
#
# Seed scripts run only when the data volume is empty (first start). An existing volume is never touched.
FROM postgres:18

LABEL org.opencontainers.image.title="cafy-agent-db" \
      org.opencontainers.image.description="PostgreSQL 18 with the Cafy Agent schema and job listings (no personal data)" \
      org.opencontainers.image.source="https://github.com/Elakiya2904/cafy-agent"

COPY initdb/ /docker-entrypoint-initdb.d/

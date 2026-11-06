# Cafy Agent database image: official PostgreSQL 18 + a seed that runs on first start.
#
# The seed (docker/postgres/initdb, made by build-seed.ps1) creates the full schema and loads the scraped job
# listings only. It contains no users, sign-in tokens, profiles, resumes, applications or email data.
#
#   .\docker\postgres\build-seed.ps1
#   docker build -t cafy-agent-db:local docker\postgres
#
# Seed scripts run only when the data volume is empty (first start). An existing volume is never touched.
#
# Full variant (PRIVATE, contains personal data: users, password hashes, resumes, applications...):
#   .\docker\postgres\build-seed.ps1 -Full
#   docker build --build-arg SEED_DIR=initdb-full -t cafy-agent-db:full docker\postgres
FROM postgres:18

# initdb = schema + job listings (shareable); initdb-full = everything (private).
ARG SEED_DIR=initdb
ARG SEED_KIND=schema-and-jobs

LABEL org.opencontainers.image.title="cafy-agent-db" \
      org.opencontainers.image.description="PostgreSQL 18 with the Cafy Agent database seed (${SEED_KIND})" \
      org.opencontainers.image.source="https://github.com/Elakiya2904/cafy-agent" \
      cafy.seed="${SEED_KIND}"

COPY ${SEED_DIR}/ /docker-entrypoint-initdb.d/

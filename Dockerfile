# ── Frontend build stage ─────────────────────────────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend ./
# Vite is configured to output to ../app/webdist
RUN mkdir -p /app/webdist && npm run build

# ── Python runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# postgresql-client provides pg_dump/pg_restore, used by app/backup.py.
# zlib1g is named explicitly so the layer upgrades the base image's vulnerable
# build to the fixed trixie-security version (issue #24); libpq5 arrives with
# postgresql-client and likewise resolves to the fixed 17.12-0+deb13u1.
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client zlib1g \
    && rm -rf /var/lib/apt/lists/*

# pip is not a lockfile dep (pip-tools marks it unsafe for hashed files); pin it
# here so the shipped image carries all published pip CVE fixes (issue #24).
RUN pip install --no-cache-dir pip==26.3

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY schema.sql .
COPY app ./app
# Bring in the built SPA from the frontend stage
COPY --from=frontend /app/webdist ./app/webdist

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

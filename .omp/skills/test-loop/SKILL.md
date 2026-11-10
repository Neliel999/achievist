---
name: test-loop
description: Verified local test-loop for the achievist fork on this workstation — podman Postgres on 5433, Python 3.12 venv from the dev-gh toolbox, REQUIRE_DB_TESTS=1 pytest, frontend/e2e handling with node absent.
---

# Verified environment facts (2026-11-10)
- Host: podman 5.8.9; NO docker, NO gh, NO node/npm; system python is 3.14
  (psycopg[binary] 3.2.3 has no cp314 wheels — that is why AGENTS.md pins 3.12).
- Toolbox `dev-gh`: python3.12 = 3.12.16 (`python3.12 -m venv` + pip 26.0.1
  verified; psycopg 3.2.3 wheel is py3-none-any). gh 2.97.0 also there.

# Backend suite (the real gate)
```sh
# throwaway Postgres 16 on an ISOLATED port (CI uses 5432; local uses 5433)
podman run --rm -d --name achievist-test-pg \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pantheon_test \
  -p 5433:5432 postgres:16-alpine
podman exec achievist-test-pg pg_isready -U postgres   # wait until accepting

# Python 3.12 venv in /tmp (never inside the repo)
toolbox run -c dev-gh python3.12 -m venv /tmp/achievist-venv-test
/tmp/achievist-venv-test/bin/pip install -r requirements-dev.txt

# run from the repo root
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pantheon_test \
REQUIRE_DB_TESTS=1 /tmp/achievist-venv-test/bin/pytest -q
```
- `REQUIRE_DB_TESTS=1` turns a missing/unreachable DB into a hard FAILURE
  (tests/conftest.py pytest_configure). Without TEST_DATABASE_URL the DB tests
  SKIP with a distinctive reason and the run prints a banner — a green total
  with skips is PARTIAL, never report it as full green.
- Teardown: `podman rm -f achievist-test-pg`; venv lives in /tmp.

# Frontend suite
- node/npm are NOT installed on the host or in any toolbox (verified). Either
  provision node 22 (dnf or official tarball) and run
  `cd frontend && npm ci && npm test && npm run build`,
  or report `not_runnable_locally` — CI (.github/workflows/test.yml, frontend
  job) covers it. Never fake a pass.

# e2e (only when asked)
Needs built frontend + `playwright install chromium` + a running server +
`E2E_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pantheon_e2e pytest e2e -q`
(see README "Browser smoke tests"; e2e/conftest.py seeds its own data).

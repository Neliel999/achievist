---
name: test-loop
description: Verified local test-loop for the achievist fork — podman Postgres on 5433, Python 3.12 venv from the achievist-dev toolbox (run inside the toolbox), REQUIRE_DB_TESTS=1 pytest, frontend vitest/build via node in achievist-dev, e2e recipe.
---

# Verified environment facts (2026-11-13, post Kinoite-45 migration)
- Host: Fedora Kinoite 45, podman 6.1.3, toolbox 0.3; no docker; host system
  python is 3.15 (psycopg[binary] 3.2.3 has no cp315 wheels — that is why
  AGENTS.md pins 3.12). All podman commands below run ON THE HOST. Human-facing
  setup docs: README "Development" → "Local dev on Fedora Kinoite".
- Toolbox `achievist-dev` (fedora-toolbox:45, rebuilt from scratch after the
  migration): python3.12 = 3.12.16 (venv + pip 26.1.2 via ensurepip verified;
  `python3.12-pip` does not exist on F45), gh 2.97.0, node v22.23.1 + npm
  10.9.8 (matches CI's node 22), psycopg 3.2.3 wheel installs and imports in
  the 3.12 venv. A static gh also lives on the host at `~/.local/bin/gh`.

# Backend suite (the real gate)
```sh
# throwaway Postgres 16 on an ISOLATED port (CI uses 5432; local uses 5433)
podman run --rm -d --name achievist-test-pg \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pantheon_test \
  -p 5433:5432 postgres:16-alpine
podman exec achievist-test-pg pg_isready -U postgres   # wait until accepting

# Python 3.12 venv in /tmp (never inside the repo). Create AND run it inside
# the achievist-dev toolbox: the venv python needs libpython3.12.so.1.0 from the
# toolbox (verified: host execution fails to start).
toolbox run -c achievist-dev python3.12 -m venv /tmp/achievist-venv-test --copies
toolbox run -c achievist-dev /tmp/achievist-venv-test/bin/pip install -r requirements-dev.txt

# run from the repo root, inside the toolbox
toolbox run -c achievist-dev env TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pantheon_test \
REQUIRE_DB_TESTS=1 /tmp/achievist-venv-test/bin/pytest -q
```
- `REQUIRE_DB_TESTS=1` turns a missing/unreachable DB into a hard FAILURE
  (tests/conftest.py pytest_configure). Without TEST_DATABASE_URL the DB tests
  SKIP with a distinctive reason and the run prints a banner — a green total
  with skips is PARTIAL, never report it as full green.
- Teardown: `podman rm -f achievist-test-pg`; venv lives in /tmp.
- Verified end to end 2026-11-10: 309 passed, 0 failed, 0 skipped.

# Frontend suite (node/npm live in the achievist-dev toolbox)
```sh
cd frontend
toolbox run -c achievist-dev npm ci
toolbox run -c achievist-dev npm test        # vitest run (jsdom)
toolbox run -c achievist-dev npm run build   # tsc -b && vite build → ../app/webdist
```
If node is ever unavailable again, report `not_runnable_locally` — never fake
a pass; CI (.github/workflows/test.yml frontend job) covers it.

# e2e (only when asked)
Needs the built frontend + `playwright install chromium` (in the venv) + a
running server + `E2E_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pantheon_e2e pytest e2e -q`
(README "Browser smoke tests"; e2e/conftest.py seeds its own data). jsdom
cannot check real layout — e2e is the only place that can.

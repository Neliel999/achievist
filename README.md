# Achievist

A self-hosted, single-user cross-platform achievement aggregator. Track achievements, trophies, and playtime across Steam, Xbox, PlayStation, Epic Games, RetroAchievements, Ubisoft Connect, Guild Wars 2, and Wargaming titles — one dashboard, running on your own box.

## Stack

FastAPI + APScheduler backend in one container, Postgres for storage, a React + Tailwind SPA frontend. No login, no leaderboards, no multi-tenancy: it's yours alone.

## Quick start

```bash
docker compose up -d --build
```

Open `http://<host>:8744`. Everything else — connecting platforms, credentials, sync — happens in the **Accounts** tab of the app itself. There's no `.env` setup required to get the app running; `.env` is only for a handful of optional app-level settings (see below).

## Connecting platforms

Every platform is connected from the **Accounts** tab in the UI, not `.env`. Click **Connect** on a platform card and follow its prompt:

| Platform | What you need | Notes |
|---|---|---|
| **Steam** | SteamID64 + API key | Profile & game details must be public |
| **Xbox** | "Sign in with Xbox" (device code) or a public gamertag | Needs `XBOX_CLIENT_ID` set — see below |
| **PlayStation** | A one-time `npsso` token, then any public Online ID | Trophy privacy must be "Anyone" |
| **Epic Games** | Your Epic account ID (from your profile URL) | Profile must be public |
| **RetroAchievements** | Username + API key | |
| **Ubisoft Connect** | A one-time browser session ticket, then any public username | Only legacy "Uplay units" achievements are available — see [Platform notes](#platform-notes) |
| **Guild Wars 2** | An API key (progression scope) | |
| **Wargaming** (WoT/WoWS) | Application ID + nickname/region | |

Once connected, an account syncs automatically on the schedule (`SYNC_INTERVAL_HOURS`, default 12h) or on demand via **Sync all** / the per-account **Sync** button.

### Xbox setup

Xbox sign-in needs a free, one-time Azure app registration — Microsoft doesn't allow the device-code flow for a shared/borrowed client ID:

1. [portal.azure.com](https://portal.azure.com) → **App registrations** → **New registration**
   - Supported account types: *Personal Microsoft accounts only*
   - No redirect URI needed
2. **Authentication** → **Allow public client flows** → **Yes** → Save
3. Copy the **Application (client) ID** into `.env` as `XBOX_CLIENT_ID`
4. `docker compose up -d --build`, then Accounts → Xbox → **Sign in with Xbox**

After that, you can also add other public gamertags as separate accounts.

### PlayStation setup

1. Log into [playstation.com](https://playstation.com) in a browser
2. Visit `https://ca.account.sony.com/api/v1/ssocookie` in the same browser — copy the `npsso` value from the JSON
3. Accounts → PlayStation → Connect → paste it (one-time backend session)
4. Add accounts by **PSN Online ID** (trophy privacy must be public)

### Ubisoft Connect setup

1. Log into [connect.ubisoft.com](https://connect.ubisoft.com), open DevTools → Network, and grab a `Ubi_v1 t=…` session ticket from any `public-ubiservices.ubi.com` request
2. Accounts → Ubisoft → Connect → paste it (expires after a few hours — you'll re-paste occasionally)
3. Add accounts by **username** (public profile required)

### GOG setup

1. Accounts → GOG → Connect → **Sign in with GOG** — opens GOG's login page in a new tab
2. After signing in, GOG lands you on a page whose address contains `?code=...` — copy that whole URL (or just the code)
3. Paste it back into achievist and connect

A per-account refresh token is stored in the account, so later syncs need no re-login. (GOG has no redirect-based login for third-party servers — the public Galaxy client's redirect is fixed to a GOG page — hence the paste-a-code step.)

## Platform notes

- **Ubisoft achievements are limited to legacy "Uplay units"**, not the modern achievement set Ubisoft's own apps show. Ubisoft's modern achievement API is locked to a private client ID only their desktop app holds, and their local caches are encrypted — there is no public path to full parity. Games and legacy unit progress still sync correctly.
- **GOG syncs directly** via GOG's API after a one-time OAuth sign-in: the owned library from `embed.gog.com` and per-game achievements (full locked catalog, unlock dates, icons, rarity) from `gameplay.gog.com`. The per-game client secret is only required for *writes*, which achievist never performs.
- **Epic Games** achievement data is fully public (no auth beyond your account ID) via Epic's Store GraphQL API.

## Accounts and sessions

Logins are throttled. Eight failed attempts on one username within 15 minutes
locks that username out for 10 minutes; the correct password clears the count
immediately. There is a much looser per-IP cap (30) as a backstop against
someone spraying many usernames — deliberately loose, because behind a reverse
proxy every request arrives from one address and a tight limit there would let
one attacker lock out the whole household.

The trade-off runs the other way too: anyone who can reach the login page can
lock one person out for 10 minutes by guessing badly on purpose. That is an
annoyance rather than damage, and it is the price of the protection.

Counters live in memory. The app runs a single uvicorn process, so there is
nothing to share them with, and they reset on restart. **If you ever run it
with multiple workers, this has to move to Postgres** — otherwise each worker
enforces its own limit and the effective cap multiplies by the worker count.

Expired sessions are swept once at startup and daily thereafter. Sessions last
30 days and lookups already filter on expiry, so the old rows were harmless —
just permanent.

### The session cookie over HTTPS

The session cookie is `HttpOnly` and `SameSite=Lax`, and carries `Secure` when
the request arrived over https — so the browser will never send it over plain
http, including on a link an attacker downgrades.

Detection reads `X-Forwarded-Proto` before the socket's own scheme, and that
order matters: uvicorn runs without `--proxy-headers`, so behind a
TLS-terminating reverse proxy the app only ever sees http on the socket. Going
by that alone would leave `Secure` off on exactly the deployments that need it.

`COOKIE_SECURE` overrides the detection: `true` always sets the flag (right for
an https-only deployment), `false` never does. The `auto` default exists
because an install can be reachable both ways — https from outside, plain http
on the LAN — and a hard `true` would silently break every http login: the
browser accepts the cookie and then refuses to send it back, which looks like
being logged out the moment you sign in.

Note this is the app's half only. HSTS, redirecting http to https, and the
certificate itself belong to whatever terminates TLS in front of it.

## Optional app-level settings (`.env`)

Copy `.env.example` to `.env` for these — none are required to start the app:

| Variable | Purpose |
|---|---|
| `XBOX_CLIENT_ID` | Required for Xbox sign-in (see above) |
| `SYNC_INTERVAL_HOURS`, `REQUEST_DELAY_SECONDS` | Sync scheduling / per-request throttling |
| `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` | Portrait cover art fallback (Twitch dev app) |
| `SGDB_API_KEY` | SteamGridDB landscape cover art (preferred over IGDB) |
| `EXOPHASE_*` | Xbox 360 locked-achievement import from exophase.com |
| `BACKUP_KEEP_COUNT`, `BACKUP_INTERVAL_HOURS` | Backup retention count / schedule (defaults: 14 kept, every 24h) |
| `COOKIE_SECURE` | `auto` (default), `true`, or `false` — whether the session cookie carries the Secure flag |

## Backups

Everything Achievist knows — synced games/achievements *and* connected-account
credentials — lives in a single Postgres database, so backups are a `pg_dump`
away. This happens automatically:

- A `pg_dump -Fc` runs on a schedule (`BACKUP_INTERVAL_HOURS`, default 24h) and
  is written to a `/backups` volume, keeping the most recent `BACKUP_KEEP_COUNT`
  (default 14).
- The **Maintenance** page has a **Backups** section to trigger a backup on
  demand, download any backup, or delete old ones.
- The same is available directly: `POST /api/backups` (create), `GET
  /api/backups` (list), `GET /api/backups/{filename}` (download), `DELETE
  /api/backups/{filename}` (delete).

The **Maintenance** page also has a **Cover Art** section to re-fetch every
game's SteamGridDB cover art from scratch (`POST /api/sgdb-refresh?force=true`)
— useful after a change to which art is preferred, or if a batch of covers
still look wrong.

**Maintenance is admin-only**, and its tab is hidden for everyone else. Every
section on it acts on the whole install rather than on one person — the cover
refresh overwrites manually chosen art in every account's library — so the
endpoints behind them require an admin session, not just a logged-in one.
Personal data export is not a maintenance job and lives in the **profile**
dialog (click your name at the top of the page); it serves `GET /api/export`,
which any signed-in user may call and which only ever returns their own data.

**Restore** a downloaded `.dump` file into a running stack:

```sh
docker compose exec -T db pg_restore -U pantheon -d pantheon --clean --if-exists < backup.dump
```

**Security note:** backup files contain plaintext account credentials (API
keys, tokens) for every connected platform. Treat them like secrets — store
downloaded copies somewhere access-controlled, not in a shared or public
location.

## Installing on a phone

Achievist is a PWA, so it installs to a home screen without an app store.

- **Android / Chrome** — open the site and use the "Install app" prompt, or
  ⋮ → *Add to Home screen*.
- **iOS / Safari** — Share → *Add to Home Screen*. iOS ignores the manifest
  and uses the `apple-touch-icon`, which is why both exist.

Installed, it opens with no browser chrome, gets its own icon and its own
entry in the task switcher.

**This needs HTTPS.** Service workers require a secure context, and browsers
count only `localhost` as an exception — reached over plain `http://` at a
LAN address like `http://192.168.1.20:8000`, the app still works fine but
will not offer to install. Put it behind a reverse proxy with a certificate
(Caddy or Tailscale Serve both do this with no manual certificate work).

**It is not an offline app.** The service worker exists because Chrome will
not offer to install without one, and it caches only the content-hashed
build assets. It deliberately never touches `/api/*`: those responses are one
person's private library behind a session cookie, and a cached copy could be
handed to whoever signs in next on a shared device. Open it with no
connection and you get the browser's offline page.

Regenerate the icons with `pip install pillow && python scripts/make_icons.py`
— they are committed as PNGs so neither the build nor CI needs an image
library.

## Cover art priority

For non-Steam games, covers are resolved in this order:
1. **SteamGridDB** landscape grid (460×215 or 920×430)
2. **IGDB** portrait cover (cropped to landscape)
3. **Platform icon**

Use the **Change Cover** action on a game's detail page to search SGDB manually and pin a specific image.

## API reference

The frontend is a full SPA; these are the main endpoints it talks to (see `app/main.py` for the complete set):

| Method | Path | Purpose |
|---|---|---|
| GET / PUT | `/api/profile` | Your display name and avatar (shown in the header — click it to edit) |
| GET | `/api/summary` | Overall + per-platform stats |
| GET | `/api/games` | Library, paginated (`sort`, `platform`, `completion`, `search`) |
| GET | `/api/achievements/search` | Achievement search across the whole library (`q`, `rarity`, `platform`, `unlocked`, `sort`) |
| GET | `/api/games/{id}` | Game detail with achievements and rarity |
| GET | `/api/activity` | Unlock heatmap, streaks, recent-activity feed |
| GET | `/api/statistics` | Rarity/completion breakdowns, records, progression |
| GET | `/api/platforms` | Connect-schema for every supported platform |
| GET / POST / DELETE | `/api/accounts` | List / connect / disconnect accounts |
| POST | `/api/accounts/{id}/sync` | Sync a single account |
| POST | `/api/sync` | Sync all accounts (202, or 409 if busy) |
| GET | `/api/sync/progress` | Live sync status |
| GET / POST | `/api/backups` | List backups / trigger one now |
| GET / DELETE | `/api/backups/{filename}` | Download / delete a backup |

## Development

### Backend tests

```bash
pip install --require-hashes -r requirements-dev.txt
pytest
```

`requirements.txt` / `requirements-dev.txt` are hash-locked lockfiles generated
by [pip-tools](https://github.com/jazzband/pip-tools) from `requirements.in` /
`requirements-dev.in`. To add or bump a dependency, edit the `.in` file and
recompile:

```bash
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --output-file=requirements-dev.txt requirements-dev.in
```

Never edit the generated `.txt` files directly; installs use `--require-hashes`
(CI and Dockerfile included), so a missing or wrong hash fails the install.
The `lockfiles` CI job also fails if the `.txt` files are stale relative to the
`.in` files — always recompile and commit both together.

**Most of the suite needs a database.** Pure parsing/auth helpers, the
platform-registry contract and a few DB-free API routes run with no setup, but
everything else — account dedup, unlock detection, schema migrations, and every
hand-written query behind the statistics, leaderboard, milestone and chase-list
endpoints — needs a real Postgres. Point `TEST_DATABASE_URL` at a throwaway
database to run the lot:

```bash
createdb pantheon_test   # or: docker run --rm -d -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pantheon_test pytest
```

Without one, those tests skip and the run ends with a banner saying how many
did not run — a bare `pytest` still works, it just isn't a full pass, and says
so rather than printing a green total that looks like one.

Set `REQUIRE_DB_TESTS=1` to turn a missing database into an error instead of a
skip. CI sets it, so a Postgres service container that fails to start fails the
build rather than quietly reducing it to the DB-free tests.

### Frontend

```bash
cd frontend
npm install
npm run dev      # dev server with API proxy to :8000
npm run build    # production build → app/webdist (what Docker serves)
```

### Frontend tests

```bash
cd frontend
npm test         # once
npm run test:watch
```

Vitest with Testing Library, running against jsdom, so they need no browser and
no database. They cover the formatting/rarity/platform helpers and component
rendering — the empty states, milestone wording, and the panels on the Home
page. Note the limit: jsdom has no real layout engine, so a purely visual
regression (an element wrapping onto two lines, a colour that's hard to read)
will pass here and still needs a look in a browser.

### Browser smoke tests

```bash
cd frontend && npm ci && npm run build   # they drive the real app
cd .. && playwright install chromium     # once
E2E_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pantheon_e2e pytest e2e
```

A handful of Playwright tests that load the built app in Chromium and check
what jsdom cannot: that no page scrolls sideways, that header and tab labels
do not wrap, that panels render with real size. They live in `e2e/` rather
than `tests/`, so a plain `pytest` neither runs them nor pretends to — run
them by name. CI runs them as their own job.

They are deliberately few. Anything assertable without a layout engine
belongs in the Vitest tests, which are far quicker.

### Full stack locally

```bash
docker compose up -d --build
```

CI (`.github/workflows/test.yml`) runs three jobs on every push and PR: the backend suite against a Postgres service container, the frontend tests plus a production build, and the browser smoke tests against the whole stack.

### Local dev on Fedora Kinoite (immutable host, no docker)

On a Kinoite workstation the host is immutable and its system Python is too new
for the pinned deps (psycopg 3.2.3 has no wheels past Python 3.12), so run the
tooling in a toolbox named `achievist-dev`. Home is bind-mounted into the
toolbox, so `~/.config/gh` credentials and `~/Projects` carry over — no re-login.

Create it from scratch (fresh install or after a host migration):

```bash
toolbox create -c achievist-dev          # fedora-toolbox:<host release>
toolbox run -c achievist-dev sudo dnf install -y \
  gh python3.12 python3.12-devel git nodejs nodejs-npm podman podman-compose
```

Notes: do not add `python3.12-pip` (not packaged on F45; `python3.12 -m venv`
bootstraps pip via ensurepip). F45's `nodejs` is already 22 with npm 10. For a
reproducible image, keep `~/Containerfile.achievist-dev` and rebuild with
`podman build -t localhost/achievist-dev -f ~/Containerfile.achievist-dev ~ &&
toolbox create -c achievist-dev -i localhost/achievist-dev` (the Containerfile
also wraps `/usr/bin/podman` to remote mode — see the gotcha below).

Backend tests (Postgres on the host's podman, venv inside the toolbox):

```bash
podman run --rm -d --name achievist-test-pg \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=pantheon_test \
  -p 5433:5432 postgres:16-alpine        # local port 5433; CI uses 5432
podman exec achievist-test-pg pg_isready -U postgres

toolbox run -c achievist-dev python3.12 -m venv /tmp/achievist-venv-test --copies
toolbox run -c achievist-dev /tmp/achievist-venv-test/bin/pip install --require-hashes -r requirements-dev.txt
toolbox run -c achievist-dev env TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/pantheon_test \
  REQUIRE_DB_TESTS=1 /tmp/achievist-venv-test/bin/pytest -q
podman rm -f achievist-test-pg            # teardown
```

The venv must be created AND run inside the toolbox (its python needs
libpython3.12 from there). `REQUIRE_DB_TESTS=1` makes a missing DB a failure,
not a skip.

Frontend tests/build:
```bash
toolbox run -c achievist-dev bash -c 'cd frontend && npm ci && npm test && npm run build'
```

Full stack locally (instead of `docker compose`): run podman-compose from the
toolbox against the host's podman socket — containers, volumes and the :8744
port all land on the host:

```bash
toolbox run -c achievist-dev bash -c 'cd ~/Projects/achievist && podman-compose -f docker-compose.yml up -d --build'
# → http://localhost:8744
```

Gotchas (verified on Kinoite 45 / podman 6.1.3): never run plain `podman` in
local mode inside a toolbox — it shares /run/user/1000 with the host and
deletes the host's pause/conmon pid files, which bricks the host podman service
("unable to create a new pause process"). The achievist-dev Containerfile wraps
`/usr/bin/podman` to `--remote --url unix:///run/user/1000/podman/podman.sock`
so this cannot happen; on a toolbox without the wrapper use
`CONTAINER_HOST=unix:///run/user/1000/podman/podman.sock`. Also,
`podman-compose up -d --build` will not replace a crash-looping container after
a rebuild — `podman rm -f <container>` on the host first. And after host
migrations, container records can survive without their writable layers
("container not known"): `podman rm -f <name>` on the host and recreate the
toolbox; exclude `~/.local/share/containers/storage` from migration copies
(containers are disposable; images survive).

## Version control and updates

### One-time: publish to GitHub

```bash
git init
git add .
git commit -m "Initial Achievist"
git branch -M main
git remote add origin git@github.com:<you>/pantheon.git
git push -u origin main
```

`.env` and `pgdata/` are gitignored — secrets and the database are never committed. Platform credentials live in the database, not in git, either way.

### Tier 1: pull and rebuild on the box

```bash
chmod +x update.sh   # once
./update.sh          # git pull --ff-only + docker compose up -d --build + prune
```

### Tier 2: build in CI, pull the image

`.github/workflows/build.yml` builds on every push to `main` and pushes to GHCR.

1. Push to `main` — GitHub Actions publishes `ghcr.io/<you>/pantheon:latest`
2. Deploy with `docker-compose.ghcr.yml` (set `<youruser>` first, `docker login ghcr.io` once if private)
3. Update: `docker compose -f docker-compose.ghcr.yml pull && docker compose -f docker-compose.ghcr.yml up -d`

`.gitattributes` pins shell and code files to LF so Windows checkouts don't break Linux scripts.

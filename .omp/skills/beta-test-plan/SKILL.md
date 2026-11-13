---
name: beta-test-plan
description: When a prerelease tag (vX.Y.Z-beta.N) is published on stable, diff it against the previous release and produce a tester-facing test plan with repro steps for every new feature, improvement and fix on the :beta channel.
---

# Beta release test plan

Trigger: a new prerelease exists on Neliel999/achievist —
`toolbox run -c dev-gh gh release list -R Neliel999/achievist` (prereleases are
marked), or locally `git tag -l 'v*-beta.*'`. Run once per prerelease, right
after the tag push (tag pushes are ask-gated; the release pipeline itself is
release.yml: pytest gate -> GHCR `:<tag>` + `:beta` -> GitHub prerelease).

## 1. Identify comparison bases

- TAG = the prerelease just published (e.g. v1.1.0-beta.1).
- BASE = previous RELEASE (newest non-prerelease tag):
  `git tag -l 'v*' --sort=-v:refname | grep -v -- '-' | head -1` (e.g. v1.0.0).
  The primary diff is always BASE..TAG — that is what testers upgrade from.
- PREV_BETA (optional, incremental re-test scope): the previous beta of the
  same X.Y.Z, `git tag -l 'vX.Y.Z-beta.*' --sort=-v:refname | sed -n 2p`.

## 2. Collect the changes

```sh
git fetch --tags   # if needed
git log --oneline BASE..TAG            # conventional commits = the changelog
git diff BASE...TAG --stat             # size of the change
git diff BASE...TAG -- <paths>         # read substantive hunks; skip pure CI/lockfile churn
```

Note tester-facing infra changes explicitly: compose files, env vars, ports,
image tags (e.g. docker-compose.ghcr-beta.yml, IMAGE_TAG, :beta channel).

## 3. Build the test plan

For every user-visible change (feat/fix/perf with a scope), one scenario:

- **What changed** — one line with commit sha + file.
- **Reproduce** — exact steps against the beta stack:
  `IMAGE_TAG=<TAG> docker compose -f docker-compose.ghcr-beta.yml up -d`
  (side-by-side on port 8745, isolated DB), then the concrete action: UI page,
  API call, or platform account to add (Steam ID + key, Xbox sign-in, PSN
  NPSSO, Epic ID, RA user+key), trigger a sync, and where to observe the result
  (page, `/api/...` JSON, app logs, DB row).
- **Expected result** — the observable that proves the change works.
- **Edge cases / risks** from the diff: auth changes, schema migrations, new
  env vars, rate limiting, error paths.

Always append a **regression smoke** section: the previous release's happy path
must still pass on the beta image — sign-in, add one account per platform, run
a sync, achievements/trophies render, backup job runs.

If the diff is CI/docs-only, the plan is: deploy the beta image, run one sync
per platform, confirm green — say so explicitly.

## 4. Deliver

- Write the plan as Markdown, show it via `out://`, and summarize in chat as a
  checklist with checkboxes per scenario.
- Testers use stub/test credentials only — never homelab prod secrets.
- Optionally append a "Test plan" section to the prerelease body with
  `gh release edit <TAG> -R Neliel999/achievist --notes ...` — only on explicit
  user request; never edit releases unprompted.
- Tag pushes remain ask-gated; this skill never pushes anything.

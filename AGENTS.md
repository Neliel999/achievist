# Achievist fork agent guide

## Context

This is a maintained thin-patch fork of mayberts/achievist (dormant upstream,
last commit 2026-09-19). Goal: carry a minimal, rebaseable patch set on top of
upstream main, with versioned releases. The fork is designed to shrink to zero
diff if upstream revives.

## Repo topology (invariant)

- `main` = fast-forward-only mirror of upstream main. NEVER commit here.
- `stable` = release branch = upstream main + small labeled patch commits.
- Tags (SemVer: v1.0.0, v1.0.1, v1.1.0 …) live only on `stable`.
- Remotes: origin (fork), upstream (mayberts), fernando (FernandoOMelo).
  The `fernando` remote can be removed once its patch is carried on stable.

## Workflow rules

- Work happens in a per-session git worktree, created as a SIBLING of the main
  clone: `git worktree add ../achievist-<topic> -b <topic> stable` from
  ~/Projects/achievist. Never commit on stable/main checkouts directly.
- Patch discipline: one fix = one small commit, conventional-commit style
  (`fix(psn): ...`). Never squash divergent changes into one commit.
- Git add/commit only in worktrees; `git push` (any branch, any tag) is
  ask-gated: prepare everything, then request approval.
- After a topic branch merges into stable, delete the branch locally and on
  origin. Merged branches must not linger.
- Rebase procedure when upstream moves: fetch upstream, fast-forward main,
  rebase stable onto main, drop patches upstream superseded, run pytest,
  report the resulting patch diff summary before any push.

## Environment & secrets

- Dev/test uses stub credentials only (throwaway Postgres, fake API keys).
  Tests read `TEST_DATABASE_URL`; set `REQUIRE_DB_TESTS=1` so a missing DB
  fails the run instead of skipping the DB-backed suite.
- Real platform credentials (NPSSO, Steam API key, XBOX_CLIENT_ID) exist only
  in the deployed homelab instance. Never copy them into worktrees, tests,
  CI, or committed files. CI must remain secretless (GITHUB_TOKEN only).
- Toolchain: Python 3.12 venv (upstream pins, e.g. psycopg 3.2.3, have no
  wheels on newer Python); Postgres 16 test container on an isolated port.

## Dev loop

- Backend: FastAPI + Postgres. Tests: `pytest -q` (must pass before any
  release prep or rebase completion).
- Frontend: React + Vite under `frontend/`. e2e suite under `e2e/`.
- Releases: tag push `v*` on stable triggers GitHub Actions (pytest gate with
  DB -> GHCR image -> GitHub Release). Agents prepare the tag; the user
  approves the push.

## Release & versioning

- SemVer, starting at v1.0.0. Patch-level for carried fixes, minor for
  custom features, major for breaking changes.
- Tags are immutable once their release artifacts exist (image published or
  a compose fragment references the tag). A tag whose CI failed before
  publishing anything may be deleted and re-created; after that, upgrades
  are always a new tag.
- Homelab consumes the image by TAG (`ghcr.io/neliel999/achievist:v1.0.0`),
  so tag immutability is a hard requirement, not a nicety.

## Current patch set

- `0677d31` cherry-picked as ac51b66 (from fernando/fix-psn-profile-lookup,
  FernandoOMelo): PSN sync fix — _BASE .net->.com, profile lookup on legacy
  us-prof host with universalSearch fallback, trophy names/descriptions/icons
  from the title-level endpoint, play-time sync, db repair helper, plus
  tests/test_psn.py. Supersedes PR #298 (ec346c5), whose profile route is
  refused with 403 by PSN's edge.

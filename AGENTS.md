# Achievist fork agent guide

## Context

This is a maintained thin-patch fork of mayberts/achievist (dormant upstream,
last commit 2026-09-19). Goal: carry a minimal, rebaseable patch set on top of
upstream main, with versioned releases. The fork is designed to shrink to zero
diff if upstream revives.

## Repo topology (invariant)

- `main` = fast-forward-only mirror of upstream main. NEVER commit here.
- `stable` = release branch = upstream main + small labeled patch commits.
- Tags (CalVer, e.g. v2026.11.0) live only on `stable`.
- Remotes: origin (fork), upstream (mayberts), fernando (FernandoOMelo, PR #298
  patch source; remove once upstream merges it).

## Workflow rules

- Work happens in a per-session git worktree, never directly on stable/main.
- Patch discipline: one fix = one small commit, conventional-commit style
  (`fix(psn): ...`). Never squash divergent changes into one commit.
- Git add/commit only in worktrees; `git push` (any branch, any tag) is
  ask-gated: prepare everything, then request approval.
- Rebase procedure when upstream moves: fetch upstream, fast-forward main,
  rebase stable onto main, drop patches upstream superseded, run pytest,
  report the resulting patch diff summary before any push.

## Environment & secrets

- Dev/test uses stub credentials only (throwaway Postgres, fake API keys).
  See `.env.example` for the key names.
- Real platform credentials (NPSSO, Steam API key, XBOX_CLIENT_ID) exist only
  in the deployed homelab instance. Never copy them into worktrees, tests,
  CI, or committed files. CI must remain secretless (GITHUB_TOKEN only).

## Dev loop

- Backend: FastAPI + Postgres. Tests: `pytest -q` (must pass before any
  release prep or rebase completion).
- Frontend: React + Vite under `frontend/`. e2e suite under `e2e/`.
- Releases: tag push `v*` on stable triggers GitHub Actions (test gate ->
  GHCR image -> GitHub Release). Agents prepare the tag; the user approves
  the push.

## Current patch set

- PR #298 cherry-pick (FernandoOMelo): PSN trophy sync fix — trophy API base
  URL update + accountId nested under `profile`. Source branch on the
  `fernando` remote. Also verify `app/platforms/psn.py:13`
  (m.np.playstation.net -> .com typo) is covered by it.

---
name: worktree-flow
description: Git worktree/branch discipline for the achievist fork: sibling worktrees off stable, one conventional commit per fix, pushes ask-gated (agents never push).
---

From AGENTS.md (canonical):

- Main clone: `~/Projects/achievist`, checked out on `stable`.
- Work happens in a SIBLING worktree:
  `cd ~/Projects/achievist && git worktree add ../achievist-<topic> -b <topic> stable`
- NEVER commit on the `main`/`stable` checkouts directly. `main` is a
  fast-forward-only mirror of upstream — never commit there at all.
- One fix = one small conventional-commit (`fix(psn): ...`, `feat(...):`,
  `ci(...):`, `docs(...):`). Never squash divergent changes into one commit.
- Push (any branch, any tag) is ASK-GATED: agents prepare the branch/commit
  and report; only the user approves and runs the push.
- Topic branches are opened as PRs against stable (base stable); the user
  reviews and merges on GitHub. stable is PR-only — branch protection on
  origin/stable blocks direct pushes and local merges. After the PR merges,
  delete the branch locally and on origin.
- When upstream moves, use the `rebase-stable` skill instead of merging.

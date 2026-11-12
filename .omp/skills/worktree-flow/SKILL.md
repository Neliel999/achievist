---
name: worktree-flow
description: Git worktree/branch discipline for the achievist fork: sibling worktrees off stable, one conventional commit per fix, branch pushes/PRs ungated (user judges PRs), tag pushes ask-gated.
---

From AGENTS.md (canonical):

- Main clone: `~/Projects/achievist`, checked out on `stable`.
- Work happens in a SIBLING worktree:
  `cd ~/Projects/achievist && git worktree add ../achievist-<topic> -b <topic> stable`
- NEVER commit on the `main`/`stable` checkouts directly. `main` is a
  fast-forward-only mirror of upstream — never commit there at all.
- One fix = one small conventional-commit (`fix(psn): ...`, `feat(...):`,
  `ci(...):`, `docs(...):`). Never squash divergent changes into one commit.
- Branch pushes and PR creation are NOT ask-gated: push the branch and open
  the PR when the work is finished; the user validates or refuses the PR.
  TAG pushes remain ask-gated (they trigger releases): prepare, user approves.
- Topic branches are opened as PRs against stable (base stable); the user
  reviews and merges on GitHub. stable is PR-only — branch protection on
  origin/stable blocks direct pushes and local merges. After the PR merges,
  delete the branch locally and on origin.
- When upstream moves, use the `rebase-stable` skill instead of merging.

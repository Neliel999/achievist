---
name: worktree-flow
description: Git worktree/branch discipline for the achievist fork: sibling worktrees off dev, one conventional commit per fix, PRs base dev, branch pushes/PRs ungated (user judges PRs), tag pushes ask-gated.
---

From AGENTS.md (canonical):

- Main clone: `~/Projects/achievist`, checked out on `stable`.
- Work happens in a SIBLING worktree:
  `cd ~/Projects/achievist && git worktree add ../achievist-<topic> -b <topic> dev`
- NEVER commit on the `main`/`dev`/`stable` checkouts directly. `main` is a
  fast-forward-only mirror of upstream — never commit there at all.
- One fix = one small conventional-commit (`fix(psn): ...`, `feat(...):`,
  `ci(...):`, `docs(...):`). Never squash divergent changes into one commit.
- Branch pushes and PR creation are NOT ask-gated: push the branch and open
  the PR when the work is finished; the user validates or refuses the PR.
  TAG pushes remain ask-gated (they trigger releases): prepare, user approves.
- Topic branches are opened as PRs against dev (base dev — dev is the repo
  default branch); the user reviews and merges on GitHub. dev is PR-only —
  branch protection on origin/dev blocks direct pushes. After the PR merges,
  delete the branch locally and on origin.
- stable accepts ONLY the promotion PR from dev (head=dev), enforced by the
  `stable-pr-guard` check in test.yml plus branch protection (green checks;
  review count is 0 because a single maintainer cannot self-approve — the
  merge click is the human gate). Never open any other PR against stable.
- When upstream moves, use the `rebase-stable` skill instead of merging.

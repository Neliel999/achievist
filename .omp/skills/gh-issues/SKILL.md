---
name: gh-issues
description: Read GitHub issues/PRs for the achievist fork (issues re-enabled 2026-11-10) and upstream mayberts/achievist. Host gh is a static binary at ~/.local/bin/gh; toolbox dev-gh also has gh 2.97.0.
---

# Where gh lives (verified on this workstation, 2026-11-10)
- Host: static gh 2.97.0 at `~/.local/bin/gh` (first on omp's PATH), auth in
  `~/.config/gh/hosts.yml` (user Neliel999, `repo` scope). Plain `gh ...` works
  in bash; `issue://<owner>/<repo>[/<n>]` works in any omp session started after
  the install (sessions running since before it cached "gh not installed").
- Toolbox `dev-gh` also carries gh 2.97.0 and python3.12: `toolbox run -c dev-gh ...`
  (needed for the test venv; a `~/.local/bin/gh` wrapper around `toolbox run`
  HANGS from omp's process tree — do not use that pattern).

# What to read
- Fork `Neliel999/achievist` (issues re-enabled via repo Settings UI,
  2026-11-10; `hasIssuesEnabled=true`):
  `gh issue list -R Neliel999/achievist --state open --json number,title,labels,body`
  `gh pr list -R Neliel999/achievist --state open --json number,title,labels,body,author`
  Recognize and do not dispatch: PR #298 "Fix PlayStation Network trophy sync"
  (superseded by stable patch ac51b66).
- Upstream `mayberts/achievist` (issues enabled, currently zero open):
  `gh issue list -R mayberts/achievist --state open --json number,title,labels,body`
  `gh pr list -R mayberts/achievist --state open --json number,title,labels,body`
  (merged PRs 291+ document upstream movement; PRs are visible via the issues API).
- Parse JSON with `gh --jq '...'` or python3.12.

# upstream-sync
- Label `upstream-sync` = rebase signal → run the `rebase-stable` skill; never
  dispatch it as feature work.
- `.github/workflows/upstream-watch.yml` creates that issue on the fork — works
  now that fork issues are re-enabled. Regardless of the notification, detect
  upstream movement directly:
  `git fetch upstream main && git rev-list --count origin/main..upstream/main`
  (nonzero ⇒ rebase).

---
name: gh-issues
description: Read GitHub issues/PRs for the achievist fork and upstream mayberts/achievist. gh is not on the host PATH — it lives in the dev-gh toolbox; the fork has issues disabled, so PRs are the fork channel.
---

# Where gh lives (verified on this workstation)
- Host PATH has NO gh. Toolbox `dev-gh` has gh 2.97.0, authenticated as
  Neliel999 (keyring, `repo` scope). Run everything as:
  `toolbox run -c dev-gh gh ...`
- Native `issue://` needs gh on the omp host PATH — there is none. A
  `~/.local/bin/gh` wrapper around `toolbox run` was tried and HANGS when
  invoked from omp's process tree (flatpak-spawn GLib thread error, verified
  2026-11-10), so do not rely on it: always call gh via bash as
  `toolbox run -c dev-gh gh ...`.

# What to read
- Fork `Neliel999/achievist`: issues are DISABLED (verified
  `hasIssuesEnabled=false`) — intake is PRs:
  `toolbox run -c dev-gh gh pr list -R Neliel999/achievist --state open --json number,title,labels,body,author`
  Recognize and do not dispatch: PR #298 "Fix PlayStation Network trophy
  sync" (superseded by stable patch ac51b66).
- Upstream `mayberts/achievist`: issues enabled (currently zero open) —
  `gh issue list -R mayberts/achievist --state open --json number,title,labels,body`
  and `gh pr list -R mayberts/achievist --state open --json number,title,labels,body`
  (merged PRs 291+ document upstream movement; PRs are visible via the issues API).
- Parse JSON with `gh --jq '...'` or `toolbox run -c dev-gh python3.12`.

# upstream-sync
- Label `upstream-sync` = rebase signal → run the `rebase-stable` skill; never
  dispatch it as feature work.
- `.github/workflows/upstream-watch.yml` creates that issue on the FORK, where
  issues are disabled, so `gh issue create` currently fails there. Until
  issues are enabled on the fork, detect upstream movement directly:
  `git fetch upstream main && git rev-list --count origin/main..upstream/main`
  (nonzero ⇒ rebase).

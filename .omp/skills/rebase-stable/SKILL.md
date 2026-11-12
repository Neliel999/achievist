---
name: rebase-stable
description: Rebase procedure when upstream mayberts/achievist moves (upstream-sync signal): fetch upstream, fast-forward main, rebase stable, drop superseded patches, run the test loop, report the patch diff before any push.
---

From AGENTS.md. Trigger: an `upstream-sync`-labeled item (see gh-issues) or
`git fetch upstream main && git rev-list --count origin/main..upstream/main` > 0.

```sh
cd ~/Projects/achievist
git fetch upstream main
# main is a fast-forward-only mirror — never commit on it
git checkout main && git merge --ff-only upstream/main && git push origin main   # branch push: not ask-gated, push when done
# rebase the release branch
git checkout stable && git rebase main
# drop patches upstream superseded (git rebase does this automatically when
# the patch-id matches; verify none of our labeled patches conflict semantically)
```

- Then run the full DB-backed suite via the `test-loop` skill (REQUIRE_DB_TESTS=1).
- Report the resulting patch set BEFORE any push:
  `git log origin/main..stable --oneline` and `git diff origin/main...stable --stat`.
- Current carried patch: ac51b66 (PSN sync fix, supersedes upstream PR #298).
- Branch protection makes stable PR-only, but this procedure is the sanctioned
  exception: after the rebase, push stable with `git push --force-with-lease
  origin stable` (branch pushes are not ask-gated, but always report the patch
  set first — see above).
- Tag pushes remain ask-gated; branch pushes and PR creation do not.

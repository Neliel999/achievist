---
name: rebase-stable
description: Rebase procedure when upstream mayberts/achievist moves (upstream-sync signal): fetch upstream, fast-forward main, rebase dev onto main, run the test loop, then promote dev -> stable via PR; report the patch diff before any push.
---

From AGENTS.md. Trigger: an `upstream-sync`-labeled item (see gh-issues) or
`git fetch upstream main && git rev-list --count origin/main..upstream/main` > 0.

```sh
cd ~/Projects/achievist
git fetch upstream main
# main is a fast-forward-only mirror — never commit on it
git checkout main && git merge --ff-only upstream/main && git push origin main   # branch push: not ask-gated, push when done
# rebase the integration branch
git checkout dev && git rebase main
# drop patches upstream superseded (git rebase does this automatically when
# the patch-id matches; verify none of our labeled patches conflict semantically)
```

- Then run the full DB-backed suite via the `test-loop` skill (REQUIRE_DB_TESTS=1).
- Report the resulting patch set BEFORE any push:
  `git log origin/main..dev --oneline` and `git diff origin/main...dev --stat`.
- Current carried patch: ac51b66 (PSN sync fix, supersedes upstream PR #298).
- Branch protection makes dev PR-only, but this procedure is the sanctioned
  exception: after the rebase, push dev with `git push --force-with-lease
  origin dev` (branch pushes are not ask-gated, but always report the patch
  set first — see above). Use the runtime credential-helper push from the
  `gh-pat-push-achievist` skill, and pin
  `--force-with-lease=refs/heads/dev:<old-sha>` because pushing via the HTTPS
  URL does not update refs/remotes/origin/dev.
- stable is NOT rebased or pushed directly anymore: after dev is rebased and
  green, promote with a PR dev -> stable (base stable, head dev) — the only PR
  stable accepts (stable-pr-guard). Merge it on GitHub; then cut the next tag
  on the branch the tag rules require (prerelease `vX.Y.Z-beta.N` on dev,
  release `vX.Y.Z` on stable).
- Tag pushes remain ask-gated; branch pushes and PR creation do not.

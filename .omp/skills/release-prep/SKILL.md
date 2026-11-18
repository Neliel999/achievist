---
name: release-prep
description: Release/tag rules for the achievist fork — SemVer from v1.0.0, prerelease tags on dev, release tags only on stable, immutability once artifacts exist, prepare the tag but never push (user approves).
---

From AGENTS.md:

- SemVer starting at v1.0.0: patch = carried fixes, minor = custom features,
  major = breaking changes. Prerelease tags `vX.Y.Z-beta.N` are cut on `dev`;
  release tags `vX.Y.Z` ONLY on `stable`. release.yml enforces the placement:
  a `-` tag's commit must be contained in origin/dev, a final tag's in
  origin/stable.
- Tag immutability is a hard requirement: the homelab consumes the image BY
  TAG (`ghcr.io/neliel999/achievist:vX.Y.Z`). Once release artifacts exist
  (GHCR image published or a compose fragment references the tag), a tag is
  immutable — upgrades are always a NEW tag. A tag whose CI failed before
  publishing anything may be deleted and re-created.
- `v*` tag push triggers `.github/workflows/release.yml`: tag-placement
  guard -> pytest gate (DB-backed) -> GHCR image (`:<tag>` + channel tag) ->
  GitHub Release. Final tags push `:stable` and publish a full release;
  prerelease tags push `:beta` and publish a GitHub prerelease.
- Promotion flow: after a beta round on dev passes, merge the promotion PR
  dev -> stable (green checks + 1 approving review), THEN cut the release tag
  on stable. Agents PREPARE the tag: `git tag vX.Y.Z stable` (beta:
  `git tag vX.Y.Z-beta.N dev`) after the test loop is green, then STOP. The
  push is ask-gated — the user approves it.
- Beta-cycle discipline: during an active round for X.Y.Z, only that line's
  hotfixes merge into dev; next-minor (X.Y+1.0) work waits until vX.Y.Z is
  tagged on stable. Tag vX.Y.Z-beta.N+1 from the dev tip AFTER the hotfixes
  merge. Exception: if the delta since the last beta tag touches no runtime
  paths (`git diff --name-only vX.Y.Z-beta.N..dev` vs app/, frontend/, e2e/,
  Dockerfile, requirements*), promote/release the moved tip directly.
  release/X.Y.Z branches are NOT in use yet — introduce them only if a big
  next-minor PR ever cannot wait out a round.
- Changelog: release notes are generated from commits since the last tag
  (`softprops/action-gh-release`), so keep commits conventional — they become
  the release notes.

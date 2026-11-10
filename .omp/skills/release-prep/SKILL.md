---
name: release-prep
description: Release/tag rules for the achievist fork — SemVer from v1.0.0, tags only on stable, immutability once artifacts exist, prepare the tag but never push (user approves).
---

From AGENTS.md:

- SemVer starting at v1.0.0: patch = carried fixes, minor = custom features,
  major = breaking changes. Tags live ONLY on `stable`.
- Tag immutability is a hard requirement: the homelab consumes the image BY
  TAG (`ghcr.io/neliel999/achievist:vX.Y.Z`). Once release artifacts exist
  (GHCR image published or a compose fragment references the tag), a tag is
  immutable — upgrades are always a NEW tag. A tag whose CI failed before
  publishing anything may be deleted and re-created.
- `v*` tag push on stable triggers `.github/workflows/release.yml`:
  pytest gate (DB-backed) → GHCR image (`:<tag>` + `:stable`) → GitHub Release.
- Agents PREPARE the tag: `git tag vX.Y.Z stable` (after the test loop is
  green), then STOP. The push is ask-gated — the user approves it.
- Changelog: release notes are generated from commits since the last tag
  (`softprops/action-gh-release`), so keep commits conventional — they become
  the release notes.

---
name: platform-sync
description: Contract for adding or fixing a platform sync module in app/platforms/ — Platform ABC, PLATFORMS registry, connect-schema rules, per-platform tests, stub-credentials-only rule.
---

# Contract (app/platforms/base.py)
- Subclass `Platform`; set `KEY` (must equal its registry key), `LABEL`
  (non-empty), `AUTH_TYPE` (`form` or `oauth`), `CONNECT_FIELDS`, and
  `EXTERNAL_ID` for fixed-identity platforms (gw2, xbox, ubisoft).
- `CONNECT_FIELDS` entries: `{"name", "label", "type": text|password|select,
  "required", "help"?, "secret"?}`; `select` fields need `options`. The field
  named `external_id` becomes the account's unique id. `connect_schema()`
  serializes all of this for the ConnectModal.
- Implement `async def sync(self, account: dict, conn) -> None` — pull data,
  upsert via `app/db.py` helpers (`upsert_linked_account`,
  `upsert_platform_game`, `upsert_user_game`, `upsert_achievement`,
  `get_earned_counts`, ...). Use `self.cred(account, key, default)` and
  `self._inc("progress_key")` for sync progress.
- Register the class in `app/platforms/__init__.py` `PLATFORMS` dict.

# Enforcement and tests
- `tests/test_platforms_registry.py` parametrizes over PLATFORMS and fails on
  any contract violation — run it for every platform change.
- Add/extend `tests/test_<key>.py` with STUB credentials only. Real NPSSO /
  Steam keys / XBOX_CLIENT_ID never enter tests, CI, or git (AGENTS.md).
- HTTP via `httpx.AsyncClient(timeout=...)`; respect
  `config.REQUEST_DELAY_SECONDS` between external calls.
- External endpoints change (see the PSN patch ac51b66 for the pattern:
  host migration, fallback lookups, title-level trophy detail) — when an
  upstream API 403s/404s, check for a working alternative endpoint before
  redesigning.

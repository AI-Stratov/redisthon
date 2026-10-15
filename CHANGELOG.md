# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-12

First release on PyPI.

### Added

- `RedisSession`, a Telethon session that stores the auth key, data center and
  takeout ID in Redis or Dragonfly.
- Entity cache with lookups by ID (marked and unmarked), username, phone and
  display name.
- Update states, so Telethon can resume from them after a restart.
- Sent-file cache for photos and documents.
- `ttl_seconds` on every key, refreshed on each `save()`.
- `delete()` removes all keys of the session; Telethon calls it on `log_out()`.
- `list_sessions()` returns all sessions under a key prefix.
- `RedisClient`, which can be shared between sessions through `redis_client=`.
- `get_health_info()` and `get_statistics()`.
- Type hints (`py.typed`), checked with `mypy --strict`.

### Changed since the unreleased code on `main`

Only relevant if you installed from Git before this release.

- `get_update_states()` returns `(entity_id, State)` pairs and
  `get_entity_rows_by_*()` return one `(id, hash)` tuple or `None`, as Telethon
  expects. The old return types broke `TelegramClient`.
- `clone()` returns an empty in-memory session, like `SQLiteSession.clone()`.
- `close()` no longer closes a `RedisClient` passed in by the caller.
- Redis failures raise `ConnectionError`; serialization failures raise
  `SerializationError` instead of `ConnectionError`.
- Sent-file cache fields include the file type. Entries written before this
  release are ignored.
- `redisthon.schemas` was removed.

[Unreleased]: https://github.com/AI-Stratov/redisthon/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AI-Stratov/redisthon/releases/tag/v0.1.0

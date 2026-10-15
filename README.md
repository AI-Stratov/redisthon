# redisthon

[![CI](https://github.com/AI-Stratov/redisthon/actions/workflows/ci.yml/badge.svg)](https://github.com/AI-Stratov/redisthon/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/redisthon.svg)](https://pypi.org/project/redisthon/)
[![Python](https://img.shields.io/pypi/pyversions/redisthon.svg)](https://pypi.org/project/redisthon/)

Telethon session storage in Redis or Dragonfly, for Telegram bots and userbots
that run in containers or move between hosts, where a local `.session` file is
inconvenient.

## Install

```bash
pip install redisthon
```

## Usage

```python
import asyncio

from telethon import TelegramClient

from redisthon import RedisSession

API_ID = 12345  # from https://my.telegram.org
API_HASH = '0123456789abcdef0123456789abcdef'


async def main() -> None:
    session = RedisSession('my_account', host='localhost', port=6379)
    async with TelegramClient(session, API_ID, API_HASH) as client:
        me = await client.get_me()
        print(me.username)


asyncio.run(main())
```

The first run asks for a phone number and login code. Later runs, on this or any
other host that can reach the same Redis, reuse the stored session.

Other `RedisSession` options: `db`, `username`, `password`, `key_prefix`
(default `redisthon:session`), `ttl_seconds` (default 30 days, `0` disables
expiry), `save_entities` (default `True`), `is_dragonfly`, and pool settings
(`max_connections`, `connection_timeout`, `socket_keepalive`).
To share one connection pool between sessions, create a `RedisClient` and pass
it as `redis_client=`. Sessions do not close a client they were given.

## Features

- Auth key, data center and takeout ID are stored on every `save()` and loaded
  when the session is created.
- Entity cache: users and chats Telethon sees are stored, and
  `get_input_entity()` resolves them by ID, username, phone or name.
- Update states (pts, qts, seq, date) are stored per entity.
- Sent-file cache for photos and documents.
- Every key gets `ttl_seconds`. Each `save()` refreshes the TTL of all four
  keys, so an active session keeps its caches.
- `delete()`, which `client.log_out()` calls, removes all keys of the session.
- `list_sessions()` returns the names of all sessions under the key prefix.
- `clone()` returns an empty in-memory session, like `SQLiteSession.clone()`.
  Telethon uses it for CDN connections, which therefore never touch Redis.
- Dragonfly: `is_dragonfly=True` only skips `SELECT db`. The integration tests
  run against both Redis and Dragonfly.
- `get_health_info()` (ping, server info, key names) and `get_statistics()`
  (cached entity, update state and file counts).
- Type hints ship with the package (`py.typed`) and pass `mypy --strict`.

Keys for a session named `name` with the default prefix:

```
redisthon:session:name:data           msgpack: auth key, DC, takeout ID
redisthon:session:name:entities       hash: entity ID -> base64(msgpack)
redisthon:session:name:update_states  hash: entity ID -> base64(msgpack)
redisthon:session:name:sent_files     hash: <md5 hex>_<size>_<photo|document> -> base64(msgpack)
```

## Limitations

- The Redis client is synchronous, because Telethon's session interface is.
  Every session call blocks the event loop for one Redis round trip.
- With the default TTL, a session that nobody starts for 30 days expires and the
  account has to log in again. Set `ttl_seconds=0` to keep it.
- Lookups by username, phone or name scan the whole entity hash.
- Redis errors while reading or writing entities, update states and sent files
  are logged and treated as a cache miss. Errors in `save()` and in loading the
  session raise `SessionError`.
- Do not run two clients on one session at the same time. Telegram rejects the
  duplicated auth key.
- There is no `ssl` option.

## Compatibility

Tested in CI:

| Component | Versions                                     |
|-----------|----------------------------------------------|
| Python    | 3.11, 3.12, 3.13, 3.14                       |
| Telethon  | 1.34.0 (lowest allowed), 1.45.0 (locked)     |
| redis-py  | 5.0.0 (lowest allowed), 8.1.0 (locked)       |
| Redis     | 6.2, 7.4, 8.10                               |
| Dragonfly | 2.0                                          |

## Development

Uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy redisthon
uv run pytest --cov=redisthon    # unit tests, no server needed, 100% coverage required
```

Integration tests need Redis on `REDIS_HOST:REDIS_PORT` (default
`localhost:6379`). Dragonfly tests run when `DRAGONFLY_PORT` is set.

```bash
docker run -d -p 6379:6379 redis:8.10
docker run -d -p 6380:6379 --ulimit memlock=-1 docker.dragonflydb.io/dragonflydb/dragonfly:v2.0.2
DRAGONFLY_PORT=6380 uv run pytest tests/integration
```

## Changes and security

See [CHANGELOG.md](CHANGELOG.md). Report vulnerabilities privately, as described
in [SECURITY.md](SECURITY.md); it also has a deployment checklist.

## License

MIT, see [LICENSE](LICENSE).

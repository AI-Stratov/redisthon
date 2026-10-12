# redisthon

[![CI](https://github.com/AI-Stratov/redisthon/actions/workflows/ci.yml/badge.svg)](https://github.com/AI-Stratov/redisthon/actions/workflows/ci.yml)

Telethon session storage in Redis or Dragonfly, for Telegram bots and userbots
that run in containers or move between hosts, where a local `.session` file is
inconvenient.

## Install

Install from GitHub until the first PyPI release:

```bash
pip install git+https://github.com/AI-Stratov/redisthon
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
it as `redis_client=`.

## Features

- Auth key, data center and takeout ID are stored on every `save()` and loaded
  when the session is created.
- Entity cache: users and chats Telethon sees are stored, and
  `get_input_entity()` resolves them by ID, username, phone or name.
- Update states (pts, qts, seq, date) are stored per entity.
- Sent-file cache for photos and documents.
- Every key gets `ttl_seconds`, refreshed on each write.
- Dragonfly: `is_dragonfly=True` only skips `SELECT db`. The integration tests
  run against both Redis and Dragonfly.
- `get_health_info()` (ping, server info, key names) and `get_statistics()`
  (cached entity, update state and file counts).

Keys for a session named `name` with the default prefix:

```
redisthon:session:name:data           msgpack: auth key, DC, takeout ID
redisthon:session:name:entities       hash: entity ID -> base64(msgpack)
redisthon:session:name:update_states  hash: entity ID -> base64(msgpack)
redisthon:session:name:sent_files     hash: <md5 hex>_<size> -> base64(msgpack)
```

## Limitations

- The Redis client is synchronous, because Telethon's session interface is.
  Every session call blocks the event loop for one Redis round trip.
- With the default TTL, a session that nobody starts for 30 days expires and the
  account has to log in again. Set `ttl_seconds=0` to keep it.
- Lookups by username, phone or name scan the whole entity hash.
- `delete()`, which `client.log_out()` calls, closes the connection pool but
  leaves the keys in Redis.
- `list_sessions()` returns only the current session's name.
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
| Redis     | 6.2, 7.4, 8.2                                |
| Dragonfly | 1.34                                         |

## Development

Uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy redisthon
uv run pytest                    # unit tests, no server needed
```

Integration tests need Redis on `REDIS_HOST:REDIS_PORT` (default
`localhost:6379`). Dragonfly tests run when `DRAGONFLY_PORT` is set.

```bash
docker run -d -p 6379:6379 redis:7.4
docker run -d -p 6380:6379 --ulimit memlock=-1 docker.dragonflydb.io/dragonflydb/dragonfly:v1.34.1
DRAGONFLY_PORT=6380 uv run pytest tests/integration
```

## License

MIT, see [LICENSE](LICENSE).

# Security

## Supported versions

Security fixes go into the latest release. Upgrade to the newest version before
reporting.

## Reporting a vulnerability

Report privately through
[GitHub security advisories](https://github.com/AI-Stratov/redisthon/security/advisories/new).
Do not open a public issue. Expect a first reply within a week.

## What redisthon stores

The `<prefix>:<name>:data` key holds the session's Telegram auth key. Anyone who
can read it can act as that Telegram account until the key is revoked: from the
account's active sessions in Telegram, or with `client.log_out()`, which also
deletes the keys. Treat the Redis instance like a password store.

## Deployment checklist

- Do not expose Redis or Dragonfly to the internet. Keep it on a private network.
- Require authentication. With Redis 6+, give the application its own ACL user,
  limited to the session keys and the commands redisthon uses:

  ```
  ACL SETUSER redisthon on >PASSWORD ~redisthon:session:* resetchannels -@all +get +set +expire +exists +del +scan +hset +hget +hscan +hlen +ping +info
  ```

  Then pass `username='redisthon', password='PASSWORD'` to `RedisSession`.

  Adjust `~redisthon:session:*` if you change `key_prefix`.
- redisthon has no `ssl` option. If traffic leaves a trusted network, use a TLS
  tunnel or a pre-configured `redis.Redis(ssl=True, ...)` passed as
  `RedisClient(redis_client=...)`. The second option is not covered by tests.
- Snapshots and replicas contain the auth keys too. Protect RDB/AOF files and
  backups accordingly.

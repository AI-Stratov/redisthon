## What and why

<!-- The change and the problem it solves. Link the issue if there is one. -->

## Checklist

- [ ] Tests cover the change (`uv run pytest --cov=redisthon` stays at 100%)
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy redisthon` pass
- [ ] Integration tests pass if storage or Redis calls changed (`uv run pytest tests/integration`)
- [ ] `CHANGELOG.md` has an entry under Unreleased if users will notice the change

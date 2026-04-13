# AGENTS.md — Guidelines for AI agents working on this repository

## Project overview

Home Assistant custom integration that exposes Claude.ai session and weekly usage as native sensors.

```
config/custom_components/claude_usage/   ← integration source (canonical location)
tests/                                   ← pytest smoke tests
scripts/                                 ← standalone CLI helper
```

## Architecture

| File | Role |
|------|------|
| `coordinator.py` | `DataUpdateCoordinator` — polls `GET /api/organizations/{org_id}/usage` every 60 s, auto-renews cookies, accumulates `UsageMetrics` |
| `sensor.py` | 8 usage sensors + 5 diagnostic sensors; `ClaudeUsageSensorDescription` carries a `value_fn` (usage) or `metric_fn` (diagnostics) |
| `config_flow.py` | Three flows: `user` (initial setup), `reauth_confirm` (triggered by `ConfigEntryAuthFailed`), `reconfigure` (manual update) |
| `__init__.py` | Entry setup/unload + `async_get_config_entry_diagnostics` |
| `const.py` | All constants — change `UPDATE_INTERVAL` here to adjust poll frequency |

## Running tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

Tests use `pytest-homeassistant-custom-component` for HA fixtures and `aioresponses` for HTTP mocking. No real network calls are made.

## Commit conventions

Use **Conventional Commits** with a single subject line, no body:

```
feat: add weekly token-count sensor
fix: url-encode cf_clearance cookie to avoid latin-1 error
chore: bump pytest-homeassistant-custom-component to 0.14
test: add coordinator cookie-renewal smoke test
docs: update README installation steps
```

Types: `feat`, `fix`, `chore`, `test`, `docs`, `refactor`, `ci`.

## Key constraints

- **No `br` in `Accept-Encoding`** — the server may return brotli-compressed responses that aiohttp cannot decode without the optional `brotli` package. Keep `"accept-encoding": "gzip, deflate"`.
- **URL-encode cookies** — `cf_clearance` contains unicode characters; always wrap values with `urllib.parse.quote(..., safe='')`.
- **`ConfigEntryAuthFailed`** — raise this (not `UpdateFailed`) on 401/403 so HA triggers the native reauth notification automatically.
- **Diagnostic sensors are always available** — their `available` property returns `True` unconditionally; they read from `coordinator.metrics`, not `coordinator.data`.
- Integration files live under `config/custom_components/` (not at the repo root) so the `config/` directory can be mounted directly as the HA config volume during development.

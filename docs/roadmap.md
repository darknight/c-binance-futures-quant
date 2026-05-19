# Roadmap

This roadmap captures the current modernization state after the migration away from the original Aliyun/MySQL/Bottle/React 16/C++ path.

## Completed foundations

- Package management: `uv`, `pyproject.toml`, `uv.lock`
- Configuration: `.env` + `settings.py` with `pydantic-settings`
- Database: PostgreSQL, SQLModel/SQLAlchemy, Alembic migrations
- Backend: FastAPI in `web_server/`
- Frontend: React 19 + Vite in `web-front/`
- WebSocket aggregation: Rust `ws-server/`
- Notifications/storage: Telegram + Cloudflare R2-compatible S3 client
- Local/container development: Docker Compose and documented Podman flow

## Phase 1: Cognitive debt cleanup

Goal: make the active architecture obvious and reduce old/new confusion.

Status: completed for the current documentation and route-coverage pass.

Completed in this phase:

- Root README now starts with the maintained architecture and local development flow.
- Legacy upstream README content is preserved but marked as historical context.
- `web-front/README.md` describes the actual dashboard instead of the Vite template.
- Legacy paths are explicitly marked as deprecated or reference-only:
  - `webServer.py`
  - `wsServer.cpp`
  - `react-front/`
  - `dataPy/uploadDataPy.py`
- Web server route tests now include dashboard router registration.

Deferred owner decisions:

- Decide when `react-front/` can be deleted.
- Decide when `wsServer.cpp` can move from protocol reference to removed legacy file.
- Decide whether `afterTrade/webOssUpdate.py` remains as static snapshot publishing or is replaced by FastAPI/dashboard-only flows.

## Phase 2: Local dry-run loop

Goal: run a full local loop without real Binance orders.

Suggested tasks:

- Add a `ws-server` smoke producer/consumer that writes tick/kline/position/balance data and verifies the `B` snapshot format.
- Add a dry-run trading mode that records order intent instead of calling Binance.
- Make `simpleTrade.py` run at least one complete dry-run loop.
- Provide one command or Makefile target for PostgreSQL, migrations, demo data, backend, and frontend.

## Phase 3: Strategy runner

Goal: make custom strategies an interface instead of edits inside a large script.

Suggested boundary:

```python
class Strategy:
    def on_market_snapshot(self, ctx) -> list[Signal]:
        ...
```

Suggested tasks:

- Extract market data adapter from `simpleTrade.py`.
- Extract execution adapter for order placement, cancellation, retries, and recording.
- Keep strategy code focused on signal generation.
- Add unit tests for strategy decisions from kline/position inputs.
- Add paper-trading fills and PnL simulation.

## Phase 4: Pre-live risk hardening

Goal: prevent strategy bugs from becoming real losses.

Suggested tasks:

- Global trading switch, default off.
- Per-symbol max position and per-order notional limits.
- Daily loss, consecutive loss, and API error circuit breakers.
- Client order ID convention and duplicate-signal suppression.
- Structured audit logs for every real order path.

## Phase 5: Deployment and observability

Goal: make the system operable on DigitalOcean/Dokploy.

Suggested tasks:

- Health checks and restart policies for each service.
- Production `.env` field inventory.
- PostgreSQL backup and restore docs.
- Standard stdout logging strategy, later attach logs to Grafana/Loki or platform logs.
- Enable `ws-server` token auth in production.
- Keep internal-only ports off the public internet.

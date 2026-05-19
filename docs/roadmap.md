# Roadmap

This roadmap captures the current modernization state after the migration away from the original Aliyun/MySQL/Bottle/React 16/C++ path.

## Completed foundations

- Package management: `uv`, `pyproject.toml`, `uv.lock`
- Configuration: `.env` + `settings.py` with `pydantic-settings`
- Database: PostgreSQL, SQLModel/SQLAlchemy, Alembic migrations
- Backend: FastAPI in `web_server/`
- Frontend: React 19 + Vite in `frontend/web-front/`
- WebSocket aggregation: Rust `ws/ws-server/`
- Notifications/storage: Telegram + Cloudflare R2-compatible S3 client
- Local/container development: Docker Compose and documented Podman flow

## Phase 1: Cognitive debt cleanup

Goal: make the active architecture obvious and reduce old/new confusion.

Status: completed for the current documentation and route-coverage pass.

Completed in this phase:

- Root README now starts with the maintained architecture and local development flow.
- Legacy upstream README content is preserved but marked as historical context.
- `frontend/web-front/README.md` describes the actual dashboard instead of the Vite template.
- Active runtime code is grouped by responsibility under `services/`, `frontend/`, and `ws/`, while deprecated references live under `legacy/`.
- Legacy paths are explicitly marked as deprecated or reference-only:
  - `legacy/webServer.py`
  - `legacy/wsServer.cpp`
  - `legacy/react-front/`
  - `legacy/uploadDataPy.py`
- Web server route tests now include dashboard router registration.
- The repository layout reorganization is recorded in `docs/plans/repo-layout-reorganization.md`.

Deferred owner decisions:

- Decide when `legacy/react-front/` can be deleted.
- Decide when `legacy/wsServer.cpp` can move from protocol reference to removed legacy file.
- Decide whether `services/post_trade/webOssUpdate.py` remains as static snapshot publishing or is replaced by FastAPI/dashboard-only flows.
- Decide whether `web_server/`, `app/`, and shared Python helpers should later move under a packaged backend namespace.

## Phase 2A: Deterministic Local Loop

Goal: prove the internal trading loop can run predictably without real Binance data or orders.

Required scope:

- Add a `ws-server` smoke producer/consumer that writes controlled tick/kline/position/balance data through the real websocket protocol and verifies the `B` snapshot format.
- Add a dry-run runner that reads the real `ws-server` snapshot and emits order intent without calling Binance.
- Use a deterministic demo rule for the first runner instead of refactoring `services/trading/simple_trade.py` in place.
- Emit dry-run order intents as structured JSONL on stdout so command-line runs, Docker logs, and tests can inspect the same output.

First acceptance scenario:

- One fake symbol: `BTCUSDT`
- Empty position
- Available balance
- No ban on `BTCUSDT`
- One deterministic 1m decline from fake kline/tick data
- Expected dry-run output: one `open_long` **Order Intent** for `BTCUSDT`

Explicitly out of scope for the first slice:

- Binance production or testnet connectivity.
- Simulated fills, PnL, or paper-trading account state.
- Required database, FastAPI, or frontend dashboard persistence for dry-run intents.
- Refactoring the full `services/trading/simple_trade.py` strategy flow.
- Multi-symbol, short-side, close-position, stop-loss, stop-profit, and insufficient-balance scenarios.

Optional follow-up:

- Persist, query, and display dry-run intents once the deterministic local loop is stable.

## Phase 2B: Binance Testnet Adapter

Goal: validate the external exchange boundary after the deterministic local loop is stable.

Suggested tasks:

- Add explicit Binance Futures testnet configuration that cannot silently point at production.
- Validate market/account/order API behavior against testnet using small controlled scenarios.
- Keep real trading disabled by default even when the testnet adapter is available.

## Phase 3: Strategy runner

Goal: make custom strategies an interface instead of edits inside a large script.

Suggested boundary:

```python
class Strategy:
    def on_market_snapshot(self, ctx) -> list[Signal]:
        ...
```

Suggested tasks:

- Extract market data adapter from `services/trading/simple_trade.py`.
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

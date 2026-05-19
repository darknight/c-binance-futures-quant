# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Binance Futures quantitative trading framework with distributed architecture. Uses the Rust WebSocket aggregation server as the central data hub, with many distributed Python servers for data collection, risk control, and trading. The framework handles data ingestion, risk management, and trade execution — but does not include specific trading strategies.

Production environment: Ubuntu 22.04, Python 3.14+

Package management: uv (pyproject.toml + uv.lock)

## Architecture

```
[Distributed Python Data Collectors] → [WS Aggregation Server] → [Trading Servers]
  (collectors, risk, post-trade)         (ws/ws-server)             (services/trading/simple_trade.py)
                                                                            ↓
                                                                    [Binance Futures API]
```

- **ws/ws-server/** — Rust rewrite of the WebSocket aggregation server (replaces `legacy/wsServer.cpp`). Uses tokio + tokio-tungstenite. HashMap-based storage (no fixed array limits), structured logging (tracing), optional token auth, graceful shutdown. Protocol-compatible with the C++ version — Python clients require zero changes.
- **legacy/wsServer.cpp** — Legacy C++ WebSocket server reference. Compiled with: `g++ legacy/wsServer.cpp -o wsServer.out -lboost_system` (requires websocketpp + boost)
- **infra_client.py** — `InfraClient` class providing PostgreSQL via SQLAlchemy/SQLModel, WebSocket (A/B channels), Telegram notifications, Cloudflare R2 object storage, and Binance order routing
- **settings.py** — pydantic-settings based configuration, reads from `.env` file. Template: `.env.example`
- **binance_f/** — Modified Binance Futures Python SDK (forked from official)
- **web_server/** — FastAPI-based HTTP server providing REST APIs for order management, position queries, trade recording, and machine status. Entry point: `run_web_server.py`
- **legacy/webServer.py** — Legacy Bottle-based HTTP server (deprecated, kept as reference). Replaced by `web_server/`

## Key Modules

| Directory | Purpose |
|-----------|---------|
| `services/collectors/` | Distributed data collectors (tick, kline) that feed into wsServer. Each instance identified by `SERVER_NAME` and `MACHINE_INDEX` env vars |
| `services/risk/` | Critical operations: position monitoring (`getBinancePosition`, `positionRisk`, `wsPosition`), stop-loss (`makerStopLoss`), order timeout (`checkTimeoutOrders`), commission tracking |
| `services/post_trade/` | Post-trade data processing and OSS/R2 upload for frontend display |
| `legacy/react-front/` | **DEPRECATED** — Legacy React 16 frontend. Replaced by `frontend/web-front/`. Kept for reference until new frontend is stable |
| `frontend/web-front/` | React 19 frontend dashboard (Vite, TypeScript, antd 5, Zustand, ECharts). Fetches data from FastAPI backend API |
| `updateSymbol/` | SQL scripts and Python for managing the `trade_symbol` table in PostgreSQL |
| `tool/` | Speed test utilities for Binance API and tick data |
| `ws/ws-server/` | Rust WebSocket aggregation server (tokio + tokio-tungstenite). Replaces `legacy/wsServer.cpp` |
| `web_server/` | FastAPI HTTP server: `app.py` (app factory), `state.py` (shared state), `binance_helpers.py` (Binance API utils), `routers/` (9 route modules incl. `dashboard.py` for frontend KPI/profit APIs) |
| `app/` | Python package: `database.py` (SQLAlchemy engine + session factory), `app/models/` (15 SQLModel models) |
| `alembic/` | Alembic migration environment and versioned migration scripts |
| `tests/` | Test suite: `test_database.py`, `test_models.py` |

## Build & Run Commands

### Rust Aggregation Server (ws/ws-server/)
```bash
cd ws/ws-server

# Development
cargo run -- --port 3698 --log-level debug

# Run tests
cargo test

# Lint
cargo clippy --all-targets
cargo fmt -- --check

# Production build
cargo build --release
nohup ./target/release/ws-server --port 3698 --log-level info >/dev/null &
```

### Legacy C++ Aggregation Server (deprecated)
```bash
g++ legacy/wsServer.cpp -o wsServer.out -lboost_system
nohup ./wsServer.out >/dev/null &
```

### Python Services
```bash
# Install dependencies
uv sync

# Run any Python service locally
PYTHONPATH=. uv run python run_web_server.py
PYTHONPATH=. uv run python services/trading/simple_trade.py

# Each Python file runs as its own service on a separate server/IP
# Remote deployment still uses shebang (#!/usr/bin/env python3):
nohup ./legacy/webServer.py >/dev/null &
```
Legacy deployment used `legacy/uploadDataPy.py` (deprecated) to distribute across Aliyun servers. Current deployment via Dokploy (Docker).

### Local Full-Stack Development (Podman)

Use this flow when Docker is not installed locally. The checked-in `.env.example` matches these defaults; copy it to `.env` if needed. `.env` is local-only and must not be committed.

```bash
# Start local PostgreSQL 18 on localhost:15432
podman run -d \
  --name quant-postgres \
  -e POSTGRES_USER=quant \
  -e POSTGRES_PASSWORD=quant \
  -e POSTGRES_DB=quant \
  -p 15432:5432 \
  postgres:18-alpine

# If the container already exists
podman start quant-postgres

# Apply schema migrations
uv run alembic upgrade head

# Optional: seed deterministic dashboard demo data for frontend development
PYTHONPATH=. uv run python scripts/seed_demo_dashboard_data.py

# Start FastAPI backend on http://localhost:8888
PYTHONPATH=. uv run python run_web_server.py
```

In another terminal:

```bash
cd frontend/web-front
npm install
VITE_API_URL=http://localhost:8888 npm run dev
```

Open `http://127.0.0.1:5173/`. The backend startup calls Binance `exchangeInfo`; local startup requires outbound access to `https://fapi.binance.com`.

### Database (PostgreSQL + SQLModel + Alembic)

Stack: PostgreSQL, SQLAlchemy/SQLModel ORM, Alembic migrations. Configure `DATABASE_URL` in `.env` (local Podman default: `postgresql+psycopg://quant:quant@localhost:15432/quant`).

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new migration from model changes
uv run alembic revision --autogenerate -m "description"

# Run tests
uv run pytest tests/ -v
```

### Legacy React Frontend (legacy/react-front/) — DEPRECATED
```bash
cd legacy/react-front
npm install

# QUANT_CDN_URL is required — set it in .env or pass directly
source ../../.env
QUANT_CDN_URL=$QUANT_CDN_URL npm start          # dev server
QUANT_CDN_URL=$QUANT_CDN_URL npm run build      # production build
```

### New React Frontend (frontend/web-front/)
```bash
cd frontend/web-front
npm install

# VITE_API_URL is required — set it in .env or pass directly
VITE_API_URL=http://localhost:8888 npm run dev    # dev server
VITE_API_URL=http://localhost:8888 npm run build  # production build
```

### Docker (all services)
```bash
# Build all images
docker compose build

# Start infrastructure first
docker compose up -d postgres ws-server

# Run database migrations
docker compose run --rm web-server uv run alembic upgrade head

# Optional: seed deterministic dashboard demo data
docker compose run --rm web-server uv run python scripts/seed_demo_dashboard_data.py

# Start all services
docker compose up -d

# View logs
docker compose logs -f web-server
docker compose logs -f simple-trade

# Stop all
docker compose down

# Stop and remove volumes (destroys database)
docker compose down -v
```

## Design Principles

- Each Python module = one server + one IP, tuned to max Binance API rate limits
- Position/balance data is read via 3 independent methods (positionRisk, account API, WebSocket) and cross-validated by timestamp in wsServer
- Kline data is split into two messages: latest 2 bars (real-time) and full history (periodic sync), to minimize parsing overhead on trading servers
- Risk control in `commission.py`: per-symbol 4h loss > 150u or 24h loss > 1800u triggers trading ban; total 24h loss > 3000u halts all trading
- Stop-loss orders in `makerStopLoss` trigger on >5% position change, split into 5 orders at staggered prices (5%, 5.5%, 6%, 6.5%, 7% from cost)
- Web server uses FastAPI with CORSMiddleware; all endpoints accept form data via `Form()` for backward compatibility with the React frontend

## Important Notes

- `services/trading/simple_trade.py` is a demo only (long when 1min gain >1%, close when 1min drop <-0.5%). Pay attention to `updateSymbolInfo()` for price/quantity precision handling
- The `binance_f/` SDK is a modified fork — not the vanilla Binance SDK
- Data collectors are configured via environment variables (`SERVER_NAME`, `MACHINE_INDEX`, `TICK_INSTANCE_COUNT`) for multi-instance sharding
- WebSocket channels A and B in `InfraClient` connect to the aggregation server at addresses configured in `.env` (`WS_ADDRESS_A`, `WS_ADDRESS_B`)
- Configuration is managed via `.env` file (not committed to git). See `.env.example` for template
- Legacy frontend CDN URL is injected at webpack build time via `QUANT_CDN_URL` env var (→ `CDN_BASE_URL` global). Never hardcode domains in frontend source
- Binance API keys are configured in `.env` as `BINANCE_API_ARR` (JSON array supporting multiple keys for rate limit distribution)
- UI/trading config (`hot_key_config_obj`, `state_config_obj`) is stored in `user_config.json` (runtime-writable, not committed to git)
- The User table has been removed — the project is single-user, no registration/login system
- All database queries use SQLModel ORM via `InfraClient.get_session()` context manager — no raw SQL. Legacy `mysql_*` methods have been removed

## Agent skills

### Issue tracker

Issues and PRDs are tracked in GitHub Issues for `darknight/c-binance-futures-quant`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default mattpocock/skills triage labels unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo: read root `CONTEXT.md` and root `docs/adr/` when they exist. See `docs/agents/domain.md`.

## Rules

- **Acceptance criteria**: Every code change must compile, pass all tests, and run correctly locally before considering it done
- **CLAUDE.md sync**: After every code change, check if CLAUDE.md needs updating. If so, update and commit together
- **Git commits**: Use the current git user directly. Do NOT add `Co-authored-by` or similar trailers. Follow [Conventional Commits](https://www.conventionalcommits.org/) format (e.g., `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
- **Branch strategy**: This is a forked project. `main` branch tracks the original author's code — never push our changes to `main`. All our work goes to `develop` (the default branch). PRs should target `develop`, not `main`
- **No merge commits**: The `develop` branch has GitHub repository rules that forbid merge commits. Always use `git rebase` instead of `git merge` when integrating branches

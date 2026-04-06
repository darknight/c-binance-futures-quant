# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Binance Futures quantitative trading framework with distributed architecture. Uses a C++ WebSocket aggregation server as the central data hub, with many distributed Python servers for data collection, risk control, and trading. The framework handles data ingestion, risk management, and trade execution — but does not include specific trading strategies.

Production environment: Ubuntu 22.04, Python 3.14+

Package management: uv (pyproject.toml + uv.lock)

## Architecture

```
[Distributed Python Data Collectors] → [WS Aggregation Server] → [Trading Servers]
  (tick, kline, position, balance)       (ws-server / wsServer)     (simpleTrade.py)
                                                                            ↓
                                                                    [Binance Futures API]
```

- **ws-server/** — Rust rewrite of the WebSocket aggregation server (replaces wsServer.cpp). Uses tokio + tokio-tungstenite. HashMap-based storage (no fixed array limits), structured logging (tracing), optional token auth, graceful shutdown. Protocol-compatible with the C++ version — Python clients require zero changes.
- **wsServer.cpp** — Legacy C++ WebSocket server (being replaced by ws-server/). Compiled with: `g++ wsServer.cpp -o wsServer.out -lboost_system` (requires websocketpp + boost)
- **infra_client.py** — `InfraClient` class providing PostgreSQL via SQLAlchemy/SQLModel, WebSocket (A/B channels), Telegram notifications, Cloudflare R2 object storage, and Binance order routing
- **settings.py** — pydantic-settings based configuration, reads from `.env` file. Template: `.env.example`
- **binance_f/** — Modified Binance Futures Python SDK (forked from official)
- **web_server/** — FastAPI-based HTTP server providing REST APIs for order management, position queries, trade recording, and machine status. Entry point: `run_web_server.py`
- **webServer.py** — Legacy Bottle-based HTTP server (deprecated, kept as reference). Replaced by `web_server/`

## Key Modules

| Directory | Purpose |
|-----------|---------|
| `dataPy/` | Distributed data collectors (tick, kline) that feed into wsServer. Each instance identified by `SERVER_NAME` and `MACHINE_INDEX` env vars |
| `keyPy/` | Critical operations: position monitoring (`getBinancePosition`, `positionRisk`, `wsPosition`), stop-loss (`makerStopLoss`), order timeout (`checkTimeoutOrders`), commission tracking |
| `afterTrade/` | Post-trade data processing and OSS upload for frontend display |
| `react-front/` | React frontend (webpack, antd, echarts, mobx). Reads data from Cloudflare R2 |
| `updateSymbol/` | SQL scripts and Python for managing the `trade_symbol` table in PostgreSQL |
| `tool/` | Speed test utilities for Binance API and tick data |
| `ws-server/` | Rust WebSocket aggregation server (tokio + tokio-tungstenite). Replaces wsServer.cpp |
| `web_server/` | FastAPI HTTP server: `app.py` (app factory), `state.py` (shared state), `binance_helpers.py` (Binance API utils), `routers/` (8 route modules) |
| `app/` | Python package: `database.py` (SQLAlchemy engine + session factory), `app/models/` (15 SQLModel models) |
| `alembic/` | Alembic migration environment and versioned migration scripts |
| `tests/` | Test suite: `test_database.py`, `test_models.py` |

## Build & Run Commands

### Rust Aggregation Server (ws-server/)
```bash
cd ws-server

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
g++ wsServer.cpp -o wsServer.out -lboost_system
nohup ./wsServer.out >/dev/null &
```

### Python Services
```bash
# Install dependencies
uv sync

# Run any Python service locally
uv run python run_web_server.py

# Each Python file runs as its own service on a separate server/IP
# Remote deployment still uses shebang (#!/usr/bin/env python3):
nohup ./webServer.py >/dev/null &
```
Legacy deployment used `dataPy/uploadDataPy.py` (deprecated) to distribute across Aliyun servers. Current deployment via Dokploy (Docker).

### Database (PostgreSQL + SQLModel + Alembic)

Stack: PostgreSQL, SQLAlchemy/SQLModel ORM, Alembic migrations. Configure `DATABASE_URL` in `.env` (default: `postgresql+psycopg://localhost:5432/quant`).

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Generate a new migration from model changes
uv run alembic revision --autogenerate -m "description"

# Run tests
uv run pytest tests/ -v
```

### React Frontend
```bash
cd react-front
npm install

# QUANT_CDN_URL is required — set it in .env or pass directly
source ../.env
QUANT_CDN_URL=$QUANT_CDN_URL npm start          # dev server
QUANT_CDN_URL=$QUANT_CDN_URL npm run build      # production build
```

### Docker (all services)
```bash
# Build all images
docker compose build

# Start infrastructure first
docker compose up -d postgres ws-server

# Run database migrations
docker compose run --rm web-server uv run alembic upgrade head

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

- `simpleTrade.py` is a demo only (long when 1min gain >1%, close when 1min drop <-0.5%). Pay attention to `updateSymbolInfo()` for price/quantity precision handling
- The `binance_f/` SDK is a modified fork — not the vanilla Binance SDK
- Data collectors are configured via environment variables (`SERVER_NAME`, `MACHINE_INDEX`, `TICK_INSTANCE_COUNT`) for multi-instance sharding
- WebSocket channels A and B in `InfraClient` connect to the aggregation server at addresses configured in `.env` (`WS_ADDRESS_A`, `WS_ADDRESS_B`)
- Configuration is managed via `.env` file (not committed to git). See `.env.example` for template
- Frontend CDN URL is injected at webpack build time via `QUANT_CDN_URL` env var (→ `CDN_BASE_URL` global). Never hardcode domains in frontend source
- Binance API keys are configured in `.env` as `BINANCE_API_ARR` (JSON array supporting multiple keys for rate limit distribution)
- UI/trading config (`hot_key_config_obj`, `state_config_obj`) is stored in `user_config.json` (runtime-writable, not committed to git)
- The User table has been removed — the project is single-user, no registration/login system
- All database queries use SQLModel ORM via `InfraClient.get_session()` context manager — no raw SQL. Legacy `mysql_*` methods have been removed

## Rules

- **Acceptance criteria**: Every code change must compile, pass all tests, and run correctly locally before considering it done
- **CLAUDE.md sync**: After every code change, check if CLAUDE.md needs updating. If so, update and commit together
- **Git commits**: Use the current git user directly. Do NOT add `Co-authored-by` or similar trailers. Follow [Conventional Commits](https://www.conventionalcommits.org/) format (e.g., `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`)
- **No merge commits**: The `develop` and `main` branches have GitHub repository rules that forbid merge commits. Always use `git rebase` instead of `git merge` when integrating branches

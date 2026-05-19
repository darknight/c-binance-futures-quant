# Repository Layout Reorganization Plan

> Status: COMPLETED on 2026-05-19. The scheme B layout was applied, active path references were updated, and local Python, Rust, frontend, and Docker Compose startup verification passed.

## Goal

Reorganize the repository around trading-system responsibilities so the active architecture is easier to understand before Phase 2 dry-run work starts.

The target shape is the conservative version of "Scheme B": move the obvious service, frontend, websocket, and legacy boundaries first, while leaving shared Python foundations in place until the import/package boundary is clearer.

## Why Now

The current root mixes active services, deprecated references, frontend apps, websocket servers, database code, and scripts:

- Active and deprecated HTTP servers are side by side: `web_server/` and `webServer.py`.
- Active and deprecated websocket servers are side by side: `ws-server/` and `wsServer.cpp`.
- Active and deprecated frontends are side by side: `web-front/` and `react-front/`.
- Runtime Python services are split across older names: `dataPy/`, `keyPy/`, `afterTrade/`, and `simpleTrade.py`.

Phase 2 will add dry-run data flow and trading intent. Doing that before the layout cleanup would make the old/new split harder to see.

## Target Layout

```text
/
├── services/
│   ├── collectors/          # market/account data producers, from dataPy/
│   ├── risk/                # account/risk/order maintenance services, from keyPy/
│   ├── post_trade/          # post-trade records and snapshot publishing, from afterTrade/
│   └── trading/             # trading entrypoints, starting with simple_trade.py
├── backend/
│   └── web_server/          # FastAPI control plane, later move if worthwhile
├── frontend/
│   └── web-front/           # active React dashboard
├── ws/
│   └── ws-server/           # active Rust websocket aggregation server
├── legacy/
│   ├── webServer.py         # old Bottle backend reference
│   ├── wsServer.cpp         # old C++ websocket protocol reference
│   ├── react-front/         # old React 16 frontend reference
│   └── uploadDataPy.py      # old SSH/Aliyun deployment reference
├── app/                     # keep for now: SQLModel models and database helpers
├── binance_f/               # keep for now: forked Binance SDK
├── infra_client.py          # keep for now: shared runtime client
├── settings.py              # keep for now: env settings
├── alembic/                 # keep for now: migration environment
├── scripts/
├── tests/
└── docs/
```

## Move Map

| Current path | Target path | Notes |
| ------------ | ----------- | ----- |
| `dataPy/` | `services/collectors/` | Active collector services |
| `keyPy/` | `services/risk/` | Active account/risk services |
| `afterTrade/` | `services/post_trade/` | Active but needs future owner decision around OSS/R2 snapshots |
| `simpleTrade.py` | `services/trading/simple_trade.py` | Demo trading entrypoint; keep behavior unchanged |
| `web-front/` | `frontend/web-front/` | Active dashboard |
| `react-front/` | `legacy/react-front/` | Deprecated reference |
| `ws-server/` | `ws/ws-server/` | Active Rust websocket server |
| `wsServer.cpp` | `legacy/wsServer.cpp` | Deprecated protocol reference |
| `webServer.py` | `legacy/webServer.py` | Deprecated Bottle backend reference |
| `dataPy/uploadDataPy.py` | `legacy/uploadDataPy.py` | Pull out of active collectors because it is deprecated deployment tooling |

## Explicitly Not Moving Yet

These paths stay at the root for this pass:

- `infra_client.py`
- `settings.py`
- `app/`
- `binance_f/`
- `alembic/`
- `alembic.ini`
- `tests/`
- `scripts/`
- `tool/`
- `updateSymbol/`

Reason: moving them now would turn a layout cleanup into a Python packaging migration. That is useful later, but it would increase risk before Phase 2.

## Required Active Path Updates

Update every active runtime reference to the moved paths:

- `docker-compose.yml`
  - `ws-server` build context: `./ws/ws-server`
  - Python service commands under `services/collectors/`, `services/risk/`, `services/post_trade/`, and `services/trading/`
- `Dockerfile`
  - default command if it still points to a moved backend entrypoint
- `README.md`
  - architecture table
  - local commands
  - websocket commands
  - frontend commands
  - Docker Compose examples
- `CLAUDE.md`
  - project overview
  - architecture diagram
  - key module table
  - build/run commands
  - important notes
- `web-front` commands in docs become `cd frontend/web-front`
- Rust commands become `cd ws/ws-server`
- Python trading command becomes `uv run python services/trading/simple_trade.py`

## Backend Move Decision

This first pass should not move `web_server/` into `backend/` unless the implementation pass confirms the import/update cost is small.

Reason: `run_web_server.py`, tests, and imports currently assume `web_server` is an importable top-level package. Moving it physically requires either:

1. updating imports from `web_server...` to `backend.web_server...`, or
2. adding packaging/path compatibility.

Both are real codebase decisions, not just layout cleanup. If moved, move `run_web_server.py` with it and update all imports/tests deliberately. If not moved, document `backend/` as the eventual target and leave the active backend root package alone for now.

## Historical Docs Policy

Do not update old implementation plans under `docs/superpowers/` or completed plan files just to rewrite paths. Those files are historical evidence of previous migrations.

Update only current-facing docs:

- `README.md`
- `CLAUDE.md`
- `docs/roadmap.md`
- `docs/TODO.md`
- `docs/frontend-parity-audit.md` if path references become misleading
- this plan file

## Implementation Steps

1. Create target directories:

   ```text
   services/collectors/
   services/risk/
   services/post_trade/
   services/trading/
   frontend/
   ws/
   legacy/
   ```

2. Move files with `git mv`:

   ```text
   dataPy/ -> services/collectors/
   keyPy/ -> services/risk/
   afterTrade/ -> services/post_trade/
   simpleTrade.py -> services/trading/simple_trade.py
   web-front/ -> frontend/web-front/
   react-front/ -> legacy/react-front/
   ws-server/ -> ws/ws-server/
   wsServer.cpp -> legacy/wsServer.cpp
   webServer.py -> legacy/webServer.py
   services/collectors/uploadDataPy.py -> legacy/uploadDataPy.py
   ```

3. Update active runtime references:

   - `docker-compose.yml`
   - `Dockerfile`
   - `README.md`
   - `CLAUDE.md`
   - current docs that describe active commands

4. Update tests and code references only where needed for moved executable paths.

5. Run verification commands.

6. Commit as one mechanical layout commit if tests pass. DONE

## Verification

Minimum verification:

```bash
uv run pytest tests/ -q
```

Rust websocket verification:

```bash
cd ws/ws-server
cargo test
cargo fmt -- --check
cargo clippy --all-targets
```

Frontend verification:

```bash
cd frontend/web-front
npm run build
```

Docker Compose sanity check:

```bash
docker compose config
```

If local Docker/Podman, Rust, or Node dependencies are unavailable, record the exact command and failure reason rather than claiming full verification.

Completed verification:

- `PYTHONPATH=. uv run pytest tests/ -q`
- `cargo test` in `ws/ws-server`
- `cargo fmt -- --check` in `ws/ws-server`
- `cargo clippy --all-targets` in `ws/ws-server`
- `npm run build` in `frontend/web-front`
- `docker compose config`
- Docker Compose build and startup with an isolated `quant-layout` project, fresh PostgreSQL 18 instance, migrations, demo dashboard seed data, and all configured services `Up`
- Container-internal HTTP checks for `/health` and `/get_dashboard_summary`

## Risks

- Python services are script-style entrypoints. Moving them changes the script paths used by Compose and operators.
- Some imports or relative file assumptions may depend on current working directory rather than file location.
- `frontend/web-front/node_modules/` and `ws/ws-server/target/` are large generated directories. Verify they are ignored and not accidentally staged after moves.
- Legacy files may contain stale references by design. Do not overfit historical docs or deprecated code during this pass.

## Commit Shape

Preferred commit:

```text
refactor: reorganize repository layout by system responsibility
```

If the implementation reveals backend import changes are needed, split into two commits:

1. `refactor: reorganize service and legacy directories`
2. `refactor: move backend package under backend namespace`

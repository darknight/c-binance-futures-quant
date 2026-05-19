# TODO

## Modernization roadmap

Current tracking doc: `docs/roadmap.md`.

The high-level migration is no longer "rewrite everything". The current priority is to keep the modernized infrastructure stable while making the strategy/execution path testable before real trading.

### Cognitive debt cleanup (DONE)

- ~~Document the current main path in `README.md`: `uv`, PostgreSQL, FastAPI, Rust `ws-server`, `frontend/web-front`, Docker/Podman~~
- ~~Replace the Vite template text in `frontend/web-front/README.md`~~
- ~~Keep legacy entry points clearly marked: `legacy/webServer.py`, `legacy/wsServer.cpp`, `legacy/react-front/`, `legacy/uploadDataPy.py`~~
- ~~Reorganize active runtime paths by responsibility: `services/`, `frontend/`, `ws/`, and `legacy/`~~
- ~~Record the next phases in `docs/roadmap.md`~~
- ~~Clarify dashboard router coverage in web server tests~~

### Phase 2A: Deterministic Local Loop (NEXT)

- Add a local smoke producer/consumer for `ws-server` that writes controlled fake data through the real protocol
- Add a dry-run runner with a deterministic demo rule so strategies can emit order intent without calling Binance
- Emit dry-run order intents as structured JSONL on stdout without requiring database/API/frontend persistence
- First acceptance scenario: `BTCUSDT` empty position plus deterministic 1m decline emits one `open_long` order intent

### Phase 2B: Binance Testnet Adapter (FUTURE)

- Add explicit Binance Futures testnet configuration that cannot silently point at production
- Validate external market/account/order API behavior against testnet
- Keep real trading disabled by default even when testnet support exists

### Strategy runner (FUTURE)

- Extract market data adapter, execution adapter, and strategy interface from `services/trading/simple_trade.py`
- Add strategy unit tests for signal generation
- Add paper-trading PnL simulation before any real order path

## Remove unused User/Chat/Visitor system

The project is single-user (self-use only). The multi-user login, chat, and visitor tracking features are unnecessary and should be fully removed.

### Chat + Visitor (DONE — commits 71b0958, a26eb41)

- ~~**Chat table + chat endpoints**: `legacy/webServer.py` `/new_chat`, `/get_chat`, `/get_chat_and_system`, `CHAT_OBJ`, `CHAT_ARR`, `SYSTEM_ARR`~~
- ~~**Visitor table + visitor logging**: visitor IP/page tracking~~
- ~~**SQLModel models**: `app/models/visitor.py`, `app/models/chat.py`~~
- ~~**Tests**: related test cases in `tests/test_models.py`~~
- ~~**Alembic migration**: `e358e791b829_drop_chat_and_visitor_tables.py`~~

### User system (DONE)

- ~~**Registration/login endpoints**: `legacy/webServer.py` `/register`, `/login`~~
- ~~**`binance_f/impl/tradeServer.py`**: abandoned prototype of `legacy/webServer.py`, deleted entirely~~
- ~~**Dynamic income table names**: replaced `accessToken+"_income"` / `accessToken+"_income_day"` with fixed `income` / `income_day` table names, removed CREATE TABLE lazy-loading, cleaned up dead accessToken parameters and commented-out code~~
- ~~**Config migration**: `binance_api_arr` → `.env`, `hot_key_config_obj` / `state_config_obj` → `user_config.json`, `show_symbol_obj` / `server_info_obj` → dropped~~
- ~~**Endpoint cleanup**: deleted `/add_api`, `/delete_api`, `/update_show_symbol_obj`, `/change_quote`; rewrote `/modify_hot_key`, `/get_state_config`, `/modify_state_config`; added `/get_config`~~
- ~~**User table dropped**: deleted `app/models/user.py`, `test_user_create`, Alembic migration `280092e4b641`~~
- ~~**Frontend**: deleted LoginModal, ChatModal, OldChatModal; replaced login with `loadConfig()`; removed accessToken from all requests~~

## Standardize time fields to UTC (DONE — commit 0c0e723)

- ~~Converted 5 fields across 4 models from `str` (VARCHAR) to `datetime` (TIMESTAMPTZ)~~
- ~~Changed `infra_client.py` `turn_ts_to_time()` family to UTC (`gmtime`/`calendar.timegm`)~~
- ~~Removed hardcoded `8*3600` Shanghai timezone offset in `legacy/webServer.py`~~
- ~~Added `UTCEncoder` for JSON serialization of datetime in API responses~~
- ~~Alembic migration `d06ff177ba08`~~

## Replace raw SQL with SQLModel queries (DONE)

- ~~All 100+ raw SQL calls across legacy/webServer.py, services/post_trade/, services/risk/, services/collectors/, updateSymbol/ migrated to SQLModel ORM~~
- ~~Legacy `mysql_select`/`mysql_commit`/`mysql_pool_select`/`mysql_pool_commit` methods removed from InfraClient~~
- ~~Dynamic `position_record_a/b/all` tables consolidated to single `position_record` table~~
- ~~CREATE TABLE lazy-loading removed from all files (Alembic manages schema)~~
- ~~New models created: TradesTake, IncomeHistoryTake, IncomeHistoryTakeDay, CommissionTempIncome, Trades, BeginTradeRecord~~
- ~~125 integration tests covering all ORM query patterns~~

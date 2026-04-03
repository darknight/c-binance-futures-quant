# Raw SQL to SQLModel ORM Migration Plan — COMPLETED 2026-04-03

> **Status:** ✅ All 12 tasks completed. 125 integration tests passing.

**Goal:** Replace all raw SQL (`%s` placeholder style) with SQLModel ORM queries across the entire codebase, remove legacy CREATE TABLE lazy-loading, and consolidate dynamic table names to fixed single tables.

**Architecture:** Test-first migration — for each table group, write integration tests that validate query behavior, then replace raw SQL with ORM queries and verify the same tests pass. Add a SQLModel `Session` helper to `InfraClient`, then migrate file-by-file. Alembic manages all schema changes.

**Tech Stack:** SQLModel, SQLAlchemy, Alembic, PostgreSQL (psycopg)

**Testing Strategy:** Each migration task follows this cycle:
1. Write integration test: seed test data → query with ORM → assert expected results
2. Run test to verify it passes (proves the ORM query is correct)
3. Replace raw SQL in production code with the tested ORM pattern
4. Compile check + run full test suite

---

## File Structure

### Files to modify:
- `infra_client.py` — Replace `mysql_*` methods with SQLModel session-based methods
- `webServer.py` — Migrate 33+ SQL calls to ORM, remove dynamic `position_record_*` table names
- `afterTrade/positionRecord.py` — Migrate 7+ SQL calls, remove CREATE TABLE
- `afterTrade/tradesUpdate.py` — Migrate 8+ SQL calls, remove CREATE TABLE
- `afterTrade/webOssUpdate.py` — Migrate 12+ SQL calls, remove CREATE TABLE
- `keyPy/commission.py` — Migrate 8+ SQL calls, remove CREATE TABLE
- `keyPy/binanceOrdersRecord.py` — Migrate 8+ SQL calls, remove CREATE TABLE
- `keyPy/binanceTradesRecord.py` — Migrate 5+ SQL calls, remove CREATE TABLE
- `updateSymbol/updateTradeSymbol.py` — Migrate 10+ SQL calls
- `dataPy/tickToWs.py`, `dataPy/oneMinKlineToWs.py`, `dataPy/specialOneMinKlineToWs.py` — Simple SELECT migrations

### New model files to create:
- `app/models/trades_take.py` — TradesTake model (currently no SQLModel mapping)
- `app/models/income_history_take.py` — IncomeHistoryTake model (used in afterTrade/, keyPy/)
- `app/models/income_history_take_day.py` — IncomeHistoryTakeDay model (used in afterTrade/)
- `app/models/commission_temp_income.py` — CommissionTempIncome model (used in keyPy/)

### Test files:
- `tests/test_models.py` — Add tests for new models
- `tests/test_queries.py` — **NEW** — Integration tests for all ORM query patterns used in migration

---

## Task 1: Fix InfraClient — Add Session Support + %s Compatibility

**Files:**
- Modify: `infra_client.py:110-125`
- Test: `tests/test_database.py`

The current `mysql_select`/`mysql_commit` use `text()` which breaks with `%s` placeholders. Fix with `exec_driver_sql` as transitional bridge, and add `get_session()` for ORM code.

- [x] **Step 1: Fix mysql_select/mysql_commit to use exec_driver_sql**

In `infra_client.py`, replace lines 110-125:

```python
def mysql_select(self, sql, params):
    with self._engine.connect() as conn:
        result = conn.exec_driver_sql(sql, tuple(params) if params else ())
        return result.fetchall()

def mysql_commit(self, sql, params):
    with self._engine.connect() as conn:
        conn.exec_driver_sql(sql, tuple(params) if params else ())
        conn.commit()

def mysql_pool_select(self, q, params):
    return self.mysql_select(q, params)

def mysql_pool_commit(self, q, params):
    self.mysql_commit(q, params)
    return True

def get_session(self):
    from sqlmodel import Session
    return Session(self._engine)
```

- [x] **Step 2: Run all tests**

Run: `uv run pytest tests/ -v`

- [x] **Step 3: Compile check**

Run: `python3 -m py_compile webServer.py && python3 -m py_compile infra_client.py`

- [x] **Step 4: Commit**

```bash
git add infra_client.py
git commit -m "fix: make mysql_* methods compatible with %s placeholders, add get_session()"
```

---

## Task 2: Create Missing SQLModel Models

**Files:**
- Create: `app/models/trades_take.py`
- Create: `app/models/income_history_take.py`
- Create: `app/models/income_history_take_day.py`
- Create: `app/models/commission_temp_income.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_models.py`

Read CREATE TABLE statements from existing code to derive schemas:
- `afterTrade/tradesUpdate.py:32-55` — trades_take
- `afterTrade/webOssUpdate.py:32-42` — income_history_take_day
- `keyPy/commission.py:55-74` — commission_temp_income
- `afterTrade/positionRecord.py` + `keyPy/commission.py` — income_history_take (referenced but CREATE TABLE may be elsewhere)

Also verify existing models match CREATE TABLE schemas:
- `keyPy/binanceOrdersRecord.py:46-72` vs Order model
- `keyPy/binanceTradesRecord.py:46-65` vs Trade model

- [x] **Step 1: Read all CREATE TABLE definitions from source files**
- [x] **Step 2: Create each model file with SQLModel field types matching the CREATE TABLE columns**

Example structure for each model:
```python
from datetime import datetime
from decimal import Decimal
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import BigInteger, DateTime, Numeric, String

class TradesTake(SQLModel, table=True):
    __tablename__ = "trades_take"
    id: int | None = Field(default=None, primary_key=True)
    # ... fields derived from CREATE TABLE
```

- [x] **Step 3: Update `app/models/__init__.py` with new imports**
- [x] **Step 4: Write `test_*_create` tests for each new model in `tests/test_models.py`**
- [x] **Step 5: Run tests**

Run: `uv run pytest tests/ -v`

- [x] **Step 6: Generate and apply Alembic migration**

```bash
uv run alembic revision --autogenerate -m "add trades_take, income_history_take, income_history_take_day, commission_temp_income tables"
uv run alembic upgrade head
```

- [x] **Step 7: Commit**

```bash
git add app/models/ tests/test_models.py alembic/versions/
git commit -m "feat: add missing SQLModel models for trades_take, income_history_take, income_history_take_day, commission_temp_income"
```

---

## Task 3: Consolidate Dynamic position_record Tables

**Files:**
- Modify: `webServer.py` — Replace `position_record_a/b/all/d/e` + `history_position_record_*` with fixed `position_record`

The `POSITION_RECORD_TABLE_NAME_OBJ` maps symbols to separate tables (legacy multi-account design). Consolidate to single `position_record` table — model already has `symbol` column for filtering.

- [x] **Step 1: Remove `POSITION_RECORD_TABLE_NAME_OBJ` dict**
- [x] **Step 2: Replace all dynamic table name references with fixed `position_record`**

Add `AND symbol=%s` WHERE conditions where the old code selected from a per-symbol table.

- [x] **Step 3: Compile check**

Run: `python3 -m py_compile webServer.py`

- [x] **Step 4: Commit**

```bash
git add webServer.py
git commit -m "refactor: consolidate dynamic position_record tables to single table"
```

---

## Task 4: Remove All CREATE TABLE Lazy-Loading

**Files:**
- Modify: `webServer.py:59-115`
- Modify: `afterTrade/positionRecord.py:19-45`
- Modify: `afterTrade/tradesUpdate.py:24-55`
- Modify: `afterTrade/webOssUpdate.py:25-42`
- Modify: `keyPy/commission.py:47-74`
- Modify: `keyPy/binanceOrdersRecord.py:38-72`
- Modify: `keyPy/binanceTradesRecord.py:38-65`

Remove all `SHOW TABLES` + `CREATE TABLE` blocks. Alembic now manages all schema.

- [x] **Step 1: Remove CREATE TABLE blocks from all 7 files**
- [x] **Step 2: Compile check all files**
- [x] **Step 3: Commit**

```bash
git add webServer.py afterTrade/ keyPy/
git commit -m "refactor: remove CREATE TABLE lazy-loading, Alembic manages all schema"
```

---

## Task 5: Write Query Integration Tests + Migrate webServer.py — trade_server_status

**Files:**
- Create: `tests/test_queries.py`
- Modify: `webServer.py` — ~8 SQL calls for trade_server_status
- Model: `TradeServerStatus` (exists)

- [x] **Step 1: Create `tests/test_queries.py` with session fixture and trade_server_status tests**

```python
from datetime import datetime, timezone
from decimal import Decimal
from sqlmodel import SQLModel, Session, create_engine, select
import pytest

from app.models.trade_server_status import TradeServerStatus

@pytest.fixture
def session():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

# Test: query all trade server statuses (used in updateTradeServerStatusData)
def test_select_all_trade_server_status(session):
    ts1 = TradeServerStatus(private_ip="10.0.0.1", name="server_1", symbol="BTCUSDT",
                            extra_para='{"customizeDangerous":{}}', run_info='{}', update_ts=1000)
    ts2 = TradeServerStatus(private_ip="10.0.0.2", name="server_2", symbol="ETHUSDT",
                            extra_para='{"customizeDangerous":{}}', run_info='{}', update_ts=2000)
    session.add(ts1)
    session.add(ts2)
    session.commit()
    results = session.exec(select(TradeServerStatus)).all()
    assert len(results) == 2

# Test: find by private_ip (used in check_maker_server_in_data)
def test_find_trade_server_by_ip(session):
    ts = TradeServerStatus(private_ip="10.0.0.1", name="server_1", symbol="BTCUSDT")
    session.add(ts)
    session.commit()
    result = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.1")
    ).first()
    assert result is not None
    assert result.symbol == "BTCUSDT"

# Test: find by ip returns None when not exists
def test_find_trade_server_by_ip_not_found(session):
    result = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.private_ip == "10.0.0.99")
    ).first()
    assert result is None

# Test: update trade server status (used in update_maker_server_run_info)
def test_update_trade_server_status(session):
    ts = TradeServerStatus(private_ip="10.0.0.1", name="server_1", symbol="BTCUSDT",
                           update_ts=1000)
    session.add(ts)
    session.commit()
    ts.update_ts = 2000
    ts.run_info = '{"direction":"long"}'
    ts.update_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    session.add(ts)
    session.commit()
    session.refresh(ts)
    assert ts.update_ts == 2000
    assert ts.run_info == '{"direction":"long"}'

# Test: update extra_para for all rows (used in update_customize_dangerous)
def test_update_all_extra_para(session):
    ts1 = TradeServerStatus(private_ip="10.0.0.1", symbol="BTCUSDT", extra_para='{}')
    ts2 = TradeServerStatus(private_ip="10.0.0.2", symbol="ETHUSDT", extra_para='{}')
    session.add(ts1)
    session.add(ts2)
    session.commit()
    all_ts = session.exec(select(TradeServerStatus)).all()
    for t in all_ts:
        t.extra_para = '{"customizeDangerous":{"maxLoss":100}}'
        session.add(t)
    session.commit()
    results = session.exec(select(TradeServerStatus)).all()
    assert all(r.extra_para == '{"customizeDangerous":{"maxLoss":100}}' for r in results)

# Test: update extra_para by symbol (used in update_customize_dangerous)
def test_update_extra_para_by_symbol(session):
    ts1 = TradeServerStatus(private_ip="10.0.0.1", symbol="BTCUSDT", extra_para='{}')
    ts2 = TradeServerStatus(private_ip="10.0.0.2", symbol="ETHUSDT", extra_para='{}')
    session.add(ts1)
    session.add(ts2)
    session.commit()
    target = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.symbol == "BTCUSDT")
    ).first()
    target.extra_para = '{"customizeDangerous":{"maxLoss":200}}'
    session.add(target)
    session.commit()
    unchanged = session.exec(
        select(TradeServerStatus).where(TradeServerStatus.symbol == "ETHUSDT")
    ).first()
    assert unchanged.extra_para == '{}'
```

- [x] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_queries.py -v`

- [x] **Step 3: Replace raw SQL in webServer.py with ORM equivalents matching the tested patterns**

For each function (`updateTradeServerStatusData`, `check_maker_server_in_data`, `update_maker_server_run_info`, `update_customize_dangerous`), replace `FUNCTION_CLIENT.mysql_pool_select/commit` calls with `FUNCTION_CLIENT.get_session()` + SQLModel queries.

- [x] **Step 4: Compile check + run full test suite**

Run: `python3 -m py_compile webServer.py && uv run pytest tests/ -v`

- [x] **Step 5: Commit**

```bash
git add tests/test_queries.py webServer.py
git commit -m "refactor: migrate trade_server_status queries to SQLModel ORM with tests"
```

---

## Task 6: Test + Migrate webServer.py — machine_status + trade_machine_status

**Files:**
- Modify: `tests/test_queries.py` — Add machine_status query tests
- Modify: `webServer.py` — ~10 SQL calls
- Models: `MachineStatus`, `TradeMachineStatus` (exist)

- [x] **Step 1: Add integration tests for machine_status queries to `tests/test_queries.py`**

Test patterns:
- SELECT by private_ip (find existing machine)
- INSERT new machine status
- UPDATE status and update_ts by private_ip
- SELECT all trade_machine_status ordered by update_ts desc

- [x] **Step 2: Run tests to verify they pass**
- [x] **Step 3: Replace raw SQL in webServer.py (`update_machine_status`, `update_trade_machine_status`, `get_trade_machine_status_data`)**
- [x] **Step 4: Compile check + run full test suite**
- [x] **Step 5: Commit**

```bash
git add tests/test_queries.py webServer.py
git commit -m "refactor: migrate machine_status queries to SQLModel ORM with tests"
```

---

## Task 7: Test + Migrate webServer.py — income + income_day

**Files:**
- Modify: `tests/test_queries.py` — Add income/income_day query tests
- Modify: `webServer.py` — ~14 SQL calls
- Models: `Income`, `IncomeDay` (exist)

- [x] **Step 1: Add integration tests to `tests/test_queries.py`**

Test patterns:
- SELECT income WHERE binance_ts > threshold ORDER BY id DESC
- SELECT income WHERE apiKey = X ORDER BY id DESC LIMIT 100
- INSERT income record
- SELECT income_day ORDER BY id DESC LIMIT 1 (get latest)
- SELECT income_day ORDER BY id ASC (get all)
- INSERT income_day record
- UPDATE income_day SET commission, pnl WHERE day_end_time = X
- SELECT income WHERE binance_ts between range (for day aggregation)

- [x] **Step 2: Run tests to verify they pass**
- [x] **Step 3: Replace raw SQL in webServer.py (`getIncomeObj`, `/r` endpoint, `updateDayIncome`, `get_day_income`)**
- [x] **Step 4: Compile check + run full test suite**
- [x] **Step 5: Commit**

```bash
git add tests/test_queries.py webServer.py
git commit -m "refactor: migrate income/income_day queries to SQLModel ORM with tests"
```

---

## Task 8: Test + Migrate webServer.py — loss_limit_time + position_record + trades_take + remaining

**Files:**
- Modify: `tests/test_queries.py` — Add remaining query tests
- Modify: `webServer.py` — remaining ~15 SQL calls
- Models: `LossLimitTime`, `PositionRecord`, `TradesTake`

- [x] **Step 1: Add integration tests to `tests/test_queries.py`**

Test patterns:
- SELECT all loss_limit_time
- INSERT / UPDATE loss_limit_time by symbol
- SELECT position_record WHERE ts between range AND symbol = X
- SELECT position_record ORDER BY id DESC LIMIT 1
- SELECT trades_take WHERE symbol AND status = 'tradeBegin'
- INSERT trades_take
- SELECT trades_record WHERE profitPercentByBalance <= -0.15

- [x] **Step 2: Run tests to verify they pass**
- [x] **Step 3: Replace raw SQL in webServer.py**
- [x] **Step 4: Compile check + run full test suite**
- [x] **Step 5: Commit**

```bash
git add tests/test_queries.py webServer.py
git commit -m "refactor: migrate remaining webServer.py queries to SQLModel ORM with tests"
```

---

## Task 9: Test + Migrate afterTrade/ Files

**Files:**
- Modify: `tests/test_queries.py` — Add afterTrade query tests
- Modify: `afterTrade/positionRecord.py` — 7+ SQL calls
- Modify: `afterTrade/tradesUpdate.py` — 8+ SQL calls
- Modify: `afterTrade/webOssUpdate.py` — 12+ SQL calls

- [x] **Step 1: Add integration tests for key query patterns used in afterTrade/**

Test patterns:
- PositionRecord: INSERT batch, SELECT WHERE ts < X AND update_profit_and_commission = false, UPDATE profit/commission by id
- TradesTake: SELECT WHERE status, UPDATE value/amount/profit, complex status transitions
- IncomeHistoryTake: SELECT by binance_ts range, SELECT latest
- IncomeHistoryTakeDay: SELECT latest, INSERT, UPDATE by day_end_time

- [x] **Step 2: Run tests**
- [x] **Step 3: Migrate positionRecord.py**
- [x] **Step 4: Migrate tradesUpdate.py**
- [x] **Step 5: Migrate webOssUpdate.py**
- [x] **Step 6: Compile check all three + run full test suite**
- [x] **Step 7: Commit**

```bash
git add tests/test_queries.py afterTrade/
git commit -m "refactor: migrate afterTrade/ queries to SQLModel ORM with tests"
```

---

## Task 10: Test + Migrate keyPy/ + dataPy/ + updateSymbol/ Files

**Files:**
- Modify: `tests/test_queries.py` — Add keyPy query tests
- Modify: `keyPy/commission.py` — 8+ SQL calls
- Modify: `keyPy/binanceOrdersRecord.py` — 8+ SQL calls
- Modify: `keyPy/binanceTradesRecord.py` — 5+ SQL calls
- Modify: `updateSymbol/updateTradeSymbol.py` — 10+ SQL calls
- Modify: `dataPy/tickToWs.py`, `dataPy/oneMinKlineToWs.py`, `dataPy/specialOneMinKlineToWs.py`

- [x] **Step 1: Add integration tests for key query patterns**

Test patterns:
- Order: SELECT by symbol, INSERT with all fields, UPDATE all fields by id
- Trade: SELECT by symbol, INSERT
- Commission: DELETE WHERE binance_ts < X, SELECT all, INSERT batch
- TradeSymbol: SELECT WHERE status='yes', UPDATE index/defaultShow/linkSymbolArr by id, TRUNCATE equivalent

- [x] **Step 2: Run tests**
- [x] **Step 3: Migrate each file**
- [x] **Step 4: Compile check + run full test suite**
- [x] **Step 5: Commit**

```bash
git add tests/test_queries.py keyPy/ updateSymbol/ dataPy/
git commit -m "refactor: migrate keyPy/dataPy/updateSymbol queries to SQLModel ORM with tests"
```

---

## Task 11: Remove Legacy mysql_* Methods + MySQL Pool

**Files:**
- Modify: `infra_client.py` — Remove `mysql_select`, `mysql_commit`, `mysql_pool_select`, `mysql_pool_commit`
- Modify: `webServer.py` — Remove `pool = MySQLConnectionPool(...)`, `import mysql.connector`

- [x] **Step 1: Grep to verify no remaining callers**

```bash
grep -rn "mysql_pool_select\|mysql_pool_commit\|mysql_select\|mysql_commit\|pool\.get_connection" --include="*.py" .
```

- [x] **Step 2: Remove legacy methods from infra_client.py**
- [x] **Step 3: Remove MySQL pool setup + mysql.connector import from webServer.py**
- [x] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`

- [x] **Step 5: Commit**

```bash
git add infra_client.py webServer.py
git commit -m "refactor: remove legacy mysql_* methods and MySQL connection pool"
```

---

## Task 12: Final Verification + Update Docs

- [x] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```

- [x] **Step 2: Grep for any remaining raw SQL patterns**

```bash
grep -rn "exec_driver_sql\|mysql_pool\|mysql_select\|mysql_commit\|SHOW TABLES\|CREATE TABLE" --include="*.py" .
```

- [x] **Step 3: Update docs/TODO.md — mark "Replace raw SQL" as DONE**
- [x] **Step 4: Update CLAUDE.md — note SQLModel ORM is now the standard DB access pattern**
- [x] **Step 5: Final commit**

```bash
git add docs/TODO.md CLAUDE.md
git commit -m "docs: mark raw SQL to SQLModel migration as complete"
```

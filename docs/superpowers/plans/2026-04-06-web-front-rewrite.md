# Web Frontend Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the legacy `react-front/` dashboard as `web-front/` using modern tech, with data sourced from FastAPI backend API instead of R2 CDN.

**Architecture:** Two-phase build. Phase A adds 2 new dashboard endpoints to the FastAPI backend (`/get_dashboard_summary`, `/get_profit_by_symbol`). Phase B builds the `web-front/` SPA that calls these endpoints plus 3 existing ones. Frontend uses multi-frequency polling (10s for KPI, 5min for heavy aggregations).

**Tech Stack:** Python/FastAPI/SQLModel (backend), Vite/React 19/TypeScript/antd 5/Zustand/ECharts (frontend)

**Reference files:**
- `afterTrade/webOssUpdate.py` lines 58-161 — `getProfit()` logic to replicate
- `react-front/src/work/constainers/Show.js` — original 839-line component
- `web_server/routers/` — existing endpoint patterns
- `web_server/state.py` — `AppState` dataclass for caching

**User notes:**
- After all changes, update `CLAUDE.md` (add `web-front/`, mark `react-front/` as deprecated)
- Do NOT delete `react-front/` — mark deprecated only

---

## File Structure

### Backend (Phase A)

```
web_server/
  routers/
    dashboard.py              # NEW: /get_dashboard_summary + /get_profit_by_symbol
  state.py                    # MODIFY: add dashboard cache fields
  app.py                      # MODIFY: register dashboard router
tests/
  test_dashboard.py           # NEW: tests for dashboard endpoints
```

### Frontend (Phase B)

```
web-front/
  public/
  src/
    main.tsx                    # ReactDOM.createRoot entry
    App.tsx                     # ConfigProvider + usePolling + layout
    vite-env.d.ts               # ImportMetaEnv with VITE_API_URL
    types/
      index.ts                  # All TS interfaces
    api/
      dashboard.ts              # 5 POST request functions
    stores/
      useThemeStore.ts          # Dark/light + localStorage
      useDashboardStore.ts      # KPI data from /get_dashboard_summary
      useProfitStore.ts         # History profit table from /get_profit_by_symbol
      useDayIncomeStore.ts      # Day income chart data
      useChartStore.ts          # Balance/position trend data
    hooks/
      usePolling.ts             # Multi-frequency polling lifecycle
    utils/
      format.ts                 # Timestamp + number formatting
    components/
      ThemeToggle.tsx           # Sun/moon switch
      KpiCards.tsx              # 5 KPI stat cards
      BalanceChart.tsx          # Balance trend line chart + range selector
      PositionValueChart.tsx    # Position value trend line chart
      DayIncomeChart.tsx        # Day income bar/line toggle chart
      BigLossTable.tsx          # Big loss trades table
      HistoryTable.tsx          # History data table (13 cols, sortable)
    styles/
      global.css                # Minimal global styles
  .env.example                  # VITE_API_URL=
  index.html
  vite.config.ts
  tsconfig.json
  tsconfig.app.json
```

---

## Phase A: Backend Dashboard Endpoints

### Task 1: Add Dashboard Cache Fields to AppState

**Goal:** Add cache fields for the two new dashboard endpoints.

**Files:**
- Modify: `web_server/state.py`

- [ ] **Step 1: Add profit_by_symbol and dashboard_summary cache fields**

In `web_server/state.py`, add these fields to the `AppState` dataclass, after the existing `big_loss_trades` cache fields (around line 121):

```python
    # Dashboard summary cache
    dashboard_summary_data: dict = field(default_factory=dict)
    dashboard_summary_update_ts: int = 0

    # Profit by symbol cache
    profit_by_symbol_data: dict = field(default_factory=dict)
    profit_by_symbol_update_ts: int = 0
    profit_by_symbol_today_ts: int = 0
```

- [ ] **Step 2: Verify no syntax errors**

Run: `uv run python -c "from web_server.state import AppState; s = AppState(); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add web_server/state.py
git commit -m "feat(web-server): add dashboard cache fields to AppState"
```

---

### Task 2: Create Dashboard Router — /get_dashboard_summary

**Goal:** New endpoint aggregating KPI data for the frontend dashboard.

**Files:**
- Create: `web_server/routers/dashboard.py`
- Modify: `web_server/app.py`

- [ ] **Step 1: Create the dashboard router**

Create `web_server/routers/dashboard.py`:

```python
import json
import time

from fastapi import APIRouter, Request
from sqlalchemy import func
from sqlmodel import select

from app.models.income_history_take import IncomeHistoryTake
from app.models.machine_status import TradeMachineStatus
from app.models.position_record import PositionRecord
from web_server.binance_helpers import json_dumps

router = APIRouter()


@router.post("/get_dashboard_summary")
def get_dashboard_summary(request: Request):
    state = request.app.state.app_state
    now = int(time.time())

    if now - state.dashboard_summary_update_ts < 10 and state.dashboard_summary_data:
        return state.dashboard_summary_data

    # Balance + position value from latest PositionRecord per symbol
    all_balance = 0
    all_position = 0
    with state.infra_client.get_session() as session:
        subq = select(func.max(PositionRecord.id)).group_by(PositionRecord.symbol).scalar_subquery()
        position_record_data = session.exec(
            select(PositionRecord).where(PositionRecord.id.in_(subq))
        ).all()
    for row in position_record_data:
        all_position += (row.position_value or 0)
        all_balance += (row.balance or 0)

    # Today's profit/commission from income_obj (populated by /get_income_obj)
    today_profit = state.income_obj.get("today", {}).get("p", 0)
    today_commission = state.income_obj.get("today", {}).get("c", 0)
    today_vol = today_commission  # oneDayVol in old frontend = today's commission

    # System status from TradeMachineStatus
    system_status = ""
    system_update_ts = 0
    run_time = 0
    if now - state.update_trade_machine_status_data_ts > 60:
        state.update_trade_machine_status_data_ts = now
        with state.infra_client.get_session() as session:
            state.trade_machine_status_data = session.exec(
                select(TradeMachineStatus).order_by(TradeMachineStatus.update_ts.asc())
            ).all()
        all_run_time = 0
        for item in state.trade_machine_status_data:
            all_run_time += (item.run_time or 0)
        if len(state.trade_machine_status_data) > 0:
            state.average_run_time = int(all_run_time / len(state.trade_machine_status_data))

    if len(state.trade_machine_status_data) > 0:
        system_update_ts = state.trade_machine_status_data[0].update_ts
        system_status = state.trade_machine_status_data[0].status
        run_time = state.average_run_time

    state.dashboard_summary_data = {
        "s": "ok",
        "balance": all_balance,
        "positionValue": all_position,
        "oneDayVol": today_vol,
        "oneDayProfit": today_profit,
        "systemStatus": system_status,
        "systemUpdateTs": system_update_ts,
        "runTime": run_time,
        "t": now,
    }
    state.dashboard_summary_update_ts = now

    return json.loads(json_dumps(state.dashboard_summary_data))
```

- [ ] **Step 2: Register dashboard router in app.py**

In `web_server/app.py`, add the import and include:

Add to imports (line 10):
```python
from web_server.routers import config, market, orders, trading, income, records, status, account, dashboard
```

Add after `app.include_router(account.router)` (line 47):
```python
    app.include_router(dashboard.router)
```

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "from web_server.routers.dashboard import router; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/dashboard.py web_server/app.py
git commit -m "feat(web-server): add /get_dashboard_summary endpoint"
```

---

### Task 3: Add /get_profit_by_symbol Endpoint

**Goal:** Replicate `webOssUpdate.py` `getProfit()` logic as a cached API endpoint.

**Files:**
- Modify: `web_server/routers/dashboard.py`

- [ ] **Step 1: Add the profit_by_symbol endpoint**

Append to `web_server/routers/dashboard.py`:

```python
@router.post("/get_profit_by_symbol")
def get_profit_by_symbol(request: Request):
    state = request.app.state.app_state
    now = int(time.time())

    # Calculate today's midnight timestamp (UTC) in milliseconds
    today_ts = (now - now % 86400) * 1000

    # Return cache if within 5min TTL and same day
    if (
        now - state.profit_by_symbol_update_ts < 300
        and state.profit_by_symbol_today_ts == today_ts
        and state.profit_by_symbol_data
    ):
        return state.profit_by_symbol_data

    with state.infra_client.get_session() as session:
        income_rows = session.exec(
            select(IncomeHistoryTake).where(IncomeHistoryTake.binance_ts < today_ts)
        ).all()

    p = {}  # profit by symbol
    c = {}  # commission by symbol
    v = {}  # BNB volume by symbol

    one_day_ago = today_ts - 86400 * 1000
    seven_days_ago = today_ts - 7 * 86400 * 1000
    thirty_days_ago = today_ts - 30 * 86400 * 1000

    for row in income_rows:
        income = float(row.income) if row.income is not None else 0
        binance_ts = row.binance_ts
        income_type = row.income_type
        bnb_price = float(row.bnb_price) if row.bnb_price is not None else 0
        asset = row.asset
        symbol = row.symbol

        if not symbol:
            continue

        if symbol not in p:
            p[symbol] = [0, 0, 0, 0]
        if symbol not in c:
            c[symbol] = [0, 0, 0, 0]
        if symbol not in v:
            v[symbol] = [0, 0, 0, 0]

        real_income = income * bnb_price if asset == "BNB" else income

        if income_type == "COMMISSION":
            commission_value = real_income * 0.6
            # Commission contributes to both c[] and p[]
            if binance_ts >= one_day_ago:
                c[symbol][0] += commission_value
                p[symbol][0] += commission_value
                if asset == "BNB":
                    v[symbol][0] += income * 0.6
            if binance_ts >= seven_days_ago:
                c[symbol][1] += commission_value
                p[symbol][1] += commission_value
                if asset == "BNB":
                    v[symbol][1] += income * 0.6
            if binance_ts >= thirty_days_ago:
                c[symbol][2] += commission_value
                p[symbol][2] += commission_value
                if asset == "BNB":
                    v[symbol][2] += income * 0.6
            c[symbol][3] += commission_value
            p[symbol][3] += commission_value
            if asset == "BNB":
                v[symbol][3] += income * 0.6

        elif income_type in ("REALIZED_PNL", "FUNDING_FEE"):
            if binance_ts >= one_day_ago:
                p[symbol][0] += real_income
            if binance_ts >= seven_days_ago:
                p[symbol][1] += real_income
            if binance_ts >= thirty_days_ago:
                p[symbol][2] += real_income
            p[symbol][3] += real_income

    # Aggregate "all" row
    for d in (p, c, v):
        d["all"] = [0, 0, 0, 0]
        for key in d:
            if key != "all":
                for i in range(4):
                    d["all"][i] += d[key][i]

    state.profit_by_symbol_data = {"s": "ok", "p": p, "c": c, "v": v, "t": today_ts}
    state.profit_by_symbol_update_ts = now
    state.profit_by_symbol_today_ts = today_ts

    return state.profit_by_symbol_data
```

- [ ] **Step 2: Verify import works**

Run: `uv run python -c "from web_server.routers.dashboard import router; print(len(router.routes), 'routes'); print('OK')"`
Expected: `2 routes` and `OK`

- [ ] **Step 3: Commit**

```bash
git add web_server/routers/dashboard.py
git commit -m "feat(web-server): add /get_profit_by_symbol endpoint"
```

---

### Task 4: Backend Tests

**Goal:** Test the two new dashboard endpoints with in-memory SQLite.

**Files:**
- Create: `tests/test_dashboard.py`

- [ ] **Step 1: Write tests**

Create `tests/test_dashboard.py`:

```python
import time
from decimal import Decimal
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from app.models.income_history_take import IncomeHistoryTake
from app.models.machine_status import TradeMachineStatus
from app.models.position_record import PositionRecord
from web_server.state import AppState


def _make_app_with_state(state: AppState):
    """Create a minimal FastAPI app with the given AppState for testing."""
    from fastapi import FastAPI
    from web_server.routers import dashboard

    app = FastAPI()
    app.include_router(dashboard.router)
    app.state.app_state = state
    return app


def _seed_income_data(session: Session):
    """Seed IncomeHistoryTake rows for testing profit aggregation."""
    now_ms = int(time.time() * 1000)
    yesterday_ms = now_ms - 2 * 86400 * 1000  # 2 days ago (before today)

    session.add(IncomeHistoryTake(
        income_type="REALIZED_PNL", income=Decimal("100.0"),
        bnb_price=Decimal("600.0"), asset="USDT", symbol="BTCUSDT",
        binance_ts=yesterday_ms, trade_id="1", api_key="test",
    ))
    session.add(IncomeHistoryTake(
        income_type="COMMISSION", income=Decimal("-0.5"),
        bnb_price=Decimal("600.0"), asset="BNB", symbol="BTCUSDT",
        binance_ts=yesterday_ms, trade_id="2", api_key="test",
    ))
    session.add(IncomeHistoryTake(
        income_type="FUNDING_FEE", income=Decimal("5.0"),
        bnb_price=Decimal("600.0"), asset="USDT", symbol="ETHUSDT",
        binance_ts=yesterday_ms, trade_id="3", api_key="test",
    ))
    session.commit()


def _seed_position_records(session: Session):
    """Seed PositionRecord rows for balance/position value testing."""
    now_ts = int(time.time())
    session.add(PositionRecord(
        symbol="BTCUSDT", position_amt=0.5, position_value=15000,
        balance=20000, time=str(now_ts), ts=now_ts,
        profit=Decimal("100"), commission=Decimal("10"),
        maker_commission=Decimal("5"), unrealized_profit=Decimal("50"),
    ))
    session.add(PositionRecord(
        symbol="ETHUSDT", position_amt=5, position_value=8000,
        balance=20000, time=str(now_ts), ts=now_ts,
        profit=Decimal("50"), commission=Decimal("5"),
        maker_commission=Decimal("2"), unrealized_profit=Decimal("20"),
    ))
    session.commit()


def _create_test_state() -> AppState:
    """Create an AppState with in-memory SQLite and mock infra_client."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    state = AppState()
    infra = MagicMock()
    infra.get_session.return_value.__enter__ = lambda self: Session(engine)
    infra.get_session.return_value.__exit__ = lambda self, *args: None

    # Make get_session a proper context manager
    from contextlib import contextmanager

    @contextmanager
    def mock_get_session():
        with Session(engine) as session:
            yield session

    infra.get_session = mock_get_session
    state.infra_client = infra

    # Seed data
    with Session(engine) as session:
        _seed_position_records(session)
        _seed_income_data(session)

    return state


def test_get_dashboard_summary():
    state = _create_test_state()
    # Pre-populate income_obj as if /get_income_obj already ran
    state.income_obj = {
        "today": {"c": -50.0, "p": 200.0, "s": 10.0},
        "15m": {"c": 0, "p": 0, "s": 0},
        "30m": {"c": 0, "p": 0, "s": 0},
        "1h": {"c": 0, "p": 0, "s": 0},
        "4h": {"c": 0, "p": 0, "s": 0},
        "oneDay": {"c": 0, "p": 0, "s": 0},
    }

    app = _make_app_with_state(state)
    client = TestClient(app)
    resp = client.post("/get_dashboard_summary")
    data = resp.json()

    assert data["s"] == "ok"
    assert data["balance"] == 40000  # 20000 + 20000
    assert data["positionValue"] == 23000  # 15000 + 8000
    assert data["oneDayProfit"] == 200.0
    assert data["oneDayVol"] == -50.0


def test_get_profit_by_symbol():
    state = _create_test_state()

    app = _make_app_with_state(state)
    client = TestClient(app)
    resp = client.post("/get_profit_by_symbol")
    data = resp.json()

    assert data["s"] == "ok"
    assert "BTCUSDT" in data["p"]
    assert "ETHUSDT" in data["p"]
    assert "all" in data["p"]

    # BTCUSDT: REALIZED_PNL 100 + COMMISSION (-0.5 * 600 * 0.6) = 100 + (-180) = -80
    btc_profit_all = data["p"]["BTCUSDT"][3]
    assert abs(btc_profit_all - (100 + (-0.5 * 600 * 0.6))) < 0.01

    # ETHUSDT: FUNDING_FEE 5.0
    eth_profit_all = data["p"]["ETHUSDT"][3]
    assert abs(eth_profit_all - 5.0) < 0.01

    # BNB volume: only BTCUSDT has BNB commission
    assert "BTCUSDT" in data["v"]
    btc_vol_all = data["v"]["BTCUSDT"][3]
    assert abs(btc_vol_all - (-0.5 * 0.6)) < 0.01


def test_get_profit_by_symbol_cache():
    """Second call within 5min should return cached data."""
    state = _create_test_state()

    app = _make_app_with_state(state)
    client = TestClient(app)

    resp1 = client.post("/get_profit_by_symbol")
    resp2 = client.post("/get_profit_by_symbol")

    assert resp1.json() == resp2.json()
    assert state.profit_by_symbol_update_ts > 0
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_dashboard.py -v`
Expected: All 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dashboard.py
git commit -m "test(web-server): add tests for dashboard endpoints"
```

---

## Phase B: Frontend

### Task 5: Project Scaffolding

**Goal**: `web-front/` runs `npm run dev` and shows a blank page with antd configured.

**Files to create**: `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/vite-env.d.ts`, `src/styles/global.css`, `.env.example`

- [ ] **Step 1: Create project with Vite**

Run: `npm create vite@latest web-front -- --template react-ts`
Then: `cd web-front && npm install`

- [ ] **Step 2: Install dependencies**

Run (from `web-front/`): `npm install antd @ant-design/icons zustand echarts echarts-for-react dayjs`

- [ ] **Step 3: Create .env.example**

Create `web-front/.env.example`:
```
VITE_API_URL=
```

- [ ] **Step 4: Create src/vite-env.d.ts with VITE_API_URL type**

Replace `web-front/src/vite-env.d.ts`:
```typescript
/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_API_URL: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 5: Create minimal App.tsx with antd ConfigProvider**

Replace `web-front/src/App.tsx`:
```tsx
import { ConfigProvider, theme } from 'antd'

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <div style={{ padding: 24, color: '#fff' }}>CQuant Dashboard</div>
    </ConfigProvider>
  )
}
```

- [ ] **Step 6: Create src/styles/global.css**

Create `web-front/src/styles/global.css`:
```css
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
#root {
  min-height: 100vh;
}
```

- [ ] **Step 7: Update main.tsx to import global.css**

Replace `web-front/src/main.tsx`:
```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles/global.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 8: Update root .gitignore**

Add to `.gitignore`:
```
web-front/node_modules/
web-front/dist/
```

- [ ] **Step 9: Remove Vite boilerplate files**

Delete: `web-front/src/App.css`, `web-front/src/index.css`, `web-front/src/assets/` (if exists)

- [ ] **Step 10: Verify and commit**

Run (from `web-front/`):
- `npm run dev` — browser shows "CQuant Dashboard" with dark background. Stop after verification.
- `npx tsc --noEmit` — zero errors.

```bash
git add web-front/ .gitignore
git commit -m "feat(web-front): scaffold Vite + React 19 + TypeScript + antd 5 project"
```

---

### Task 6: Types + Utils + API Layer

**Goal**: All TypeScript interfaces, data transformation utilities, and API fetch functions.

**Files to create**: `src/types/index.ts`, `src/utils/format.ts`, `src/api/dashboard.ts`

- [ ] **Step 1: Create src/types/index.ts**

Create `web-front/src/types/index.ts`:
```typescript
// --- API Response Types ---

export interface DashboardSummaryResponse {
  s: string
  balance: number
  positionValue: number
  oneDayVol: number
  oneDayProfit: number
  systemStatus: string
  systemUpdateTs: number
  runTime: number
  t: number
}

export interface ProfitBySymbolResponse {
  s: string
  p: Record<string, number[]>  // [yesterday, week, month, all]
  c: Record<string, number[]>
  v: Record<string, number[]>
  t: number
}

export interface BigLossTradeItem {
  symbol: string
  time: string
  profit: number
  profitPercentByBalance: string
}

export interface BigLossResponse {
  s: string
  d: BigLossTradeItem[]
}

export interface DayIncomeItem {
  allNetProfit: number
  dayBeginTime: string
  dayEndTime: string
  binanceCommission: number
  netProfit: number
  profit: number
  zjyCommission: number
}

export interface DayIncomeResponse {
  s: string
  d: DayIncomeItem[]
  u: number
}

export interface PositionRecordItem {
  positionAmt: number
  positionValue: number
  balance: number
  time: string
  profit: number
  commission: number
  makerCommission: number
  price: null
  entryPrice: null
  unrealizedProfit: number
  maintMargin: null
}

export interface PositionRecordResponse {
  s: string
  d: PositionRecordItem[]
  symbol: string
}

// --- Frontend Display Types ---

export interface HistoryRow {
  key: string
  symbol: string
  yesterdayProfit: string
  yesterdayVol: string
  yesterdayCommission: string
  weekProfit: string
  weekVol: string
  weekCommission: string
  monthProfit: string
  monthVol: string
  monthCommission: string
  allProfit: string
  allVol: string
  allCommission: string
}

export interface ChartData {
  timeArr: string[]
  balanceArr: number[]
  positionValueArr: number[]
  minBalance: number
  minPositionValue: number
}

export interface DayIncomeChartData {
  timeArr: string[]
  barArr: number[]
  lineArr: number[]
  updateTime: string
}

export type ChartRangeType = 'lastOneDay' | 'lastSevenDays' | 'lastOneMonth' | 'all'

export type DayIncomeChartType = 'bar' | 'line'
```

- [ ] **Step 2: Create src/utils/format.ts**

Create `web-front/src/utils/format.ts`:
```typescript
import dayjs from 'dayjs'
import type {
  ProfitBySymbolResponse,
  HistoryRow,
  DayIncomeItem,
  DayIncomeChartData,
  PositionRecordItem,
  ChartData,
  ChartRangeType,
} from '../types'

export function formatTimestamp(ts: number): string {
  const normalized = ts < 100_000_000_000 ? ts * 1000 : ts
  return dayjs(normalized).format('YYYY-MM-DD HH:mm:ss')
}

export function transformProfitToHistoryRows(resp: ProfitBySymbolResponse): HistoryRow[] {
  const rows: HistoryRow[] = []
  for (const key of Object.keys(resp.p)) {
    const pArr = resp.p[key] || [0, 0, 0, 0]
    const vArr = resp.v[key] || [0, 0, 0, 0]
    const cArr = resp.c[key] || [0, 0, 0, 0]
    rows.push({
      key,
      symbol: key === 'all' ? '全部' : key,
      yesterdayProfit: pArr[0].toFixed(6),
      yesterdayVol: vArr[0].toFixed(6),
      yesterdayCommission: cArr[0].toFixed(6),
      weekProfit: pArr[1].toFixed(3),
      weekVol: vArr[1].toFixed(3),
      weekCommission: cArr[1].toFixed(3),
      monthProfit: pArr[2].toFixed(3),
      monthVol: vArr[2].toFixed(3),
      monthCommission: cArr[2].toFixed(3),
      allProfit: pArr[3].toFixed(3),
      allVol: vArr[3].toFixed(3),
      allCommission: cArr[3].toFixed(3),
    })
  }
  return rows
}

export function transformDayIncome(items: DayIncomeItem[]): DayIncomeChartData {
  const timeArr: string[] = []
  const barArr: number[] = []
  const lineArr: number[] = []
  let cumulative = 0
  for (const item of items) {
    timeArr.push(item.dayBeginTime)
    barArr.push(item.netProfit)
    cumulative += item.netProfit
    lineArr.push(cumulative)
  }
  return { timeArr, barArr, lineArr, updateTime: '' }
}

export function transformPositionRecord(items: PositionRecordItem[]): ChartData {
  const timeArr: string[] = []
  const balanceArr: number[] = []
  const positionValueArr: number[] = []
  let minBalance = Infinity
  let minPositionValue = Infinity

  for (const item of items) {
    timeArr.push(item.time)
    balanceArr.push(item.balance)
    positionValueArr.push(item.positionValue)
    if (item.balance < minBalance) minBalance = item.balance
    if (item.positionValue < minPositionValue) minPositionValue = item.positionValue
  }

  return { timeArr, balanceArr, positionValueArr, minBalance, minPositionValue }
}

export function getRangeTimestamps(range: ChartRangeType): { beginTs: number; endTs: number } {
  const now = Math.floor(Date.now() / 1000)
  const endTs = now
  let beginTs: number
  switch (range) {
    case 'lastOneDay':
      beginTs = now - 86400
      break
    case 'lastSevenDays':
      beginTs = now - 7 * 86400
      break
    case 'lastOneMonth':
      beginTs = now - 30 * 86400
      break
    case 'all':
    default:
      beginTs = 0
      break
  }
  return { beginTs, endTs }
}
```

- [ ] **Step 3: Create src/api/dashboard.ts**

Create `web-front/src/api/dashboard.ts`:
```typescript
import type {
  DashboardSummaryResponse,
  ProfitBySymbolResponse,
  BigLossResponse,
  DayIncomeResponse,
  PositionRecordResponse,
} from '../types'

const apiBase = import.meta.env.VITE_API_URL

async function post<T>(path: string, body?: Record<string, string>): Promise<T> {
  const formData = new URLSearchParams()
  if (body) {
    for (const [key, value] of Object.entries(body)) {
      formData.append(key, value)
    }
  }
  const res = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData,
  })
  return res.json()
}

export function fetchDashboardSummary(): Promise<DashboardSummaryResponse> {
  return post('/get_dashboard_summary')
}

export function fetchProfitBySymbol(): Promise<ProfitBySymbolResponse> {
  return post('/get_profit_by_symbol')
}

export function fetchBigLossTrades(): Promise<BigLossResponse> {
  return post('/get_big_loss_trades')
}

export function fetchDayIncome(): Promise<DayIncomeResponse> {
  return post('/get_day_income')
}

export function fetchPositionRecord(
  symbol: string,
  beginTs: number,
  endTs: number,
): Promise<PositionRecordResponse> {
  return post('/get_position_record', {
    symbol,
    beginTs: String(beginTs),
    endTs: String(endTs),
  })
}
```

- [ ] **Step 4: Verify and commit**

Run (from `web-front/`): `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/types/ web-front/src/utils/ web-front/src/api/
git commit -m "feat(web-front): add types, utils, and API layer"
```

---

### Task 7: Zustand Stores (5 stores)

**Goal**: All state management with data fetch actions.

**Files to create**: `src/stores/useThemeStore.ts`, `src/stores/useDashboardStore.ts`, `src/stores/useProfitStore.ts`, `src/stores/useDayIncomeStore.ts`, `src/stores/useChartStore.ts`

- [ ] **Step 1: Create useThemeStore.ts**

Create `web-front/src/stores/useThemeStore.ts`:
```typescript
import { create } from 'zustand'

interface ThemeState {
  isDark: boolean
  toggle: () => void
}

export const useThemeStore = create<ThemeState>((set) => ({
  isDark: localStorage.getItem('theme') !== 'light',
  toggle: () =>
    set((state) => {
      const next = !state.isDark
      localStorage.setItem('theme', next ? 'dark' : 'light')
      return { isDark: next }
    }),
}))
```

- [ ] **Step 2: Create useDashboardStore.ts**

Create `web-front/src/stores/useDashboardStore.ts`:
```typescript
import { create } from 'zustand'
import { fetchDashboardSummary } from '../api/dashboard'

interface DashboardState {
  balance: number
  positionValue: number
  oneDayVol: number
  oneDayProfit: number
  systemStatus: string
  systemUpdateTs: number
  runTime: number
  loading: boolean
  fetchSummary: () => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set) => ({
  balance: 0,
  positionValue: 0,
  oneDayVol: 0,
  oneDayProfit: 0,
  systemStatus: '',
  systemUpdateTs: 0,
  runTime: 0,
  loading: true,
  fetchSummary: async () => {
    try {
      const data = await fetchDashboardSummary()
      if (data.s === 'ok') {
        set({
          balance: data.balance,
          positionValue: data.positionValue,
          oneDayVol: data.oneDayVol,
          oneDayProfit: data.oneDayProfit,
          systemStatus: data.systemStatus,
          systemUpdateTs: data.systemUpdateTs,
          runTime: data.runTime,
          loading: false,
        })
      }
    } catch {
      set({ loading: false })
    }
  },
}))
```

- [ ] **Step 3: Create useProfitStore.ts**

Create `web-front/src/stores/useProfitStore.ts`:
```typescript
import { create } from 'zustand'
import { fetchProfitBySymbol } from '../api/dashboard'
import { transformProfitToHistoryRows } from '../utils/format'
import type { HistoryRow, ProfitBySymbolResponse } from '../types'

interface ProfitState {
  profitData: ProfitBySymbolResponse | null
  historyRows: HistoryRow[]
  historyUpdateTime: string
  fetchProfit: () => Promise<void>
}

export const useProfitStore = create<ProfitState>((set) => ({
  profitData: null,
  historyRows: [],
  historyUpdateTime: '',
  fetchProfit: async () => {
    try {
      const data = await fetchProfitBySymbol()
      if (data.s === 'ok') {
        const rows = transformProfitToHistoryRows(data)
        const updateTime = data.t
          ? new Date(data.t).toLocaleString('zh-CN', { timeZone: 'UTC' })
          : ''
        set({ profitData: data, historyRows: rows, historyUpdateTime: updateTime })
      }
    } catch {
      // silently fail, will retry on next poll
    }
  },
}))
```

- [ ] **Step 4: Create useDayIncomeStore.ts**

Create `web-front/src/stores/useDayIncomeStore.ts`:
```typescript
import { create } from 'zustand'
import { fetchDayIncome } from '../api/dashboard'
import { transformDayIncome } from '../utils/format'
import type { DayIncomeChartData, DayIncomeChartType } from '../types'

interface DayIncomeState {
  chartType: DayIncomeChartType
  chartData: DayIncomeChartData | null
  setChartType: (type: DayIncomeChartType) => void
  fetchDayIncome: () => Promise<void>
}

export const useDayIncomeStore = create<DayIncomeState>((set) => ({
  chartType: (localStorage.getItem('dayIncomeChartType') as DayIncomeChartType) || 'bar',
  chartData: null,
  setChartType: (type) => {
    localStorage.setItem('dayIncomeChartType', type)
    set({ chartType: type })
  },
  fetchDayIncome: async () => {
    try {
      const data = await fetchDayIncome()
      if (data.s === 'ok') {
        const chartData = transformDayIncome(data.d)
        set({ chartData })
      }
    } catch {
      // silently fail
    }
  },
}))
```

- [ ] **Step 5: Create useChartStore.ts**

Create `web-front/src/stores/useChartStore.ts`:
```typescript
import { create } from 'zustand'
import { fetchPositionRecord } from '../api/dashboard'
import { transformPositionRecord, getRangeTimestamps } from '../utils/format'
import type { ChartData, ChartRangeType } from '../types'

interface ChartState {
  range: ChartRangeType
  chartData: ChartData | null
  setRange: (range: ChartRangeType) => void
  fetchPositionRecord: () => Promise<void>
}

export const useChartStore = create<ChartState>((set, get) => ({
  range: 'all',
  chartData: null,
  setRange: (range) => {
    set({ range })
    get().fetchPositionRecord()
  },
  fetchPositionRecord: async () => {
    try {
      const { beginTs, endTs } = getRangeTimestamps(get().range)
      const data = await fetchPositionRecord('ALL', beginTs, endTs)
      if (data.s === 'ok') {
        const chartData = transformPositionRecord(data.d)
        set({ chartData })
      }
    } catch {
      // silently fail
    }
  },
}))
```

- [ ] **Step 6: Verify and commit**

Run (from `web-front/`): `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/stores/
git commit -m "feat(web-front): add 5 Zustand stores for data management"
```

---

### Task 8: Polling Hook + App Shell

**Goal**: Multi-frequency polling lifecycle and basic layout structure.

**Files to create/modify**: `src/hooks/usePolling.ts`, update `src/App.tsx`

- [ ] **Step 1: Create usePolling.ts**

Create `web-front/src/hooks/usePolling.ts`:
```typescript
import { useEffect, useRef } from 'react'
import { useDashboardStore } from '../stores/useDashboardStore'
import { useProfitStore } from '../stores/useProfitStore'
import { useDayIncomeStore } from '../stores/useDayIncomeStore'
import { useChartStore } from '../stores/useChartStore'

export function usePolling() {
  const fetchSummary = useDashboardStore((s) => s.fetchSummary)
  const fetchProfit = useProfitStore((s) => s.fetchProfit)
  const fetchDayIncome = useDayIncomeStore((s) => s.fetchDayIncome)
  const fetchPositionRecord = useChartStore((s) => s.fetchPositionRecord)
  const mounted = useRef(false)

  useEffect(() => {
    if (mounted.current) return
    mounted.current = true

    // Initial fetch all
    fetchSummary()
    fetchProfit()
    fetchDayIncome()
    fetchPositionRecord()

    // KPI: 10s
    const summaryTimer = setInterval(fetchSummary, 10_000)
    // Profit table: 5min
    const profitTimer = setInterval(fetchProfit, 5 * 60_000)
    // Day income: 15min
    const dayIncomeTimer = setInterval(fetchDayIncome, 15 * 60_000)
    // Position record: 5min
    const chartTimer = setInterval(fetchPositionRecord, 5 * 60_000)

    return () => {
      clearInterval(summaryTimer)
      clearInterval(profitTimer)
      clearInterval(dayIncomeTimer)
      clearInterval(chartTimer)
    }
  }, [fetchSummary, fetchProfit, fetchDayIncome, fetchPositionRecord])
}
```

- [ ] **Step 2: Update App.tsx with theme + polling + layout shell**

Replace `web-front/src/App.tsx`:
```tsx
import { ConfigProvider, theme, Layout, Typography } from 'antd'
import { useThemeStore } from './stores/useThemeStore'
import { usePolling } from './hooks/usePolling'
import ThemeToggle from './components/ThemeToggle'

const { Header, Content } = Layout

export default function App() {
  const isDark = useThemeStore((s) => s.isDark)
  usePolling()

  return (
    <ConfigProvider
      theme={{ algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
          }}
        >
          <Typography.Title level={3} style={{ margin: 0, color: isDark ? '#fff' : undefined }}>
            CQuant Dashboard
          </Typography.Title>
          <ThemeToggle />
        </Header>
        <Content style={{ padding: 24 }}>
          {/* Components will be wired in Task 12 */}
        </Content>
      </Layout>
    </ConfigProvider>
  )
}
```

- [ ] **Step 3: Create placeholder ThemeToggle**

Create `web-front/src/components/ThemeToggle.tsx`:
```tsx
import { Button } from 'antd'
import { SunOutlined, MoonOutlined } from '@ant-design/icons'
import { useThemeStore } from '../stores/useThemeStore'

export default function ThemeToggle() {
  const { isDark, toggle } = useThemeStore()
  return (
    <Button
      type="text"
      icon={isDark ? <SunOutlined /> : <MoonOutlined />}
      onClick={toggle}
      style={{ color: isDark ? '#fff' : undefined }}
    />
  )
}
```

- [ ] **Step 4: Verify and commit**

Run (from `web-front/`):
- `npx tsc --noEmit` — zero errors.
- `npm run dev` — header + theme toggle visible, polling visible in browser Network tab. Stop after verification.

```bash
git add web-front/src/hooks/ web-front/src/App.tsx web-front/src/components/ThemeToggle.tsx
git commit -m "feat(web-front): add polling hook, app shell, and theme toggle"
```

---

### Task 9: KPI Cards Component

**Goal**: 5 KPI cards showing live dashboard data.

**Files to create**: `src/components/KpiCards.tsx`

- [ ] **Step 1: Create KpiCards.tsx**

Create `web-front/src/components/KpiCards.tsx`:
```tsx
import { Card, Statistic, Space, Tag } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { useDashboardStore } from '../stores/useDashboardStore'
import { useProfitStore } from '../stores/useProfitStore'
import { formatTimestamp } from '../utils/format'

export default function KpiCards() {
  const { balance, positionValue, oneDayVol, oneDayProfit, systemStatus, systemUpdateTs, runTime } =
    useDashboardStore()
  const profitData = useProfitStore((s) => s.profitData)

  // allProfit = today's profit + all-time historical profit
  const historicalProfit = profitData?.p?.['all']?.[3] ?? 0
  const allProfit = oneDayProfit + historicalProfit

  const isNormal =
    systemUpdateTs > 0 && Date.now() / 1000 - systemUpdateTs < 5 * 60

  return (
    <Space size={16} wrap>
      <Card>
        <Statistic title="总价值" value={Math.round(balance)} suffix="USD" />
      </Card>
      <Card>
        <Statistic title="当前持仓价值" value={Math.round(positionValue)} suffix="USD" />
      </Card>
      <Card>
        <Statistic title="24小时手续费" value={Math.round(oneDayVol)} suffix="USD" />
      </Card>
      <Card>
        <Statistic title="发布至今净利润" value={Math.round(allProfit)} suffix="USD" />
      </Card>
      <Card>
        <Statistic
          title="系统状态"
          valueRender={() =>
            isNormal ? (
              <span>
                <CheckOutlined style={{ color: 'green', marginRight: 8 }} />
                近一分钟检索全币种 {runTime} 次
              </span>
            ) : systemUpdateTs === 0 ? (
              <Tag>加载中</Tag>
            ) : (
              <span>
                <Tag color="red">
                  {systemStatus === 'stopByAccountBalanceValue'
                    ? '亏损停机'
                    : systemStatus === 'bug'
                      ? '系统意外崩溃'
                      : systemStatus === 'maintain'
                        ? '维护中'
                        : systemStatus}
                </Tag>
                {formatTimestamp(systemUpdateTs)}
              </span>
            )
          }
        />
      </Card>
    </Space>
  )
}
```

- [ ] **Step 2: Verify and commit**

Run (from `web-front/`): `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/components/KpiCards.tsx
git commit -m "feat(web-front): add KPI cards component"
```

---

### Task 10: Chart Components (3 charts)

**Goal**: Balance, position value, and day income charts.

**Files to create**: `src/components/BalanceChart.tsx`, `src/components/PositionValueChart.tsx`, `src/components/DayIncomeChart.tsx`

- [ ] **Step 1: Create BalanceChart.tsx**

Create `web-front/src/components/BalanceChart.tsx`:
```tsx
import { Select } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useChartStore } from '../stores/useChartStore'
import { useThemeStore } from '../stores/useThemeStore'
import type { ChartRangeType } from '../types'

const RANGE_OPTIONS: { value: ChartRangeType; label: string }[] = [
  { value: 'lastOneDay', label: '最近一天' },
  { value: 'lastSevenDays', label: '最近七天' },
  { value: 'lastOneMonth', label: '最近一个月' },
  { value: 'all', label: '全部' },
]

export default function BalanceChart() {
  const { range, setRange, chartData } = useChartStore()
  const isDark = useThemeStore((s) => s.isDark)

  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: chartData?.timeArr ?? [] },
    yAxis: { type: 'value' as const, min: chartData?.minBalance },
    series: [{ data: chartData?.balanceArr ?? [], type: 'line' }],
  }

  return (
    <div>
      <Select
        value={range}
        onChange={(val) => setRange(val)}
        style={{ width: 200, marginBottom: 16 }}
        options={RANGE_OPTIONS}
      />
      <ReactECharts
        option={option}
        notMerge
        theme={isDark ? 'dark' : undefined}
        style={{ width: '100%', height: 400 }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Create PositionValueChart.tsx**

Create `web-front/src/components/PositionValueChart.tsx`:
```tsx
import ReactECharts from 'echarts-for-react'
import { useChartStore } from '../stores/useChartStore'
import { useThemeStore } from '../stores/useThemeStore'

export default function PositionValueChart() {
  const chartData = useChartStore((s) => s.chartData)
  const isDark = useThemeStore((s) => s.isDark)

  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: chartData?.timeArr ?? [] },
    yAxis: { type: 'value' as const, min: chartData?.minPositionValue },
    series: [{ data: chartData?.positionValueArr ?? [], type: 'line' }],
  }

  return (
    <ReactECharts
      option={option}
      notMerge
      theme={isDark ? 'dark' : undefined}
      style={{ width: '100%', height: 400 }}
    />
  )
}
```

- [ ] **Step 3: Create DayIncomeChart.tsx**

Create `web-front/src/components/DayIncomeChart.tsx`:
```tsx
import { Select } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useDayIncomeStore } from '../stores/useDayIncomeStore'
import { useThemeStore } from '../stores/useThemeStore'
import type { DayIncomeChartType } from '../types'

const TYPE_OPTIONS: { value: DayIncomeChartType; label: string }[] = [
  { value: 'bar', label: '分段柱形图' },
  { value: 'line', label: '总和折线图' },
]

export default function DayIncomeChart() {
  const { chartType, setChartType, chartData } = useDayIncomeStore()
  const isDark = useThemeStore((s) => s.isDark)

  const dataArr = chartType === 'bar' ? chartData?.barArr : chartData?.lineArr

  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: chartData?.timeArr ?? [] },
    yAxis: { type: 'value' as const },
    series: [{ data: dataArr ?? [], type: chartType }],
  }

  return (
    <div>
      <Select
        value={chartType}
        onChange={(val) => setChartType(val)}
        style={{ width: 200, marginBottom: 16 }}
        options={TYPE_OPTIONS}
      />
      <ReactECharts
        option={option}
        notMerge
        theme={isDark ? 'dark' : undefined}
        style={{ width: '100%', height: 400 }}
      />
    </div>
  )
}
```

- [ ] **Step 4: Verify and commit**

Run (from `web-front/`): `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/components/BalanceChart.tsx web-front/src/components/PositionValueChart.tsx web-front/src/components/DayIncomeChart.tsx
git commit -m "feat(web-front): add balance, position value, and day income charts"
```

---

### Task 11: Table Components

**Goal**: BigLoss and History tables with sorting.

**Files to create**: `src/components/BigLossTable.tsx`, `src/components/HistoryTable.tsx`

- [ ] **Step 1: Create BigLossTable.tsx**

Create `web-front/src/components/BigLossTable.tsx`:
```tsx
import React from 'react'
import { Table, Alert } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { create } from 'zustand'
import { fetchBigLossTrades } from '../api/dashboard'
import type { BigLossTradeItem } from '../types'

// Inline store — only used by this component
interface BigLossState {
  data: BigLossTradeItem[]
  loading: boolean
  fetch: () => Promise<void>
}

const useBigLossStore = create<BigLossState>((set) => ({
  data: [],
  loading: true,
  fetch: async () => {
    try {
      const resp = await fetchBigLossTrades()
      if (resp.s === 'ok') set({ data: resp.d, loading: false })
    } catch {
      set({ loading: false })
    }
  },
}))

const columns: ColumnsType<BigLossTradeItem> = [
  { title: '交易对', dataIndex: 'symbol', key: 'symbol' },
  { title: '时间', dataIndex: 'time', key: 'time' },
  {
    title: '收益金额',
    dataIndex: 'profit',
    key: 'profit',
    sorter: (a, b) => Number(a.profit) - Number(b.profit),
  },
  {
    title: '收益占余额比例',
    dataIndex: 'profitPercentByBalance',
    key: 'profitPercentByBalance',
    sorter: (a, b) =>
      parseFloat(a.profitPercentByBalance) - parseFloat(b.profitPercentByBalance),
  },
]

export default function BigLossTable() {
  const { data, loading, fetch: fetchData } = useBigLossStore()
  const mounted = React.useRef(false)

  React.useEffect(() => {
    if (mounted.current) return
    mounted.current = true
    fetchData()
    const timer = setInterval(fetchData, 60_000)
    return () => clearInterval(timer)
  }, [fetchData])

  if (!loading && data.length === 0) {
    return (
      <Alert
        message="当前暂未读取到大额亏损交易，该数据自2023年5月19日开始记录"
        type="warning"
      />
    )
  }

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey={(_, i) => String(i)}
      loading={loading}
      pagination={{ pageSize: 10 }}
      showSorterTooltip={false}
    />
  )
}
```

- [ ] **Step 2: Create HistoryTable.tsx**

Create `web-front/src/components/HistoryTable.tsx`:
```tsx
import { Table, Alert } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useProfitStore } from '../stores/useProfitStore'
import type { HistoryRow } from '../types'

const numSorter = (field: keyof HistoryRow) => (a: HistoryRow, b: HistoryRow) =>
  parseFloat(a[field]) - parseFloat(b[field])

const columns: ColumnsType<HistoryRow> = [
  { title: '交易对', dataIndex: 'symbol', key: 'symbol' },
  { title: '昨日利润', dataIndex: 'yesterdayProfit', key: 'yesterdayProfit', sorter: numSorter('yesterdayProfit') },
  { title: '昨日BNB', dataIndex: 'yesterdayVol', key: 'yesterdayVol', sorter: numSorter('yesterdayVol') },
  { title: '昨日手续费', dataIndex: 'yesterdayCommission', key: 'yesterdayCommission', sorter: numSorter('yesterdayCommission') },
  { title: '周利润', dataIndex: 'weekProfit', key: 'weekProfit', sorter: numSorter('weekProfit') },
  { title: '周BNB', dataIndex: 'weekVol', key: 'weekVol', sorter: numSorter('weekVol') },
  { title: '周手续费', dataIndex: 'weekCommission', key: 'weekCommission', sorter: numSorter('weekCommission') },
  { title: '月利润', dataIndex: 'monthProfit', key: 'monthProfit', sorter: numSorter('monthProfit') },
  { title: '月BNB', dataIndex: 'monthVol', key: 'monthVol', sorter: numSorter('monthVol') },
  { title: '月手续费', dataIndex: 'monthCommission', key: 'monthCommission', sorter: numSorter('monthCommission') },
  { title: '总利润', dataIndex: 'allProfit', key: 'allProfit', sorter: numSorter('allProfit') },
  { title: '总BNB', dataIndex: 'allVol', key: 'allVol', sorter: numSorter('allVol') },
  { title: '总手续费', dataIndex: 'allCommission', key: 'allCommission', sorter: numSorter('allCommission') },
]

export default function HistoryTable() {
  const { historyRows, historyUpdateTime } = useProfitStore()

  return (
    <div>
      <Alert
        style={{ marginBottom: 16 }}
        message={`更新于：${historyUpdateTime}，利润为净利润，即算上手续费和资金费率后的利润，手续费为负代表付出手续费，手续费为正代表收取手续费`}
        type="warning"
      />
      <Table
        columns={columns}
        dataSource={historyRows}
        rowKey="key"
        pagination={false}
        showSorterTooltip={false}
        scroll={{ x: true }}
      />
    </div>
  )
}
```

- [ ] **Step 3: Verify and commit**

Run (from `web-front/`): `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/components/BigLossTable.tsx web-front/src/components/HistoryTable.tsx
git commit -m "feat(web-front): add big loss and history data tables"
```

---

### Task 12: Final Assembly + Polish

**Goal**: Wire all components into App.tsx, responsive, production build works.

**Files to modify**: `src/App.tsx`

- [ ] **Step 1: Final App.tsx assembly**

Replace `web-front/src/App.tsx`:
```tsx
import { ConfigProvider, theme, Layout, Typography, Divider, Spin } from 'antd'
import { useThemeStore } from './stores/useThemeStore'
import { useDashboardStore } from './stores/useDashboardStore'
import { usePolling } from './hooks/usePolling'
import ThemeToggle from './components/ThemeToggle'
import KpiCards from './components/KpiCards'
import BalanceChart from './components/BalanceChart'
import PositionValueChart from './components/PositionValueChart'
import DayIncomeChart from './components/DayIncomeChart'
import BigLossTable from './components/BigLossTable'
import HistoryTable from './components/HistoryTable'

const { Header, Content } = Layout

export default function App() {
  const isDark = useThemeStore((s) => s.isDark)
  const loading = useDashboardStore((s) => s.loading)
  usePolling()

  return (
    <ConfigProvider
      theme={{ algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
          }}
        >
          <Typography.Title level={3} style={{ margin: 0, color: isDark ? '#fff' : undefined }}>
            CQuant Dashboard
          </Typography.Title>
          <ThemeToggle />
        </Header>
        <Content style={{ padding: 24, maxWidth: 1400, margin: '0 auto', width: '100%' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 100 }}>
              <Spin size="large" />
            </div>
          ) : (
            <>
              <KpiCards />

              <Divider>余额和持仓价值</Divider>
              <BalanceChart />
              <PositionValueChart />

              <Divider>净利润日变化</Divider>
              <DayIncomeChart />

              <Divider>大额亏损交易</Divider>
              <BigLossTable />

              <Divider>历史数据</Divider>
              <HistoryTable />
            </>
          )}
        </Content>
      </Layout>
    </ConfigProvider>
  )
}
```

- [ ] **Step 2: Verify dev server**

Run (from `web-front/`): `npm run dev`
Check: all sections render, theme toggle works, no console errors. Stop after verification.

- [ ] **Step 3: Production build verification**

Run (from `web-front/`):
- `npx tsc --noEmit` — zero TS errors.
- `npm run build` — builds to `web-front/dist/`.

- [ ] **Step 4: Commit**

```bash
git add web-front/src/App.tsx
git commit -m "feat(web-front): wire all components into final dashboard layout"
```

---

### Task 13: Update CLAUDE.md + Mark react-front Deprecated

**Goal**: Update project docs to reflect the new `web-front/` and mark `react-front/` as deprecated.

**Files to modify**: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md Key Modules table**

Add `web-front/` row and mark `react-front/` deprecated:

In the Key Modules table, change the `react-front/` row from:
```
| `react-front/` | React frontend (webpack, antd, echarts, mobx). Reads data from Cloudflare R2 |
```
to:
```
| `react-front/` | **DEPRECATED** — Legacy React 16 frontend (webpack, antd, echarts, mobx). Replaced by `web-front/`. Kept for reference until new frontend is stable |
| `web-front/` | React 19 frontend dashboard (Vite, TypeScript, antd 5, Zustand, ECharts). Fetches data from FastAPI backend API |
```

- [ ] **Step 2: Add web-front Build & Run Commands**

Add a new section under "React Frontend" in Build & Run Commands:

```markdown
### New React Frontend (web-front/)
```bash
cd web-front
npm install

# VITE_API_URL is required — set it in .env or pass directly
VITE_API_URL=http://localhost:8000 npm run dev    # dev server
VITE_API_URL=http://localhost:8000 npm run build  # production build
```
```

Also update the existing "React Frontend" section title to "### Legacy React Frontend (react-front/) — DEPRECATED".

- [ ] **Step 3: Add web_server/routers/dashboard.py to Architecture or Key Modules if needed**

In the `web_server/` description in Key Modules, update:
```
| `web_server/` | FastAPI HTTP server: `app.py` (app factory), `state.py` (shared state), `binance_helpers.py` (Binance API utils), `routers/` (8 route modules) |
```
to:
```
| `web_server/` | FastAPI HTTP server: `app.py` (app factory), `state.py` (shared state), `binance_helpers.py` (Binance API utils), `routers/` (9 route modules incl. `dashboard.py` for frontend KPI/profit APIs) |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add web-front, mark react-front deprecated, update web_server description"
```

---

## Verification Checklist

### Backend
1. `uv run pytest tests/test_dashboard.py -v` — all tests pass
2. `uv run python -c "from web_server.app import app; print('OK')"` — import succeeds

### Frontend
1. `npm run dev` starts without errors
2. All 5 KPI cards render (show zeros if no backend)
3. Balance chart loads, range selector works (4 options)
4. Position value chart updates with range changes
5. Day income chart toggles bar/line
6. BigLoss table shows empty alert or data rows
7. History table 13 columns all sortable
8. Dark/light theme toggle works, persists across reload
9. `npm run build` succeeds
10. `npx tsc --noEmit` zero errors

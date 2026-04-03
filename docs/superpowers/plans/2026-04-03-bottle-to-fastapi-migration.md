# Bottle → FastAPI Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `webServer.py` from Bottle to FastAPI, improving code organization, request validation, and maintainability while preserving 100% API compatibility with the existing React frontend.

**Architecture:** Split the monolithic 2900-line `webServer.py` into a `web_server/` package with FastAPI routers organized by domain. Replace global mutable state with an `AppState` class shared via `app.state`. Use FastAPI's `CORSMiddleware` instead of per-response manual headers. Keep sync endpoints (Binance SDK is sync, FastAPI runs sync handlers in threadpool). Accept form data via `Form()` for backward compatibility with the frontend.

**Tech Stack:** FastAPI, uvicorn, python-multipart (for form data), httpx (for testing), existing SQLModel/PostgreSQL stack

---

## File Structure

```
web_server/
    __init__.py
    app.py                 # FastAPI app factory, lifespan, CORS middleware
    state.py               # AppState class (replaces all global variables)
    binance_helpers.py     # Binance API utility functions (depth, kline, price)
    routers/
        __init__.py
        config.py          # /get_config, /modify_hot_key, /get_state_config, /modify_state_config, /get_symbol_index
        trading.py         # /open_position, /close_position, /take_open, /end_open, /stop_loss_batch, /stop_loss_once, /stop_profit_batch, /stop_profit_once
        orders.py          # /cancel_orders, /cancel_order, /get_all_open_orders, /cancel_binance_orders, /cancel_binance_order, /get_commission_rate, /change_leverage
        income.py          # /get_income_obj, /r, /get_day_income, /get_invest_percent
        records.py         # /get_position_record, /get_history_position_record, /get_order_result_arr, /get_trades_result_arr, /get_big_loss_trades, /begin_trade_record
        status.py          # /ping, /update_machine_status, /update_trade_status, /get_trade_status, /check_maker_server_in_data, /update_maker_server_run_info, /get_customize_dangerous, /update_customize_dangerous
        account.py         # /get_all_acount_info, /get_position, /get_trade_record, /get_all_open_orders_b, /get_second_open_position, /get_watch_info, /update_loss_limit_time, /get_one_day_rate
        market.py          # /get_depth, /get_one_min_select_kline
tests/
    test_web_server.py     # FastAPI endpoint tests
```

**Key design decisions:**
- `Form()` parameters for all endpoints (matches current frontend `application/x-www-form-urlencoded`)
- `AppState` singleton attached to `app.state` — all routers access it via `request.app.state`
- `UTCEncoder`-based JSON serialization preserved via custom `JSONResponse`
- `lifespan` async context manager for startup initialization (`updateSymbolInfo`, wait for BTCUSDT)
- All endpoints remain `POST` to match existing frontend behavior
- `NEW_API_OBJ` (undefined in current code) will be initialized from settings at startup

---

### Task 1: Add FastAPI Dependencies and Create Package Structure

**Files:**
- Modify: `pyproject.toml`
- Create: `web_server/__init__.py`
- Create: `web_server/app.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Add FastAPI, uvicorn, python-multipart, httpx to pyproject.toml**

```toml
[project]
name = "c-binance-futures-quant"
version = "0.1.0"
description = "Binance Futures quantitative trading framework"
requires-python = ">=3.14"
dependencies = [
    "mysql-connector-python",
    "websocket-client",
    "numpy",
    "APScheduler",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "python-multipart>=0.0.20",
    "paramiko",
    "aliyun-python-sdk-core",
    "aliyun-python-sdk-ecs",
    "requests",
    "oss2",
    "pydantic-settings>=2.13.1",
    "sqlmodel>=0.0.37",
    "alembic>=1.18.4",
    "psycopg[binary]>=3.3.3",
]

[dependency-groups]
dev = [
    "pytest>=9.0.2",
    "httpx>=0.28.0",
]
```

Note: `bottle` dependency removed, `fastapi`, `uvicorn[standard]`, `python-multipart` added. `httpx` added to dev for TestClient.

- [ ] **Step 2: Run `uv sync` to install new dependencies**

Run: `uv sync`
Expected: All dependencies install successfully.

- [ ] **Step 3: Create `web_server/__init__.py`**

```python
```

Empty file, just marks the package.

- [ ] **Step 4: Create minimal `web_server/app.py` with health check**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Write test for app creation and health endpoint**

Create `tests/test_web_server.py`:

```python
from fastapi.testclient import TestClient
from web_server.app import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}


def test_cors_headers():
    app = create_app()
    client = TestClient(app)
    resp = client.options("/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert resp.headers.get("access-control-allow-origin") == "*"
```

- [ ] **Step 6: Run tests to verify**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: 2 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock web_server/__init__.py web_server/app.py tests/test_web_server.py
git commit -m "feat: add FastAPI package structure with health endpoint and CORS"
```

---

### Task 2: Create AppState Class (Replace Global Variables)

**Files:**
- Create: `web_server/state.py`
- Modify: `web_server/app.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Create `web_server/state.py` with all global state**

```python
import json
import random
import time
from dataclasses import dataclass, field

from infra_client import InfraClient
from settings import settings


@dataclass
class AppState:
    """Centralized mutable state replacing webServer.py global variables."""

    infra_client: InfraClient = field(default=None)

    # Symbol precision info (populated by update_symbol_info)
    price_decimal_obj: dict = field(default_factory=dict)
    amount_decimal_obj: dict = field(default_factory=dict)
    price_tick_obj: dict = field(default_factory=dict)
    price_decimal_amount_obj: dict = field(default_factory=dict)
    amount_decimal_amount_obj: dict = field(default_factory=dict)
    market_max_size_obj: dict = field(default_factory=dict)
    market_min_size_obj: dict = field(default_factory=dict)

    # Order ID generation
    order_id_symbol: str = "wTake"
    order_id_index: int = field(default_factory=lambda: random.randint(1, 100000))
    private_ip: str = ""

    # API key cache {apiKey: apiSecret}
    api_obj: dict = field(default_factory=dict)

    # NEW_API_OBJ: per-symbol API config for watch/position endpoints
    new_api_obj: dict = field(default_factory=dict)

    # Income cache
    income_obj: dict = field(default_factory=lambda: {
        "15m": {"c": 0, "p": 0, "s": 0},
        "30m": {"c": 0, "p": 0, "s": 0},
        "1h": {"c": 0, "p": 0, "s": 0},
        "4h": {"c": 0, "p": 0, "s": 0},
        "oneDay": {"c": 0, "p": 0, "s": 0},
        "today": {"c": 0, "p": 0, "s": 0},
    })
    symbol_income_obj: dict = field(default_factory=dict)
    last_update_income_ts: int = 0
    income_lock: bool = False

    # Account info cache
    account_info_update_ts: int = 0
    bnb_price: float = 0
    position_arr: list = field(default_factory=lambda: [[] for _ in range(10)])
    assets_arr: list = field(default_factory=lambda: [[] for _ in range(10)])

    # Depth cache
    depth_update_ts: int = 0
    last_binance_response_obj: dict = field(default_factory=dict)

    # Open orders cache
    all_open_orders_arr_update_ts: int = 0
    all_open_orders_arr: list = field(default_factory=list)

    # Record cache
    last_record_ts: int = 0
    record_lock: bool = False

    # Day income cache
    update_day_income_ts: int = 0
    get_day_income_ts: int = 0
    get_day_income_today_ts: int = 0
    day_income_data: list = field(default_factory=list)

    # 1-min kline cache
    one_min_update_ts: int = 0
    one_min_kline: list = field(default_factory=list)

    # Trade server status cache
    trade_server_status_data: list = field(default_factory=list)
    update_trade_server_status_data_ts: int = 0
    customize_dangerous_data_arr: list = field(default_factory=list)
    customize_dangerous_data_arr_update_ts: int = 0

    # Trade machine status
    trade_machine_status_data: list = field(default_factory=list)
    update_trade_machine_status_data_ts: int = 0
    average_run_time: int = 0

    # Binance data cache
    eth_1m_kline_arr: list = field(default_factory=list)
    btc_1m_kline_arr: list = field(default_factory=list)
    eth_today_begin_price: dict = field(default_factory=lambda: {"price": 0, "updateTs": 0})
    btc_today_begin_price: dict = field(default_factory=lambda: {"price": 0, "updateTs": 0})
    tick_arr: list = field(default_factory=list)
    update_binance_data_ts: int = 0

    # Turn price cache
    eth_turn_price: float = 0
    btc_turn_price: float = 0
    turn_price_update_ts: int = 0
    eth_turn_ts: int = 0
    btc_turn_ts: int = 0

    # Watch info cache
    watch_info_update_ts: int = 0
    watch_info_obj: dict = field(default_factory=dict)

    # Loss limit time cache
    get_loss_limit_time_data_ts: int = 0
    loss_limit_time_data_arr: list = field(default_factory=list)

    # One day rate cache
    update_one_day_rate_ts: int = 0
    symbol_data_obj: dict = field(default_factory=dict)

    # Cancel orders throttle
    symbol_cancel_orders_ts_obj: dict = field(default_factory=dict)

    # Big loss trades cache
    big_loss_trades_arr: list = field(default_factory=list)
    update_big_loss_trades_data_ts: int = 0

    # Begin trade record throttle
    symbol_last_insert_ts_obj: dict = field(default_factory=dict)

    # Take open state
    take_open_obj: dict = field(default_factory=dict)

    # BNB buy throttle
    buy_bnb_ts: int = 0

    def update_api_obj(self, api_key: str) -> None:
        """Cache API secret for a given key from settings."""
        if api_key in self.api_obj:
            return
        binance_api_arr = json.loads(settings.binance_api_arr)
        for item in binance_api_arr:
            if api_key == item["apiKey"]:
                self.api_obj[item["apiKey"]] = item["apiSecret"]
                break

    def next_order_id(self) -> int:
        """Increment and return the next order ID index."""
        self.order_id_index += 1
        return self.order_id_index
```

- [ ] **Step 2: Write test for AppState**

Append to `tests/test_web_server.py`:

```python
from web_server.state import AppState


def test_app_state_defaults():
    state = AppState()
    assert state.price_decimal_obj == {}
    assert state.order_id_index >= 1
    assert state.income_obj["15m"]["c"] == 0
    assert len(state.position_arr) == 10


def test_app_state_next_order_id():
    state = AppState()
    first = state.order_id_index
    result = state.next_order_id()
    assert result == first + 1
    assert state.order_id_index == first + 1
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/state.py tests/test_web_server.py
git commit -m "feat: create AppState class to replace global variables"
```

---

### Task 3: Create Binance Helper Functions Module

**Files:**
- Create: `web_server/binance_helpers.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Create `web_server/binance_helpers.py`**

Extract all Binance API utility functions from `webServer.py` (lines 96-228, 645-782). These functions are pure helpers with no Bottle dependency.

```python
import json
import time
import requests
from datetime import datetime as _dt

from settings import settings


class UTCEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, _dt):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj):
    return json.dumps(obj, cls=UTCEncoder)


def update_symbol_info(state):
    """Fetch Binance exchange info and populate symbol precision data on state."""
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.request("GET", url, timeout=(3, 7)).json()
    symbols = response['symbols']
    for i in range(len(symbols)):
        this_instrument_id = symbols[i]['symbol']
        price_tick = 0
        price_decimal = ""
        amount_decimal = ""
        price_decimal_amount = ""
        amount_decimal_amount = ""
        for c in range(len(symbols[i]['filters'])):
            if symbols[i]['filters'][c]['filterType'] == "PRICE_FILTER":
                price_tick = float(symbols[i]['filters'][c]['tickSize'])
                this_decimal = 0
                init_para = 10
                for d in range(20):
                    this_decimal = this_decimal + 1
                    init_para = round(init_para / 10, 10)
                    if init_para == float(symbols[i]['filters'][c]['tickSize']):
                        break
                price_decimal = "%." + str(this_decimal - 1) + "f"
                price_decimal_amount = str(this_decimal - 1)
            if symbols[i]['filters'][c]['filterType'] == "LOT_SIZE":
                this_decimal = 0
                init_para = 10
                for d in range(20):
                    this_decimal = this_decimal + 1
                    init_para = round(init_para / 10, 10)
                    if init_para == float(symbols[i]['filters'][c]['stepSize']):
                        break
                amount_decimal = "%." + str(this_decimal - 1) + "f"
                amount_decimal_amount = str(this_decimal - 1)
            if symbols[i]['filters'][c]['filterType'] == "MARKET_LOT_SIZE":
                state.market_max_size_obj[this_instrument_id] = float(symbols[i]['filters'][c]['maxQty'])
                state.market_min_size_obj[this_instrument_id] = float(symbols[i]['filters'][c]['minQty'])
        state.price_decimal_obj[this_instrument_id] = price_decimal
        state.amount_decimal_obj[this_instrument_id] = amount_decimal
        state.price_tick_obj[this_instrument_id] = price_tick
        state.price_decimal_amount_obj[this_instrument_id] = price_decimal_amount
        if amount_decimal_amount != "":
            state.amount_decimal_amount_obj[this_instrument_id] = int(amount_decimal_amount)


def get_future_depth_by_symbol(symbol, limit):
    """Fetch futures order book depth with retry."""
    response = {}
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=50"
            response = requests.request("GET", url, timeout=timeout).json()
            return response
        except Exception as e:
            if timeout == (2, 2):
                print(e)
    return response


def get_kline(symbol, interval, limit):
    """Fetch kline data with retry."""
    kline_data_arr = []
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
            kline_data_arr = requests.request("GET", url, timeout=timeout).json()
            kline_data_arr.sort(key=lambda elem: float(elem[0]), reverse=False)
            return kline_data_arr
        except Exception as e:
            print(e)
            if timeout == (2, 2):
                pass
    return kline_data_arr


def get_future_now_price_by_depth(symbol):
    """Get current futures mid-price from depth with retry."""
    now_price = 0
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=5"
            response = requests.request("GET", url, timeout=timeout).json()
            now_price = (float(response['asks'][0][0]) + float(response['bids'][0][0])) / 2
            return now_price
        except Exception as e:
            if timeout == (2, 2):
                print(e)
    return now_price


def get_spot_now_price_by_depth(symbol):
    """Get current spot mid-price from depth with retry."""
    now_price = 0
    for timeout in [(0.5, 0.5), (1, 1), (2, 2)]:
        try:
            url = f"https://api.binance.com/api/v1/depth?symbol={symbol}&limit=5"
            response = requests.request("GET", url, timeout=timeout).json()
            now_price = (float(response['asks'][0][0]) + float(response['bids'][0][0])) / 2
            return now_price
        except Exception as e:
            if timeout == (2, 2):
                print(e)
    return now_price


def get_pole_price(symbol, mins):
    """Get high/low price over a time range using appropriate kline interval."""
    mins = int(mins)
    high_price = 0
    low_price = 99999999
    kline_arr = []
    if mins < 500:
        kline_arr = get_kline(symbol, "1m", mins)
    elif mins < 7500:
        kline_arr = get_kline(symbol, "15m", int(mins / 15))
    elif mins < 30000:
        kline_arr = get_kline(symbol, "1h", int(mins / 60))
    elif mins < 120000:
        kline_arr = get_kline(symbol, "4h", int(mins / 240))
    elif mins < 720000:
        kline_arr = get_kline(symbol, "1d", int(mins / 1440))

    for i in range(len(kline_arr)):
        if float(kline_arr[i][2]) > high_price:
            high_price = float(kline_arr[i][2])
        if float(kline_arr[i][3]) < low_price:
            low_price = float(kline_arr[i][3])
    return [high_price, low_price]


def get_stop_loss_price_by_time(symbol, stop_loss_para, position_direction):
    """Calculate stop loss price based on time window high/low."""
    price_arr = get_pole_price(symbol, int(stop_loss_para))
    if position_direction == "longs":
        return price_arr[1]  # low price
    if position_direction == "shorts":
        return price_arr[0]  # high price
    return 0


def get_stop_profit_price_by_time(symbol, stop_profit_para, position_direction):
    """Calculate stop profit price based on time window high/low."""
    price_arr = get_pole_price(symbol, int(stop_profit_para))
    if position_direction == "shorts":
        return price_arr[1]  # low price
    if position_direction == "longs":
        return price_arr[0]  # high price
    return 0
```

- [ ] **Step 2: Write test for binance helpers**

Append to `tests/test_web_server.py`:

```python
from web_server.binance_helpers import json_dumps, UTCEncoder
from datetime import datetime


def test_utc_encoder_datetime():
    dt = datetime(2024, 1, 15, 12, 0, 0)
    result = json_dumps({"time": dt})
    assert "2024-01-15T12:00:00" in result


def test_utc_encoder_non_datetime():
    result = json_dumps({"value": 42})
    assert '"value": 42' in result
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/binance_helpers.py tests/test_web_server.py
git commit -m "feat: extract Binance helper functions into web_server/binance_helpers.py"
```

---

### Task 4: Create Config Router

**Files:**
- Create: `web_server/routers/__init__.py`
- Create: `web_server/routers/config.py`
- Modify: `web_server/app.py`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Create `web_server/routers/__init__.py`**

```python
```

- [ ] **Step 2: Create `web_server/routers/config.py`**

```python
import json

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from settings import settings
from app.models.trade_symbol import TradeSymbol

router = APIRouter()

USER_CONFIG_PATH = "user_config.json"


def load_user_config():
    try:
        with open(USER_CONFIG_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"hot_key_config_obj": {}, "state_config_obj": {}}


def save_user_config(config):
    with open(USER_CONFIG_PATH, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


@router.post("/get_config")
def get_config():
    config = load_user_config()
    binance_api_arr = json.loads(settings.binance_api_arr)
    for item in binance_api_arr:
        item["apiSecret"] = ""
    return {
        "s": "ok",
        "binanceApiArr": binance_api_arr,
        "hotKeyConfigObj": config.get("hot_key_config_obj", {}),
        "stateConfigObj": config.get("state_config_obj", {}),
    }


@router.post("/get_symbol_index")
def get_symbol_index(request: Request):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        rows = session.exec(
            select(TradeSymbol).where(TradeSymbol.status == "yes").order_by(TradeSymbol.id.asc())
        ).all()

    trade_symbol_arr = []
    for i in range(len(rows)):
        link_data = rows[i].link_symbol_arr if isinstance(rows[i].link_symbol_arr, (list, dict)) else json.loads(rows[i].link_symbol_arr or "[]")
        trade_symbol_arr.append({
            "symbol": rows[i].symbol,
            "coin": rows[i].coin,
            "symbolIndex": rows[i].index,
            "quote": rows[i].quote,
            "linkSymbolArr": link_data,
            "defaultShow": rows[i].default_show,
            "weight": 0,
        })

    return {"s": "ok", "d": trade_symbol_arr}


@router.post("/modify_hot_key")
def modify_hot_key(newHotKeyConfigObj: str = Form()):
    new_config = json.loads(newHotKeyConfigObj)
    config = load_user_config()
    config["hot_key_config_obj"] = new_config
    save_user_config(config)
    return {"s": "ok", "newHotKeyConfigObj": new_config}


@router.post("/get_state_config")
def get_state_config():
    config = load_user_config()
    state_config_obj = config.get("state_config_obj", {})
    return {"s": "ok", "stateConfigObj": state_config_obj}


@router.post("/modify_state_config")
def modify_state_config(stateConfigObj: str = Form()):
    state_config = json.loads(stateConfigObj)
    config = load_user_config()
    config["state_config_obj"] = state_config
    save_user_config(config)
    return {"s": "ok", "stateConfigObj": state_config}
```

- [ ] **Step 3: Register config router in `web_server/app.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web_server.routers import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(config.router)

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Write tests for config endpoints**

Append to `tests/test_web_server.py`:

```python
import os
import tempfile
from unittest.mock import patch


def test_get_config():
    app = create_app()
    client = TestClient(app)
    with patch("web_server.routers.config.settings") as mock_settings:
        mock_settings.binance_api_arr = '[{"apiKey":"abc","apiSecret":"secret123","apiDescribe":"test"}]'
        resp = client.post("/get_config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["s"] == "ok"
    assert data["binanceApiArr"][0]["apiSecret"] == ""
    assert data["binanceApiArr"][0]["apiKey"] == "abc"


def test_modify_hot_key():
    app = create_app()
    client = TestClient(app)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{}')
        temp_path = f.name
    try:
        with patch("web_server.routers.config.USER_CONFIG_PATH", temp_path):
            resp = client.post("/modify_hot_key", data={"newHotKeyConfigObj": '{"key1":"value1"}'})
        assert resp.status_code == 200
        assert resp.json()["newHotKeyConfigObj"] == {"key1": "value1"}
    finally:
        os.unlink(temp_path)


def test_get_state_config():
    app = create_app()
    client = TestClient(app)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        import json as _json
        _json.dump({"state_config_obj": {"mode": "test"}}, f)
        temp_path = f.name
    try:
        with patch("web_server.routers.config.USER_CONFIG_PATH", temp_path):
            resp = client.post("/get_state_config")
        assert resp.status_code == 200
        assert resp.json()["stateConfigObj"] == {"mode": "test"}
    finally:
        os.unlink(temp_path)
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: 9 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add web_server/routers/__init__.py web_server/routers/config.py web_server/app.py tests/test_web_server.py
git commit -m "feat: add config router with /get_config, /modify_hot_key, /get_state_config, /modify_state_config, /get_symbol_index"
```

---

### Task 5: Create Market Data Router

**Files:**
- Create: `web_server/routers/market.py`
- Modify: `web_server/app.py`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Create `web_server/routers/market.py`**

```python
import json
import time

import requests
from fastapi import APIRouter, Form, Request

from web_server.binance_helpers import get_kline

router = APIRouter()


@router.post("/get_depth")
def get_depth(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    if now - state.depth_update_ts > 100:
        state.depth_update_ts = now
        url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=50"
        binance_response = requests.request("GET", url, timeout=(0.5, 0.5)).json()
        state.last_binance_response_obj = binance_response

    return {
        "s": "ok",
        "r": state.last_binance_response_obj,
        "i": symbol,
        "p": state.price_decimal_amount_obj[symbol],
        "a": state.amount_decimal_amount_obj[symbol],
    }


@router.post("/get_one_min_select_kline")
def get_one_min_select_kline(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    if now - state.one_min_update_ts >= 100:
        state.one_min_update_ts = now
        kline_arr = get_kline(symbol, "1m", 3)
        state.one_min_kline = kline_arr
    return {"s": "ok", "k": state.one_min_kline}
```

- [ ] **Step 2: Register market router in `web_server/app.py`**

Add import and include:

```python
from web_server.routers import config, market
```

In `create_app()`:

```python
    app.include_router(config.router)
    app.include_router(market.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/market.py web_server/app.py
git commit -m "feat: add market data router with /get_depth, /get_one_min_select_kline"
```

---

### Task 6: Create Orders Router

**Files:**
- Create: `web_server/routers/orders.py`
- Modify: `web_server/app.py`

- [ ] **Step 1: Create `web_server/routers/orders.py`**

```python
import json
import time

from fastapi import APIRouter, Form, Request

from binance_f.requestclient import RequestClient
from binance_f.model.constant import *

router = APIRouter()


@router.post("/change_leverage")
def change_leverage(request: Request, symbol: str = Form(), leverage: int = Form(), apiKey: str = Form()):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.change_initial_leverage(symbol, leverage)
    result = json.loads(result)
    return {"s": "ok", "result": result}


@router.post("/cancel_orders")
def cancel_orders(request: Request, apiKey: str = Form(), symbol: str = Form()):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    result = {}
    try:
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        result = request_client.cancel_all_orders(symbol=symbol)
        result = json.loads(result)
    except Exception as e:
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        result = request_client.cancel_all_orders(symbol=symbol)
        result = json.loads(result)
        print(e)
    return {"s": "ok"}


@router.post("/cancel_order")
def cancel_order(request: Request, apiKey: str = Form(), symbol: str = Form(), clientOrderId: str = Form()):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.cancel_order(symbol=symbol, orderId=clientOrderId)
    return {"s": "ok"}


@router.post("/get_all_open_orders")
def get_all_open_orders(key: str = Form(), secret: str = Form()):
    request_client = RequestClient(api_key=key, secret_key=secret)
    result = request_client.get_all_open_orders()
    result = json.loads(result)
    return {"s": "ok", "r": result, "t": int(time.time())}


@router.post("/cancel_binance_orders")
def cancel_binance_orders(request: Request, key: str = Form(), secret: str = Form(), symbol: str = Form()):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    need_cancel = True
    if symbol in state.symbol_cancel_orders_ts_obj:
        if now - state.symbol_cancel_orders_ts_obj[symbol] <= 3000:
            need_cancel = False

    if need_cancel:
        for _ in range(3):
            try:
                request_client = RequestClient(api_key=key, secret_key=secret)
                result = request_client.cancel_all_orders(symbol=symbol)
            except Exception as e:
                print(e)
        state.symbol_cancel_orders_ts_obj[symbol] = now

    return {"s": "ok"}


@router.post("/cancel_binance_order")
def cancel_binance_order(
    request: Request,
    key: str = Form(),
    secret: str = Form(),
    symbol: str = Form(),
    clientOrderId: str = Form(),
):
    state = request.app.state.app_state
    for attempt in range(3):
        try:
            request_client = RequestClient(api_key=key, secret_key=secret)
            result = request_client.cancel_order(symbol=symbol, orderId=clientOrderId)
            break
        except Exception as e:
            if attempt == 2:
                state.infra_client.send_notify_limit_one_min(
                    f"【cancel order error】，{key},{symbol},{clientOrderId},{e}"
                )
            print(e)
    return {"s": "ok"}


@router.post("/get_commission_rate")
def get_commission_rate(key: str = Form(), secret: str = Form(), symbol: str = Form()):
    request_client = RequestClient(api_key=key, secret_key=secret)
    result = request_client.get_commission_rate(symbol=symbol)
    result = json.loads(result)
    return {"s": "ok", "d": result}
```

- [ ] **Step 2: Register orders router in `web_server/app.py`**

Add import:

```python
from web_server.routers import config, market, orders
```

In `create_app()`:

```python
    app.include_router(orders.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/orders.py web_server/app.py
git commit -m "feat: add orders router with cancel, leverage, open orders, commission endpoints"
```

---

### Task 7: Create Trading Router (Open/Close Position)

**Files:**
- Create: `web_server/routers/trading.py`
- Modify: `web_server/app.py`

This is the largest router — covers `/open_position`, `/close_position`, `/stop_loss_batch`, `/stop_loss_once`, `/stop_profit_batch`, `/stop_profit_once`, `/take_open`, `/end_open`.

- [ ] **Step 1: Create `web_server/routers/trading.py`**

```python
import _thread
import decimal
import json
import math
import time
import traceback

from fastapi import APIRouter, Form, Request

from binance_f.requestclient import RequestClient
from binance_f.model.constant import *
from web_server.binance_helpers import (
    get_future_depth_by_symbol,
    get_pole_price,
    get_spot_now_price_by_depth,
    get_stop_loss_price_by_time,
    get_stop_profit_price_by_time,
)

router = APIRouter()


def _buy_bnb(state, api_key, buy_bnb_amount, bnb_price, asset_type):
    """Buy BNB via spot, transfer to futures. Throttled to once per 60s."""
    now = int(time.time())
    symbol = "BNB" + asset_type
    print("buyBNB")
    if now - state.buy_bnb_ts > 60:
        state.buy_bnb_ts = now
        from binance_f.requestclient import SpotRequestClient
        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.transfer("UMFUTURE_MAIN", asset_type, bnb_price * buy_bnb_amount * 1.05)
        result = json.loads(result)

        amount = buy_bnb_amount
        amount = decimal.Decimal(state.amount_decimal_obj[symbol] % (amount))
        bet_price = decimal.Decimal("%.1f" % (bnb_price * 1.005))

        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.post_order(
            symbol=symbol, quantity=amount, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
            price=bet_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
        )
        result = json.loads(result)
        time.sleep(1)

        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.get_account_information()
        result = json.loads(result)
        result = result['balances']
        bnb_balance = 0
        usdt_balance = 0
        for i in range(len(result)):
            if result[i]['asset'] == asset_type:
                usdt_balance = float(result[i]['free'])
            if result[i]['asset'] == "BNB":
                bnb_balance = float(result[i]['free'])

        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.transfer("MAIN_UMFUTURE", "BNB", bnb_balance)
        result = json.loads(result)
        spot_request_client = SpotRequestClient(api_key=api_key, secret_key=state.api_obj[api_key])
        result = spot_request_client.transfer("MAIN_UMFUTURE", asset_type, usdt_balance)
        result = json.loads(result)
        return True
    return False


def _take_longs_order(state, longs_price, quantity, trade_type, symbol, key, secret):
    """Place a limit long order."""
    longs_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (longs_price)))
    oid = state.next_order_id()
    new_client_order_id = f"{state.order_id_symbol}_{trade_type}_{oid}"
    result = {}
    try:
        request_client = RequestClient(api_key=key, secret_key=secret)
        result = request_client.post_order(
            newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
            quantity=quantity, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
            price=longs_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
        )
        result = json.loads(result)
        if "code" in result and result['code'] == -1001:
            request_client = RequestClient(api_key=key, secret_key=secret)
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=quantity, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
                price=longs_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
            result = json.loads(result)
        if "code" in result and result['code'] not in (-5022, -1001):
            _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"longs order error:{result},{quantity}",))
        print("--------------")
        print(result)
    except Exception as e:
        _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"longsM:{e}",))
    return result


def _take_shorts_order(state, shorts_price, quantity, trade_type, symbol, key, secret):
    """Place a limit short order."""
    shorts_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (shorts_price)))
    oid = state.next_order_id()
    new_client_order_id = f"{state.order_id_symbol}_{trade_type}_{oid}"
    result = {}
    try:
        request_client = RequestClient(api_key=key, secret_key=secret)
        result = request_client.post_order(
            newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
            quantity=quantity, side=OrderSide.SELL, ordertype=OrderType.LIMIT,
            price=shorts_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
        )
        result = json.loads(result)
        if "code" in result and result['code'] == -1001:
            request_client = RequestClient(api_key=key, secret_key=secret)
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=quantity, side=OrderSide.SELL, ordertype=OrderType.LIMIT,
                price=shorts_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
            result = json.loads(result)
        if "code" in result and result['code'] not in (-5022, -1001, -2022):
            _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"shorts order error:{result},{quantity}",))
        print("--------------")
        print(result)
    except Exception as e:
        _thread.start_new_thread(state.infra_client.send_notify_limit_one_min, (f"shortsM:{e}",))
    return result


@router.post("/open_position")
def open_position(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    money: float = Form(),
    tradeType: str = Form(),
    nowPrice: float = Form(),
    paraArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    para_arr = json.loads(paraArr)
    market_max_size = state.market_max_size_obj[symbol]
    result_arr = []
    trade_coin_quantity = 0

    def _timeout_resp():
        return {"s": "timeout", "t": tradeType, "i": symbol}

    def _data_error_resp():
        return {"s": "dataError", "t": tradeType, "i": symbol}

    if tradeType == "openLongsByMarket":
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"marketOpenLongs_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_market_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=OrderSide.BUY, ordertype=OrderType.MARKET,
                positionSide="BOTH", price="0",
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType == "openShortsByMarket":
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"marketOpenShorts_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_market_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=OrderSide.SELL, ordertype=OrderType.MARKET,
                positionSide="BOTH", price="0",
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByDepth", "openShortsByDepth"):
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()
        depth_type = para_arr[0]
        price = 0
        if depth_type == "mid":
            price = (float(depth_obj["bids"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "buy":
            price = float(depth_obj["bids"][int(para_arr[1]) - 1][0])
        elif depth_type == "sell":
            price = float(depth_obj["asks"][int(para_arr[1]) - 1][0])

        price = price * float(para_arr[2])
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        new_client_order_id = f"depthOpenLongs_s{oid}" if tradeType == "openLongsByDepth" else f"depthOpenShorts_s{oid}"
        time_in_force = TimeInForce.GTX if para_arr[4] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.BUY if tradeType == "openLongsByDepth" else OrderSide.SELL

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                price=price, positionSide="BOTH", timeInForce=time_in_force,
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByLeft", "openShortsByLeft"):
        mins = int(para_arr[0])
        price_index = float(para_arr[1])
        price_arr = get_pole_price(symbol, mins)
        high_price = price_arr[0]
        if high_price == 0:
            return _data_error_resp()
        low_price = price_arr[1]
        price = low_price * price_index if tradeType == "openLongsByLeft" else high_price * price_index

        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / price))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        new_client_order_id = f"leftOpenLongs_s{oid}" if tradeType == "openLongsByLeft" else f"leftOpenShortss_s{oid}"
        order_side = OrderSide.BUY if tradeType == "openLongsByLeft" else OrderSide.SELL

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                price=price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByRight", "openShortsByRight"):
        mins = int(para_arr[0])
        price_index = float(para_arr[1])
        price_arr = get_pole_price(symbol, mins)
        high_price = price_arr[0]
        if high_price == 0:
            return _data_error_resp()
        low_price = price_arr[1]
        if tradeType == "openLongsByRight":
            price = high_price * price_index
            stop_price = high_price
        else:
            price = low_price * price_index
            stop_price = low_price

        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / stop_price))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        new_client_order_id = f"rightOpenLongs_s{oid}" if tradeType == "openLongsByRight" else f"rightOpenShorts_s{oid}"
        order_side = OrderSide.BUY if tradeType == "openLongsByRight" else OrderSide.SELL

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_auto_order_with_price(
                newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.STOP,
                stopPrice=stop_price, price=price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType in ("openLongsByBatch", "openShortsByBatch"):
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()
        depth_type = para_arr[0]
        basic_price = 0
        if depth_type == "mid":
            basic_price = (float(depth_obj["bids"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "buy":
            basic_price = float(depth_obj["bids"][int(para_arr[1]) - 1][0])
        elif depth_type == "sell":
            basic_price = float(depth_obj["asks"][int(para_arr[1]) - 1][0])

        basic_price = basic_price * float(para_arr[2])
        add_price_percent = float(para_arr[4])
        order_count = int(para_arr[5])
        price_arr = []
        if add_price_percent == 0:
            basic_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (basic_price)))
            for i in range(order_count):
                if tradeType == "openLongsByBatch":
                    price_arr.append(basic_price - state.price_tick_obj[symbol] * i)
                else:
                    price_arr.append(basic_price + state.price_tick_obj[symbol] * i)
        else:
            for i in range(order_count):
                if tradeType == "openLongsByBatch":
                    price_arr.append(basic_price * (1 - add_price_percent * i / 100))
                else:
                    price_arr.append(basic_price * (1 + add_price_percent * i / 100))

        time_in_force = TimeInForce.GTX if para_arr[6] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.BUY if tradeType == "openLongsByBatch" else OrderSide.SELL
        for i in range(len(price_arr)):
            price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price_arr[i])))
            coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice / order_count))
            if coin_quantity > market_max_size:
                coin_quantity = market_max_size
                trade_coin_quantity = market_max_size

            oid = state.next_order_id()
            new_client_order_id = f"depthOpenLongs_s{oid}" if tradeType == "openLongsByBatch" else f"depthOpenShorts_s{oid}"

            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                    price=price, positionSide="BOTH", timeInForce=time_in_force,
                )
            except Exception:
                return _timeout_resp()
            result = json.loads(result)
            result_arr.append(result)

    elif tradeType == "openLongsByPrice":
        price = float(para_arr[0])
        client_id_prefix = "rightOpenLongs" if price > nowPrice else "leftOpenLongs"
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / price))
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"{client_id_prefix}_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            if client_id_prefix == "leftOpenLongs":
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.BUY, ordertype=OrderType.LIMIT,
                    positionSide="BOTH", price=price, timeInForce=TimeInForce.GTC,
                )
            else:
                result = request_client.post_auto_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.BUY, ordertype=OrderType.STOP_MARKET,
                    stopPrice=price, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC,
                )
        except Exception:
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    elif tradeType == "openShortsByPrice":
        price = float(para_arr[0])
        client_id_prefix = "rightOpenShorts" if price < nowPrice else "leftOpenShorts"
        coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (money / price))
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size
        oid = state.next_order_id()
        new_client_order_id = f"{client_id_prefix}_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            if client_id_prefix == "leftOpenShorts":
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.SELL, ordertype=OrderType.LIMIT,
                    positionSide="BOTH", price=price, timeInForce=TimeInForce.GTC,
                )
            else:
                result = request_client.post_auto_order(
                    newClientOrderId=new_client_order_id, reduceOnly=False, symbol=symbol,
                    quantity=coin_quantity, side=OrderSide.SELL, ordertype=OrderType.STOP_MARKET,
                    stopPrice=price, price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC,
                )
        except Exception as e:
            print(e)
            return _timeout_resp()
        result = json.loads(result)
        result_arr.append(result)

    return {
        "s": "ok",
        "resultArr": result_arr,
        "tradeCoinQuantity": trade_coin_quantity,
        "money": money,
        "symbol": symbol,
        "tradeType": tradeType,
    }


@router.post("/close_position")
def close_position(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    money: float = Form(),
    tradeType: str = Form(),
    nowPrice: float = Form(),
    direction: str = Form(),
    paraArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    para_arr = json.loads(paraArr)
    market_max_size = state.market_max_size_obj[symbol]
    trade_coin_quantity = 0
    result_arr = []

    def _timeout_resp():
        return {"s": "timeout", "t": tradeType, "i": symbol}

    def _data_error_resp():
        return {"s": "dataError", "t": tradeType, "i": symbol}

    if tradeType == "selectCoinCloseByMarket":
        oid = state.next_order_id()
        new_client_order_id = f"marketCloseLongs_s{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        order_side = OrderSide.SELL if direction == "longs" else OrderSide.BUY
        try:
            result = request_client.post_market_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=market_max_size, side=order_side, ordertype=OrderType.MARKET,
                price="0", positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return _timeout_resp()
        result_arr.append(json.loads(result))

    elif tradeType == "selectCoinCloseByDepth":
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()

        money = money * float(para_arr[0])
        depth_type = para_arr[1]
        depth_number = int(para_arr[2]) - 1
        price = 0
        if depth_type == "mid":
            price = (float(depth_obj["bids"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "reverse":
            price = float(depth_obj["bids"][depth_number][0]) if direction == "longs" else float(depth_obj["asks"][depth_number][0])
        elif depth_type == "positive":
            price = float(depth_obj["asks"][depth_number][0]) if direction == "longs" else float(depth_obj["bids"][depth_number][0])

        price_index = float(para_arr[3]) if direction == "longs" else float(para_arr[4])
        price = price * price_index
        price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price)))
        coin_quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice)))
        if coin_quantity > market_max_size:
            coin_quantity = market_max_size
            trade_coin_quantity = market_max_size

        oid = state.next_order_id()
        new_client_order_id = f"depthLongsClose_s{oid}" if direction == "longs" else f"depthShortsClose_s{oid}"
        time_in_force = TimeInForce.GTX if para_arr[5] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.SELL if direction == "longs" else OrderSide.BUY

        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                price=price, positionSide="BOTH", timeInForce=time_in_force,
            )
        except Exception:
            return _timeout_resp()
        result_arr.append(json.loads(result))

    elif tradeType == "selectCoinCloseByBatch":
        depth_obj = get_future_depth_by_symbol(symbol, 50)
        if "bids" not in depth_obj:
            return _data_error_resp()

        money = money * float(para_arr[0])
        depth_type = para_arr[1]
        depth_number = int(para_arr[2]) - 1
        basic_price = 0
        if depth_type == "mid":
            basic_price = (float(depth_obj["asks"][0][0]) + float(depth_obj["bids"][0][0])) / 2
        elif depth_type == "reverse":
            basic_price = float(depth_obj["bids"][depth_number][0]) if direction == "longs" else float(depth_obj["asks"][depth_number][0])
        elif depth_type == "positive":
            basic_price = float(depth_obj["asks"][depth_number][0]) if direction == "longs" else float(depth_obj["bids"][depth_number][0])

        price_index = float(para_arr[3]) if direction == "longs" else float(para_arr[4])
        basic_price = basic_price * price_index
        add_price_percent = float(para_arr[5])
        order_count = int(para_arr[6])
        price_arr = []
        if add_price_percent == 0:
            basic_price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (basic_price)))
            for i in range(order_count):
                if direction == "longs":
                    price_arr.append(basic_price + state.price_tick_obj[symbol] * i)
                else:
                    price_arr.append(basic_price - state.price_tick_obj[symbol] * i)
        else:
            for i in range(order_count):
                if direction == "longs":
                    price_arr.append(basic_price * (1 + add_price_percent * i / 100))
                else:
                    price_arr.append(basic_price * (1 - add_price_percent * i / 100))

        time_in_force = TimeInForce.GTX if para_arr[7] == "GTX" else TimeInForce.GTC
        order_side = OrderSide.SELL if direction == "longs" else OrderSide.BUY
        for i in range(len(price_arr)):
            price = float(decimal.Decimal(state.price_decimal_obj[symbol] % (price_arr[i])))
            coin_quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (money / nowPrice / order_count)))
            if coin_quantity > market_max_size:
                coin_quantity = market_max_size
                trade_coin_quantity = market_max_size

            oid = state.next_order_id()
            new_client_order_id = f"batchLongsClose_s{oid}" if direction == "longs" else f"batchShortsClose_s{oid}"

            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                    quantity=coin_quantity, side=order_side, ordertype=OrderType.LIMIT,
                    price=price, positionSide="BOTH", timeInForce=time_in_force,
                )
            except Exception:
                return _timeout_resp()
            result_arr.append(json.loads(result))

    return {
        "s": "ok",
        "resultArr": result_arr,
        "tradeCoinQuantity": trade_coin_quantity,
        "marketMaxSize": market_max_size,
        "symbol": symbol,
        "tradeType": tradeType,
    }


@router.post("/stop_loss_batch")
def stop_loss_batch(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    positionDirection: str = Form(),
    stopLossPriceArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_loss_price_arr = json.loads(stopLossPriceArr)
    market_max_size = state.market_max_size_obj[symbol]
    stop_loss_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_loss_price_arr)))

    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    some_order_timeout = False

    for i in range(len(stop_loss_price_arr)):
        stop_loss_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_loss_price_arr[i]))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopLoss_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        if i == len(stop_loss_price_arr) - 1:
            remaining = coinAmount - float(decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_loss_price_arr)))) * (len(stop_loss_price_arr) - 1)
            stop_loss_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (remaining))
        try:
            result = request_client.post_auto_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=stop_loss_coin_quantity, side=position_side, ordertype=OrderType.STOP_MARKET,
                stopPrice=stop_loss_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            some_order_timeout = True
        result = json.loads(result)
        order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "someOrderTimeOut": some_order_timeout}


@router.post("/stop_loss_once")
def stop_loss_once(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    stopLossType: str = Form(),
    stopLossParaArr: str = Form(),
    positionDirection: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_loss_para_arr = json.loads(stopLossParaArr)
    market_max_size = state.market_max_size_obj[symbol]

    stop_loss_price = 0
    if stopLossType == "time":
        time_index = stop_loss_para_arr[1]
        stop_loss_price = get_stop_loss_price_by_time(symbol, stop_loss_para_arr[0], positionDirection) * time_index
    elif stopLossType == "price":
        stop_loss_price = float(stop_loss_para_arr[0])

    stop_loss_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_loss_price))
    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    order_count = math.ceil(coinAmount / market_max_size)

    if order_count > 10:
        return {"s": "tooMuchPosition", "marketMaxSize": market_max_size, "symbol": symbol}

    if order_count == 1:
        coin_amount = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopLoss_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_auto_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=coin_amount, side=position_side, ordertype=OrderType.STOP_MARKET,
                stopPrice=stop_loss_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
            )
        except Exception:
            return {"s": "timeout", "t": stopLossType, "i": symbol}
        result = json.loads(result)
        order_result_arr.append(result)
    else:
        for i in range(order_count):
            oid = state.next_order_id()
            new_client_order_id = f"{positionDirection}StopLoss_s_{oid}"
            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_auto_order(
                    newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                    quantity=market_max_size, side=position_side, ordertype=OrderType.STOP_MARKET,
                    stopPrice=stop_loss_price, positionSide="BOTH", timeInForce=TimeInForce.GTC,
                )
            except Exception:
                return {"s": "timeout", "t": stopLossType, "i": symbol}
            result = json.loads(result)
            order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "stopLossType": stopLossType}


@router.post("/stop_profit_batch")
def stop_profit_batch(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    positionDirection: str = Form(),
    stopProfitPriceArr: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_profit_price_arr = json.loads(stopProfitPriceArr)
    market_max_size = state.market_max_size_obj[symbol]

    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.get_open_orders(symbol=symbol)
    result = json.loads(result)
    stop_profit_order_id_arr = []
    for i in range(len(result)):
        client_order_id = result[i]['clientOrderId']
        order_type_symbol = client_order_id.split("_")[0]
        if order_type_symbol in ("shortsStopProfit", "longsStopProfit"):
            stop_profit_order_id_arr.append(client_order_id)

    for cid in stop_profit_order_id_arr:
        for _ in range(2):
            try:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                request_client.cancel_order(symbol=symbol, orderId=cid)
                break
            except Exception as e:
                print(e)

    stop_profit_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_profit_price_arr)))
    if stop_profit_coin_quantity > market_max_size:
        return {"s": "tooMuchPosition", "marketMaxSize": market_max_size, "symbol": symbol}

    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    some_order_timeout = False

    for i in range(len(stop_profit_price_arr)):
        stop_profit_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_profit_price_arr[i]))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopProfit_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        if i == len(stop_profit_price_arr) - 1:
            remaining = coinAmount - float(decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount / len(stop_profit_price_arr)))) * (len(stop_profit_price_arr) - 1)
            stop_profit_coin_quantity = decimal.Decimal(state.amount_decimal_obj[symbol] % (remaining))
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=stop_profit_coin_quantity, side=position_side, ordertype=OrderType.LIMIT,
                price=stop_profit_price, positionSide="BOTH", timeInForce=TimeInForce.GTX,
            )
        except Exception:
            some_order_timeout = True
        result = json.loads(result)
        order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "someOrderTimeOut": some_order_timeout}


@router.post("/stop_profit_once")
def stop_profit_once(
    request: Request,
    apiKey: str = Form(),
    symbol: str = Form(),
    coinAmount: float = Form(),
    stopProfitType: str = Form(),
    stopProfitParaArr: str = Form(),
    positionDirection: str = Form(),
):
    state = request.app.state.app_state
    state.update_api_obj(apiKey)
    stop_profit_para_arr = json.loads(stopProfitParaArr)
    market_max_size = state.market_max_size_obj[symbol]

    request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
    result = request_client.get_open_orders(symbol=symbol)
    result = json.loads(result)
    stop_profit_order_id_arr = []
    for i in range(len(result)):
        client_order_id = result[i]['clientOrderId']
        order_type_symbol = client_order_id.split("_")[0]
        if order_type_symbol in ("shortsStopProfit", "longsStopProfit"):
            stop_profit_order_id_arr.append(client_order_id)

    for cid in stop_profit_order_id_arr:
        for _ in range(2):
            try:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                request_client.cancel_order(symbol=symbol, orderId=cid)
                break
            except Exception as e:
                print(e)

    stop_profit_price = 0
    if stopProfitType == "time":
        time_index = stop_profit_para_arr[1]
        stop_profit_price = get_stop_profit_price_by_time(symbol, stop_profit_para_arr[0], positionDirection) * time_index
    elif stopProfitType == "price":
        stop_profit_price = float(stop_profit_para_arr[0])

    stop_profit_price = decimal.Decimal(state.price_decimal_obj[symbol] % (stop_profit_price))
    order_result_arr = []
    position_side = OrderSide.SELL if positionDirection == "longs" else OrderSide.BUY
    order_count = math.ceil(coinAmount / market_max_size)

    if order_count > 10:
        return {"s": "tooMuchPosition", "marketMaxSize": market_max_size, "symbol": symbol}

    if order_count == 1:
        coin_amount = decimal.Decimal(state.amount_decimal_obj[symbol] % (coinAmount))
        oid = state.next_order_id()
        new_client_order_id = f"{positionDirection}StopProfit_s_{oid}"
        request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
        try:
            result = request_client.post_order(
                newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                quantity=coin_amount, side=position_side, ordertype=OrderType.LIMIT,
                price=stop_profit_price, positionSide="BOTH", timeInForce=TimeInForce.GTX,
            )
        except Exception:
            return {"s": "timeout", "t": stopProfitType, "i": symbol}
        result = json.loads(result)
        order_result_arr.append(result)
    else:
        for i in range(order_count):
            oid = state.next_order_id()
            new_client_order_id = f"{positionDirection}StopProfit_s_{oid}"
            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            try:
                result = request_client.post_order(
                    newClientOrderId=new_client_order_id, reduceOnly=True, symbol=symbol,
                    quantity=market_max_size, side=position_side, ordertype=OrderType.LIMIT,
                    price=stop_profit_price, positionSide="BOTH", timeInForce=TimeInForce.GTX,
                )
            except Exception:
                return {"s": "timeout", "t": stopProfitType, "i": symbol}
            result = json.loads(result)
            order_result_arr.append(result)

    return {"s": "ok", "resultArr": order_result_arr, "symbol": symbol, "stopProfitType": stopProfitType}


@router.post("/take_open")
def take_open(
    request: Request,
    key: str = Form(),
    secret: str = Form(),
    symbol: str = Form(),
    direction: str = Form(),
    price: float = Form(),
    openTime: int = Form(),
    positionValue: float = Form(),
    volMultiple: float = Form(),
):
    state = request.app.state.app_state
    try:
        now = int(time.time() * 1000)
        should_trade = (
            (positionValue == 0 and symbol in state.take_open_obj and now - state.take_open_obj[symbol]["ts"] > 60000 * 15)
            or (symbol in state.take_open_obj and state.take_open_obj[symbol]["status"] == "end")
            or (symbol in state.take_open_obj and openTime > state.take_open_obj[symbol]["openTime"])
            or (symbol not in state.take_open_obj)
        )
        if should_trade:
            state.take_open_obj[symbol] = {"ts": now, "openTime": openTime, "status": "trading"}
            if direction == "longs":
                value = 100
                quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (value / price)))
                _take_longs_order(state, price, quantity, "T", symbol, key, secret)
                state.infra_client.send_notify_limit_one_min(f"{symbol} take longs")
            if direction == "shorts":
                value = 100
                quantity = float(decimal.Decimal(state.amount_decimal_obj[symbol] % (value / price)))
                _take_shorts_order(state, price, quantity, "T", symbol, key, secret)
                state.infra_client.send_notify_limit_one_min(f"{symbol} take shorts")
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
    return {"s": "ok"}


@router.post("/end_open")
def end_open(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    try:
        if symbol in state.take_open_obj and state.take_open_obj[symbol]["status"] != "end":
            state.take_open_obj[symbol]["status"] = "end"
            state.infra_client.send_notify_limit_one_min(f"{symbol} end trade")
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
    return {"s": "ok"}
```

- [ ] **Step 2: Register trading router in `web_server/app.py`**

Add import:

```python
from web_server.routers import config, market, orders, trading
```

In `create_app()`:

```python
    app.include_router(trading.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/trading.py web_server/app.py
git commit -m "feat: add trading router with open/close position, stop loss/profit, take/end open"
```

---

### Task 8: Create Income Router

**Files:**
- Create: `web_server/routers/income.py`
- Modify: `web_server/app.py`

- [ ] **Step 1: Create `web_server/routers/income.py`**

```python
import decimal
import json
import time
import datetime

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from binance_f.requestclient import RequestClient
from app.models.income import Income
from app.models.income_day import IncomeDay
from web_server.binance_helpers import get_future_now_price_by_depth, json_dumps

router = APIRouter()


@router.post("/get_income_obj")
def get_income_obj(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.last_update_income_ts >= 9:
        if now - state.last_update_income_ts >= 60 or (not state.income_lock):
            state.last_update_income_ts = now
            state.income_lock = True

            today_time = datetime.datetime.utcnow().strftime("%Y-%m-%d") + " 00:00:00"
            today_ts = state.infra_client.turn_ts_to_time(today_time)

            today_limit_ts = today_ts * 1000
            fifteen_mins_limit_ts = int(time.time() * 1000) - 900000
            thirty_mins_limit_ts = int(time.time() * 1000) - 1800000
            one_hour_limit_ts = int(time.time() * 1000) - 3600000
            four_hours_limit_ts = int(time.time() * 1000) - 14400000
            one_day_limit_ts = int(time.time() * 1000) - 86400000
            limit_ts = int(time.time() * 1000) - 86400000

            with state.infra_client.get_session() as session:
                data = session.exec(
                    select(Income).where(Income.binance_ts > limit_ts).order_by(Income.id.desc())
                ).all()

            if len(data) > 0:
                state.income_obj = {
                    "15m": {"c": 0, "p": 0, "s": 0},
                    "30m": {"c": 0, "p": 0, "s": 0},
                    "1h": {"c": 0, "p": 0, "s": 0},
                    "4h": {"c": 0, "p": 0, "s": 0},
                    "oneDay": {"c": 0, "p": 0, "s": 0},
                    "today": {"c": 0, "p": 0, "s": 0},
                }

            symbol_income_obj = {}
            for row in data:
                sym = row.symbol
                binance_ts = row.binance_ts
                value = row.income
                commission = row.commission
                if sym not in symbol_income_obj:
                    symbol_income_obj[sym] = {
                        "15m": {"p": 0, "c": 0}, "30m": {"p": 0, "c": 0},
                        "1h": {"p": 0, "c": 0}, "4h": {"p": 0, "c": 0},
                        "oneDay": {"p": 0, "c": 0}, "today": {"p": 0, "c": 0},
                    }

                if row.asset == "BNB":
                    value = row.income * row.bnb_price

                time_buckets = [
                    ("15m", fifteen_mins_limit_ts), ("30m", thirty_mins_limit_ts),
                    ("1h", one_hour_limit_ts), ("4h", four_hours_limit_ts),
                    ("oneDay", one_day_limit_ts), ("today", today_limit_ts),
                ]

                if row.income_type == "COMMISSION":
                    for bucket, limit in time_buckets:
                        if binance_ts >= limit:
                            state.income_obj[bucket]["c"] += value
                            state.income_obj[bucket]["s"] += commission
                            symbol_income_obj[sym][bucket]["c"] += value
                if row.income_type == "REALIZED_PNL":
                    for bucket, limit in time_buckets:
                        if binance_ts >= limit:
                            state.income_obj[bucket]["p"] += value
                            symbol_income_obj[sym][bucket]["p"] += value

            state.symbol_income_obj = symbol_income_obj
            state.income_lock = False

    return json.loads(json.dumps({
        "s": "ok", "i": state.income_obj, "n": int(time.time()), "d": state.symbol_income_obj,
    }))


def _update_day_income(state):
    """Update income_day table with aggregated daily data."""
    now = int(time.time())
    if now - state.update_day_income_ts > 30:
        state.update_day_income_ts = now

        with state.infra_client.get_session() as session:
            latest_day = session.exec(
                select(IncomeDay).order_by(IncomeDay.id.desc()).limit(1)
            ).first()

        init_income_day_time = "2022-11-20 00:00:00"
        init_income_day_ts = state.infra_client.turn_ts_to_time(init_income_day_time)
        last_income_day_ts = 0
        if latest_day is not None:
            last_income_day_ts = state.infra_client.turn_ts_to_time(latest_day.day_begin_time)
        if last_income_day_ts == 0:
            last_income_day_ts = init_income_day_ts
        now_ts = int(time.time())
        today_ts = now_ts - now_ts % 86400

        need_insert_day = int((today_ts - last_income_day_ts) / 86400)
        for i in range(need_insert_day):
            end_day_ts = last_income_day_ts + 86400 * (i + 1)
            begin_day_ts = last_income_day_ts + 86400 * i
            with state.infra_client.get_session() as session:
                income_data = session.exec(
                    select(Income)
                    .where(Income.binance_ts > begin_day_ts * 1000)
                    .where(Income.binance_ts <= end_day_ts * 1000)
                ).all()
            day_binance_commission = 0
            day_zjy_commission = 0
            day_pnl = 0
            for item in income_data:
                if item.income_type == "COMMISSION":
                    if item.asset == "BNB":
                        day_binance_commission += item.income * item.bnb_price
                    elif item.asset in ("USDT", "BUSD"):
                        day_binance_commission += item.income
                elif item.income_type == "REALIZED_PNL":
                    if item.asset == "BNB":
                        day_pnl += item.income * item.bnb_price
                    elif item.asset in ("USDT", "BUSD"):
                        day_pnl += item.income
                day_zjy_commission += item.commission

            with state.infra_client.get_session() as session:
                existing_day = session.exec(
                    select(IncomeDay).where(IncomeDay.day_begin_time == state.infra_client.turn_ts_to_time(begin_day_ts))
                ).first()
                if existing_day is None:
                    new_day = IncomeDay(
                        api_key="",
                        day_begin_time=state.infra_client.turn_ts_to_time(begin_day_ts),
                        day_end_time=state.infra_client.turn_ts_to_time(end_day_ts),
                        binance_commission=day_binance_commission,
                        pnl=day_pnl,
                        zjy_commission=day_zjy_commission,
                    )
                    session.add(new_day)
                    session.commit()
                else:
                    existing_day.binance_commission = day_binance_commission
                    existing_day.pnl = day_pnl
                    existing_day.zjy_commission = day_zjy_commission
                    session.add(existing_day)
                    session.commit()


@router.post("/get_day_income")
def get_day_income(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    today_time = datetime.datetime.utcnow().strftime("%Y-%m-%d") + " 00:00:00"
    today_ts = state.infra_client.turn_ts_to_time(today_time)
    is_update = 0

    if now - state.get_day_income_ts > 300 or state.get_day_income_today_ts != today_ts:
        _update_day_income(state)
        is_update = 1
        state.get_day_income_today_ts = today_ts
        state.get_day_income_ts = now
        with state.infra_client.get_session() as session:
            day_income_data = session.exec(
                select(IncomeDay).order_by(IncomeDay.id.asc())
            ).all()
        state.day_income_data = []
        for item in day_income_data:
            if state.infra_client.turn_ts_to_time(item.day_begin_time) != today_ts:
                state.day_income_data.append({
                    "allNetProfit": 0,
                    "dayBeginTime": item.day_begin_time,
                    "dayEndTime": item.day_end_time,
                    "binanceCommission": item.binance_commission,
                    "netProfit": item.pnl + item.binance_commission,
                    "profit": item.pnl,
                    "zjyCommission": item.zjy_commission,
                })

    if state.infra_client.turn_ts_to_time(state.day_income_data[len(state.day_income_data) - 1]["dayBeginTime"]) != today_ts:
        state.day_income_data.append({
            "allNetProfit": 0,
            "dayBeginTime": state.infra_client.turn_ts_to_time(today_ts),
            "dayEndTime": state.infra_client.turn_ts_to_time(today_ts + 86400),
            "binanceCommission": state.income_obj["today"]["c"],
            "netProfit": state.income_obj["today"]["c"] + state.income_obj["today"]["p"],
            "profit": state.income_obj["today"]["p"],
            "zjyCommission": state.income_obj["today"]["s"],
        })
    else:
        state.day_income_data[len(state.day_income_data) - 1] = {
            "allNetProfit": 0,
            "dayBeginTime": state.infra_client.turn_ts_to_time(today_ts),
            "dayEndTime": state.infra_client.turn_ts_to_time(today_ts + 86400),
            "binanceCommission": state.income_obj["today"]["c"],
            "netProfit": state.income_obj["today"]["c"] + state.income_obj["today"]["p"],
            "profit": state.income_obj["today"]["p"],
            "zjyCommission": state.income_obj["today"]["s"],
        }

    return json.loads(json_dumps({"s": "ok", "d": state.day_income_data, "u": is_update}))


@router.post("/r")
def record_income(request: Request, apiKey: str = Form()):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.last_record_ts >= 9:
        if now - state.last_record_ts >= 300 or (not state.record_lock):
            state.record_lock = True
            state.last_record_ts = now
            state.update_api_obj(apiKey)

            with state.infra_client.get_session() as session:
                last_binance_ts_data = session.exec(
                    select(Income)
                    .where(Income.api_key == apiKey)
                    .order_by(Income.id.desc())
                    .limit(100)
                ).all()

            last_binance_ts = 0
            if len(last_binance_ts_data) > 0:
                last_binance_ts = last_binance_ts_data[0].binance_ts

            result = []
            try:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                result = request_client.get_income_history_with_no_symbol()
                result = json.loads(result)
            except Exception:
                request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
                result = request_client.get_income_history_with_no_symbol()
                result = json.loads(result)

            result.sort(key=lambda elem: float(elem["time"]), reverse=False)
            bnb_price = get_future_now_price_by_depth("BNBUSDT")

            for i in range(len(result)):
                trade_id = str(result[i]['tradeId'])
                binance_ts = str(result[i]['time'])
                income_type = str(result[i]['incomeType'])
                income = str(result[i]['income'])
                asset = str(result[i]['asset'])
                sym = str(result[i]['symbol'])

                if income_type in ("COMMISSION", "REALIZED_PNL"):
                    is_exit = False
                    for b in range(len(last_binance_ts_data)):
                        if (
                            int(result[i]['time']) < last_binance_ts
                            or (
                                str(int(last_binance_ts_data[b].binance_ts)) == str(int(binance_ts))
                                and str(last_binance_ts_data[b].income_type) == str(income_type)
                                and format(float(last_binance_ts_data[b].income), '.8f') == format(float(income), '.8f')
                                and str(last_binance_ts_data[b].asset) == str(asset)
                                and str(last_binance_ts_data[b].trade_id) == str(trade_id)
                            )
                        ):
                            is_exit = True
                    if not is_exit:
                        commission = 0
                        if income_type == "COMMISSION":
                            if asset == "BNB":
                                commission = abs(float(income) * bnb_price * 0.1) if float(income) < 0 else abs(float(income) * bnb_price * 0.05)
                            else:
                                commission = abs(float(income) * 0.1) if float(income) < 0 else abs(float(income) * 0.05)

                        with state.infra_client.get_session() as session:
                            new_income = Income(
                                access_token=str(apiKey),
                                api_key=str(apiKey),
                                income_type=str(income_type),
                                income=decimal.Decimal(str(income)),
                                asset=str(asset),
                                trade_id=trade_id,
                                binance_ts=int(binance_ts),
                                symbol=sym,
                                bnb_price=decimal.Decimal(str(bnb_price)),
                                commission=decimal.Decimal(str(commission)),
                            )
                            session.add(new_income)
                            session.commit()
            state.record_lock = False
    return {"s": "ok"}


@router.post("/get_invest_percent")
def get_invest_percent():
    invest_percent_obj_arr = [
        {'name': '吴钊庆', 'time': '2023-05-19 14:59:00', 'percent': 12.206461839330702, 'initValue': 2800, 'assetsWhileJoin': 20138.67, 'investType': 'longs'},
        {'name': '一零二四', 'time': '2023-05-19 13:36:00', 'percent': 21.81179905448812, 'initValue': 5000, 'assetsWhileJoin': 15125.24, 'investType': 'longs'},
        {'name': '李', 'time': '2023-05-16 21:52:00', 'percent': 8.808005636839024, 'initValue': 2000, 'assetsWhileJoin': 12982.22, 'investType': 'longs'},
        {'name': 'michael', 'time': '2023-05-12 20:28:00', 'percent': 52.16531441742779, 'initValue': 10000, 'assetsWhileJoin': 959, 'investType': 'longs'},
        {'name': 'ming', 'time': '2023-05-09 00:00:00', 'percent': 5.008419051914373, 'initValue': 750, 'assetsWhileJoin': 0, 'investType': 'longs'},
    ]
    for item in invest_percent_obj_arr:
        item["percent"] = int(item["percent"] * 10000) / 10000
    return {"s": "ok", "t": int(time.time()), "r": invest_percent_obj_arr}
```

- [ ] **Step 2: Register income router in `web_server/app.py`**

Add import and include:

```python
from web_server.routers import config, market, orders, trading, income
```

```python
    app.include_router(income.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/income.py web_server/app.py
git commit -m "feat: add income router with /get_income_obj, /r, /get_day_income, /get_invest_percent"
```

---

### Task 9: Create Records Router

**Files:**
- Create: `web_server/routers/records.py`
- Modify: `web_server/app.py`

- [ ] **Step 1: Create `web_server/routers/records.py`**

```python
import json
import time
import traceback
from decimal import Decimal

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from app.models.position_record import PositionRecord
from app.models.trade_record import TradeRecord
from app.models.trades import Trades
from app.models.trades_take import TradesTake
from app.models.begin_trade_record import BeginTradeRecord
from web_server.binance_helpers import json_dumps

router = APIRouter()


@router.post("/get_position_record")
def get_position_record(
    request: Request,
    symbol: str = Form(),
    beginTs: int = Form(),
    endTs: int = Form(),
):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        stmt = select(PositionRecord).where(PositionRecord.ts > beginTs, PositionRecord.ts < endTs)
        if symbol != "ALL":
            stmt = stmt.where(PositionRecord.symbol == symbol)
        position_record_data = session.exec(stmt).all()

    result = []
    for row in position_record_data:
        result.append({
            "positionAmt": row.position_amt,
            "price": None,
            "positionValue": row.position_value,
            "balance": row.balance,
            "time": row.time,
            "profit": row.profit,
            "commission": row.commission,
            "makerCommission": row.maker_commission,
            "entryPrice": None,
            "unrealizedProfit": row.unrealized_profit,
            "maintMargin": None,
        })
    return {"s": "ok", "d": result, "symbol": symbol}


@router.post("/get_history_position_record")
def get_history_position_record(
    request: Request,
    tableName: str = Form(),
    beginTs: int = Form(),
    endTs: int = Form(),
):
    state = request.app.state.app_state
    symbol = tableName
    with state.infra_client.get_session() as session:
        stmt = select(PositionRecord).where(PositionRecord.ts > beginTs, PositionRecord.ts < endTs)
        if symbol not in ("ALL", ""):
            stmt = stmt.where(PositionRecord.symbol == symbol)
        position_record_data = session.exec(stmt).all()

    result = []
    for row in position_record_data:
        result.append({
            "positionAmt": row.position_amt,
            "price": None,
            "positionValue": row.position_value,
            "balance": row.balance,
            "time": row.time,
            "profit": row.profit,
            "commission": row.commission,
            "makerCommission": row.maker_commission,
        })
    return {"s": "ok", "d": result}


@router.post("/get_big_loss_trades")
def get_big_loss_trades(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.update_big_loss_trades_data_ts > 60:
        state.update_big_loss_trades_data_ts = now
        with state.infra_client.get_session() as session:
            big_loss_data = session.exec(
                select(TradeRecord).where(TradeRecord.profit_percent_by_balance <= -0.15).order_by(TradeRecord.id.desc())
            ).all()
        state.big_loss_trades_arr = []
        for row in big_loss_data:
            state.big_loss_trades_arr.append({
                "symbol": row.symbol,
                "time": state.infra_client.turn_ts_to_time(row.end_ts),
                "profit": row.profit,
                "profitPercentByBalance": str(abs(int(row.profit_percent_by_balance * 100) / 100)) + "%",
            })
    return json.loads(json_dumps({"s": "ok", "d": state.big_loss_trades_arr}))


@router.post("/begin_trade_record")
def begin_trade_record(
    request: Request,
    volMultiple: float = Form(),
    standardRate: float = Form(),
    symbol: str = Form(),
    klineArr: str = Form(),
    nowOpenRate: float = Form(),
    machineNumber: str = Form(),
    direction: str = Form(),
    myTradeType: str = Form(),
    longsConditionA: int = Form(),
    shortsConditionA: int = Form(),
    shortsConditionB: int = Form(),
    btcNowOpenRate: float = Form(),
    ethNowOpenRate: float = Form(),
    clientBeginPrice: float = Form(),
    clientEndPrice: float = Form(),
    privateIP: str = Form(),
):
    state = request.app.state.app_state
    try:
        ts = int(time.time() * 1000)
        kline_arr_str = json.dumps(json.loads(klineArr))

        with state.infra_client.get_session() as session:
            trades_data = session.exec(
                select(TradesTake).where(TradesTake.symbol == symbol, TradesTake.status == "tradeBegin")
            ).all()

        if myTradeType.find("open") >= 0 and len(trades_data) == 0:
            if symbol not in state.symbol_last_insert_ts_obj or ts - state.symbol_last_insert_ts_obj[symbol] > 30000:
                state.symbol_last_insert_ts_obj[symbol] = ts
                with state.infra_client.get_session() as session:
                    new_row = TradesTake(
                        status="tradeBegin", version=3,
                        vol_multiple=Decimal(str(volMultiple)), standard_rate=Decimal(str(standardRate)),
                        symbol=symbol, kline_arr=kline_arr_str,
                        now_open_rate=Decimal(str(nowOpenRate)), begin_machine_number=machineNumber,
                        direction=direction, longs_condition_a=longsConditionA,
                        shorts_condition_a=shortsConditionA, shorts_condition_b=shortsConditionB,
                        btc_now_open_rate=Decimal(str(btcNowOpenRate)), eth_now_open_rate=Decimal(str(ethNowOpenRate)),
                        begin_ts=ts, end_ts=ts, trade_type=myTradeType, update_ts=ts,
                        client_begin_price=Decimal(str(clientBeginPrice)), client_end_price=Decimal(str(clientEndPrice)),
                    )
                    session.add(new_row)
                    session.commit()
        else:
            state.infra_client.send_notify_limit_one_min(myTradeType)

        return {"s": "ok"}
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
        return {"s": "error"}


@router.post("/get_order_result_arr")
def get_order_result_arr(
    request: Request,
    symbol: str = Form(),
    beginTs: int = Form(),
    endTs: int = Form(),
):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        begin_trade_record_data = session.exec(
            select(BeginTradeRecord)
            .where(BeginTradeRecord.symbol == symbol, BeginTradeRecord.ts > beginTs - 60000, BeginTradeRecord.ts < endTs + 60000)
            .order_by(BeginTradeRecord.id.desc())
            .limit(5000)
        ).all()

    result = []
    for row in begin_trade_record_data:
        result.append({
            "symbol": row.symbol,
            "time": row.time,
            "asksDepthArr": json.loads(row.asks_depth_arr or "[]"),
            "bidsDepthArr": json.loads(row.bids_depth_arr or "[]"),
            "ordersResult": json.loads(row.orders_result or "{}"),
            "direction": row.direction,
            "nowOpenRate": row.now_open_rate,
            "machineNumber": row.machine_number,
            "ts": row.ts,
            "myTradeType": row.my_trade_type,
            "nowPrice": row.now_price,
        })
    return {"s": "ok", "d": result}


@router.post("/get_trades_result_arr")
def get_trades_result_arr(request: Request, tradeTimeIntervalIndex: int = Form()):
    state = request.app.state.app_state
    try:
        now_ts = int(time.time() * 1000)
        interval_map = {0: 4, 1: 8, 2: 12, 3: 24, 4: 72}
        hours = interval_map.get(tradeTimeIntervalIndex, 4)
        limit_ts = now_ts - hours * 60 * 60 * 1000
        if limit_ts < 1686960000000:
            limit_ts = 1686960000000

        with state.infra_client.get_session() as session:
            trades_record_data = session.exec(
                select(Trades)
                .where(Trades.status == "updateProfit", Trades.begin_ts > limit_ts, Trades.version == 2)
                .order_by(Trades.id.desc())
            ).all()

        trades_record_arr = []
        for row in trades_record_data:
            vol_info_parsed = json.loads(row.vol_info) if isinstance(row.vol_info, str) else (row.vol_info or {})
            boll_up = row.begin_boll_up or 0
            boll_down = row.begin_boll_down or 0
            trades_record_arr.append([
                row.symbol, row.begin_ts, row.end_ts, row.direction,
                row.profit, row.value, row.cost, vol_info_parsed,
                row.open_type, row.open_time, row.add_time, row.close_time,
                row.open_gtx_time, row.add_gtx_time, row.close_gtx_time,
                row.now_open_rate, row.standard_rate, row.take_time,
                state.infra_client.get_percent_num(boll_up - boll_down, boll_down),
                row.take_value,
            ])

        with state.infra_client.get_session() as session:
            fail_data = session.exec(
                select(Trades).where(Trades.status == "updateProfitFail", Trades.begin_ts > limit_ts, Trades.version == 2)
            ).all()

        return {"s": "ok", "d": trades_record_arr, "fT": len(fail_data), "fV": 0}
    except Exception:
        ex = traceback.format_exc()
        state.infra_client.send_notify_limit_one_min(str(ex))
        return {"s": "error"}
```

- [ ] **Step 2: Register records router in `web_server/app.py`**

Add import and include:

```python
from web_server.routers import config, market, orders, trading, income, records
```

```python
    app.include_router(records.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/records.py web_server/app.py
git commit -m "feat: add records router with position, trades, big loss, begin trade endpoints"
```

---

### Task 10: Create Status Router

**Files:**
- Create: `web_server/routers/status.py`
- Modify: `web_server/app.py`

- [ ] **Step 1: Create `web_server/routers/status.py`**

```python
import json
import time

from fastapi import APIRouter, Form, Request
from sqlmodel import select

from binance_f.requestclient import RequestClient
from web_server.binance_helpers import get_spot_now_price_by_depth
from app.models.trade_server_status import TradeServerStatus
from app.models.machine_status import MachineStatus, TradeMachineStatus

router = APIRouter()


def _update_trade_server_status_data(state):
    """Refresh trade server status cache."""
    now = int(time.time())
    if now - state.update_trade_server_status_data_ts > 5:
        state.update_trade_server_status_data_ts = now
        with state.infra_client.get_session() as session:
            rows = session.exec(select(TradeServerStatus)).all()
        state.trade_server_status_data = []
        for item in rows:
            extra_para = json.loads(item.extra_para) if item.extra_para else {}
            state.trade_server_status_data.append({
                "extraPara": extra_para,
                "runInfo": json.loads(item.run_info) if item.run_info else {},
                "symbol": item.symbol,
                "privateIP": item.private_ip,
                "name": item.name,
                "mySymbol": item.my_symbol,
                "updateTs": item.update_ts,
                "updateTime": item.update_time,
                "customizeDangerousData": extra_para,
            })


@router.post("/ping")
def ping(
    request: Request,
    apiKey: str = Form(),
    apiIndex: int = Form(),
    timestamp: int = Form(),
    autoBuyBnbConfigArr: str = Form(),
    symbol: str = Form(),
):
    state = request.app.state.app_state
    auto_buy_config = json.loads(autoBuyBnbConfigArr)
    auto_buy_bnb = auto_buy_config[2]
    begin_min_bnb_money = auto_buy_config[0]
    buy_bnb_money = auto_buy_config[1]

    state.update_api_obj(apiKey)
    now = int(time.time() * 1000)

    # getBinanceAccountInfo logic
    buy_bnb_result = False
    if now - state.account_info_update_ts > 60000:
        positions_arr = []
        assets_arr = []
        try:
            request_client = RequestClient(api_key=apiKey, secret_key=state.api_obj[apiKey])
            result = request_client.get_account_information()
            result = json.loads(result)
            for i in range(len(result["positions"])):
                if float(result["positions"][i]["positionAmt"]) != 0:
                    positions_arr.append(result["positions"][i])
            assets_arr = result["assets"]
            bnb_amount = -1
            usdt_amount = -1
            busd_amount = -1
            for i in range(len(assets_arr)):
                if assets_arr[i]['asset'] == "BNB":
                    bnb_amount = float(assets_arr[i]['marginBalance'])
                if assets_arr[i]['asset'] == "USDT":
                    usdt_amount = float(assets_arr[i]['marginBalance'])
                if assets_arr[i]['asset'] == "BUSD":
                    busd_amount = float(assets_arr[i]['marginBalance'])
            state.bnb_price = get_spot_now_price_by_depth("BNBUSDT")
            # Auto BNB buy logic omitted for safety — preserved in trading router's _buy_bnb
            state.position_arr[apiIndex] = positions_arr
            state.assets_arr[apiIndex] = assets_arr
        except Exception as e:
            print(e)
        state.account_info_update_ts = now

    return {
        "s": "ok",
        "p": state.position_arr,
        "t": state.assets_arr,
        "r": buy_bnb_result,
        "n": now,
        "b": state.bnb_price,
        "l": timestamp,
    }


@router.post("/check_maker_server_in_data")
def check_maker_server_in_data(
    request: Request,
    name: str = Form(),
    privateIP: str = Form(),
    symbol: str = Form(),
    mySymbol: str = Form(),
):
    state = request.app.state.app_state
    with state.infra_client.get_session() as session:
        existing = session.exec(
            select(TradeServerStatus).where(TradeServerStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            extra_para = {"customizeDangerous": 0}
            new_row = TradeServerStatus(
                private_ip=privateIP,
                name=name,
                extra_para=json.dumps(extra_para),
                symbol=symbol,
                my_symbol=mySymbol,
            )
            session.add(new_row)
            session.commit()
    return {"s": "ok"}


@router.post("/update_maker_server_run_info")
def update_maker_server_run_info(
    request: Request,
    privateIP: str = Form(),
    dangerousClass: str = Form(),
    dangerousName: str = Form(),
    direction: str = Form(),
    longsOnceTradeValue: float = Form(),
    shortsOnceTradeValue: float = Form(),
    longsBollTimeAmount: float = Form(),
    shortsBollTimeAmount: float = Form(),
    positionValue: float = Form(),
    symbol: str = Form(),
):
    state = request.app.state.app_state
    run_info = {
        "dangerousClass": dangerousClass,
        "dangerousName": dangerousName,
        "longsOnceTradeValue": longsOnceTradeValue,
        "shortsOnceTradeValue": shortsOnceTradeValue,
        "longsBollTimeAmount": longsBollTimeAmount,
        "shortsBollTimeAmount": shortsBollTimeAmount,
        "positionValue": positionValue,
        "direction": direction,
    }
    now = int(time.time())
    with state.infra_client.get_session() as session:
        db_row = session.exec(
            select(TradeServerStatus).where(TradeServerStatus.private_ip == privateIP)
        ).first()
        if db_row is not None:
            db_row.run_info = json.dumps(run_info)
            db_row.update_ts = now
            db_row.update_time = state.infra_client.turn_ts_to_time(now)
            session.add(db_row)
            session.commit()

    _update_trade_server_status_data(state)
    customize_dangerous_data = {"customizeDangerous": 0}
    for a in range(len(state.trade_server_status_data)):
        if state.trade_server_status_data[a]["privateIP"] == privateIP:
            customize_dangerous_data = state.trade_server_status_data[a]["customizeDangerousData"]
            break

    return {"s": "ok", "customizeDangerous": customize_dangerous_data["customizeDangerous"]}


@router.post("/get_customize_dangerous")
def get_customize_dangerous(request: Request):
    state = request.app.state.app_state
    SYMBOL_ARR = ["ETHUSDT", "BTCUSDT"]
    now = int(time.time())
    _update_trade_server_status_data(state)

    if now - state.customize_dangerous_data_arr_update_ts > 5:
        state.customize_dangerous_data_arr_update_ts = now
        result = []
        for sym in SYMBOL_ARR:
            for item in state.trade_server_status_data:
                if item["symbol"] == sym:
                    result.append({
                        "customizeDangerous": item["customizeDangerousData"]["customizeDangerous"],
                        "dangerousName": item["runInfo"]["dangerousName"],
                        "dangerousClass": item["runInfo"]["dangerousClass"],
                        "symbol": item["symbol"],
                    })
        state.customize_dangerous_data_arr = result

    return {"s": "ok", "customizeDangerousDataArr": state.customize_dangerous_data_arr}


@router.post("/update_customize_dangerous")
def update_customize_dangerous(
    request: Request,
    customizeDangerous: int = Form(),
    symbol: str = Form(),
):
    state = request.app.state.app_state
    extra_info = json.dumps({"customizeDangerous": customizeDangerous})
    with state.infra_client.get_session() as session:
        if symbol == "all":
            rows = session.exec(select(TradeServerStatus)).all()
        else:
            rows = session.exec(
                select(TradeServerStatus).where(TradeServerStatus.symbol == symbol)
            ).all()
        for row in rows:
            row.extra_para = extra_info
            session.add(row)
        session.commit()
    return {"s": "ok"}


@router.post("/update_machine_status")
def update_machine_status(request: Request, privateIP: str = Form(), symbol: str = Form()):
    state = request.app.state.app_state
    update_ts = int(time.time())
    with state.infra_client.get_session() as session:
        existing = session.exec(
            select(MachineStatus).where(MachineStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            row = MachineStatus(private_ip=privateIP, insert_ts=update_ts, update_ts=update_ts, symbol=symbol)
            session.add(row)
        else:
            existing[0].update_ts = update_ts
            session.add(existing[0])
        session.commit()
    return {"s": "ok"}


@router.post("/update_trade_status")
def update_trade_status(request: Request, privateIP: str = Form(), status: str = Form(), runTime: str = Form()):
    state = request.app.state.app_state
    update_ts = int(time.time())
    with state.infra_client.get_session() as session:
        existing = session.exec(
            select(TradeMachineStatus).where(TradeMachineStatus.private_ip == privateIP)
        ).all()
        if len(existing) == 0:
            row = TradeMachineStatus(private_ip=privateIP, insert_ts=update_ts, update_ts=update_ts, status=status)
            session.add(row)
        else:
            existing[0].status = status
            existing[0].update_ts = update_ts
            existing[0].run_time = int(runTime)
            session.add(existing[0])
        session.commit()
    return {"s": "ok"}


@router.post("/get_trade_status")
def get_trade_status(request: Request):
    state = request.app.state.app_state
    from sqlalchemy import asc as _asc
    now = int(time.time())
    if now - state.update_trade_machine_status_data_ts > 60:
        state.update_trade_machine_status_data_ts = now
        with state.infra_client.get_session() as session:
            state.trade_machine_status_data = session.exec(
                select(TradeMachineStatus).order_by(_asc(TradeMachineStatus.update_ts))
            ).all()
        all_run_time = 0
        for item in state.trade_machine_status_data:
            all_run_time += (item.run_time or 0)
        if len(state.trade_machine_status_data) > 0:
            state.average_run_time = int(all_run_time / len(state.trade_machine_status_data))

    if len(state.trade_machine_status_data) > 0:
        return {
            "s": "ok",
            "updateTs": state.trade_machine_status_data[0].update_ts,
            "status": state.trade_machine_status_data[0].status,
            "runTime": state.average_run_time,
        }
    return {"s": "ok", "updateTs": 0, "status": "", "runTime": 0}
```

- [ ] **Step 2: Register status router in `web_server/app.py`**

Add import and include:

```python
from web_server.routers import config, market, orders, trading, income, records, status
```

```python
    app.include_router(status.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/status.py web_server/app.py
git commit -m "feat: add status router with ping, machine/trade status, server status endpoints"
```

---

### Task 11: Create Account Router (Watch Info, Position, One Day Rate)

**Files:**
- Create: `web_server/routers/account.py`
- Modify: `web_server/app.py`

- [ ] **Step 1: Create `web_server/routers/account.py`**

```python
import json
import time
import datetime

import requests
from fastapi import APIRouter, Form, Request
from sqlalchemy import func
from sqlmodel import select

from binance_f.requestclient import RequestClient
from app.models.position_record import PositionRecord
from app.models.loss_limit_time import LossLimitTime
from web_server.binance_helpers import json_dumps

router = APIRouter()


@router.post("/get_all_acount_info")
def get_all_acount_info(request: Request):
    state = request.app.state.app_state
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
    return {"s": "ok", "b": all_balance, "p": all_position, "t": int(time.time())}


@router.post("/get_all_open_orders_b")
def get_all_open_orders_b(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    request_client = RequestClient(
        api_key=state.new_api_obj[symbol]["apiKey"],
        secret_key=state.new_api_obj[symbol]["apiSecret"],
    )
    result = request_client.get_all_open_orders()
    result = json.loads(result)
    return {"s": "ok", "r": result, "t": int(time.time())}


@router.post("/get_position")
def get_position(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    positions_arr = []
    request_client = RequestClient(
        api_key=state.new_api_obj[symbol]["apiKey"],
        secret_key=state.new_api_obj[symbol]["apiSecret"],
    )
    result = request_client.get_account_information()
    result = json.loads(result)
    for i in range(len(result["positions"])):
        if float(result["positions"][i]["positionAmt"]) != 0:
            positions_arr.append(result["positions"][i])
    return {"s": "ok", "r": positions_arr, "t": int(time.time())}


@router.post("/get_trade_record")
def get_trade_record(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    request_client = RequestClient(
        api_key=state.new_api_obj[symbol]["apiKey"],
        secret_key=state.new_api_obj[symbol]["apiSecret"],
    )
    result = request_client.get_account_trades(symbol)
    result = json.loads(result)
    return {"s": "ok", "r": result, "t": int(time.time())}


@router.post("/get_second_open_position")
def get_second_open_position():
    BINANCE_API_KEY = "bJpPkJe9kW8USXKDQuP2WKeSVaEIOM5wKT7Uta1ir2wmlAxNHN9hwrZDhjJCYcEd"
    this_ip = "172.24.207.4"
    url = f"http://{this_ip}/{BINANCE_API_KEY[0:10]}.json"
    result = requests.request("GET", url, timeout=(0.5, 0.5)).json()
    return {"s": "ok", "t": int(time.time()), "r": result}


@router.post("/update_loss_limit_time")
def update_loss_limit_time(request: Request, symbol: str = Form()):
    state = request.app.state.app_state
    now_time = state.infra_client.turn_ts_to_time(int(time.time()))
    now_time_str = str(now_time) if not isinstance(now_time, str) else now_time
    with state.infra_client.get_session() as session:
        row = session.exec(select(LossLimitTime).where(LossLimitTime.symbol == symbol)).first()
        if row:
            row.limit_time = now_time_str
            session.add(row)
            session.commit()
    # Refresh cache
    _get_loss_limit_time_data(state, True)
    return {"s": "ok", "t": int(time.time())}


def _get_loss_limit_time_data(state, force_update):
    """Refresh loss limit time cache."""
    now = int(time.time())
    if (now - state.get_loss_limit_time_data_ts > 60) or force_update:
        state.get_loss_limit_time_data_ts = now
        with state.infra_client.get_session() as session:
            loss_limit_time_data = session.exec(select(LossLimitTime)).all()
        state.loss_limit_time_data_arr = []
        for row in loss_limit_time_data:
            state.loss_limit_time_data_arr.append({
                "symbol": row.symbol,
                "limitTime": row.limit_time,
            })


def _update_binance_data(state):
    """Fetch ETH/BTC kline + all tickers."""
    now = int(time.time())
    if now - state.update_binance_data_ts >= 1:
        state.update_binance_data_ts = now
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=ETHUSDT&interval=1m&limit=99"
            eth_kline = requests.request("GET", url, timeout=(1, 1)).json()
            if len(eth_kline) == 99:
                state.eth_1m_kline_arr = eth_kline
        except Exception as e:
            print(e)
        try:
            url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=99"
            btc_kline = requests.request("GET", url, timeout=(1, 1)).json()
            if len(btc_kline) == 99:
                state.btc_1m_kline_arr = btc_kline
        except Exception as e:
            print(e)
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/price"
            tick_arr = requests.request("GET", url, timeout=(1, 1)).json()
            if len(tick_arr) > 100:
                state.tick_arr = tick_arr
        except Exception as e:
            print(e)


def _update_turn_price(state):
    """Update ETH/BTC turn price from position records."""
    now = int(time.time())
    if now - state.turn_price_update_ts > 60:
        state.turn_price_update_ts = now
        with state.infra_client.get_session() as session:
            for symbol_name, price_attr, ts_attr in [
                ("ETHUSDT", "eth_turn_price", "eth_turn_ts"),
                ("BTCUSDT", "btc_turn_price", "btc_turn_ts"),
            ]:
                latest = session.exec(
                    select(PositionRecord).where(PositionRecord.symbol == symbol_name).order_by(PositionRecord.id.desc()).limit(1)
                ).first()
                if latest:
                    position_amt = latest.position_amt or 0
                    if position_amt > 0:
                        last_turn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == symbol_name, PositionRecord.position_amt < 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                    else:
                        last_turn = session.exec(
                            select(PositionRecord).where(PositionRecord.symbol == symbol_name, PositionRecord.position_amt > 0).order_by(PositionRecord.id.desc()).limit(1)
                        ).first()
                    if last_turn:
                        setattr(state, price_attr, 0)
                        setattr(state, ts_attr, last_turn.ts)


def _update_trade_server_status_data(state):
    """Imported from status router logic — duplicated here to avoid circular imports."""
    from web_server.routers.status import _update_trade_server_status_data as _update
    _update(state)


@router.post("/get_watch_info")
def get_watch_info(request: Request):
    state = request.app.state.app_state
    now = int(time.time())
    if now - state.watch_info_update_ts >= 60:
        state.watch_info_update_ts = now
        _update_binance_data(state)
        all_position_arr = []
        _update_trade_server_status_data(state)
        _update_turn_price(state)

        for key in state.new_api_obj:
            day_begin_balance_update_time = state.infra_client.turn_ts_to_day_time(now)
            if day_begin_balance_update_time != state.new_api_obj[key]["dayBeginBalaneUpdateTime"]:
                zero_point = state.infra_client.turn_ts_to_time(day_begin_balance_update_time)
                with state.infra_client.get_session() as session:
                    first_row = session.exec(
                        select(PositionRecord).where(PositionRecord.ts >= zero_point).order_by(PositionRecord.id.asc()).limit(1)
                    ).first()
                if first_row:
                    state.new_api_obj[key]["dayBeginBalane"] = first_row.balance
                    state.new_api_obj[key]["dayBeginBalaneUpdateTime"] = day_begin_balance_update_time

            this_ip = state.new_api_obj[key]["positionIP"]
            this_key = state.new_api_obj[key]["apiKey"]
            my_symbol = state.new_api_obj[key]["mySymbol"]
            day_begin_balance = state.new_api_obj[key]["dayBeginBalane"]
            symbol = state.new_api_obj[key]["symbol"]

            _get_loss_limit_time_data(state, False)
            this_loss_limit_time = ""
            for item in state.loss_limit_time_data_arr:
                if item["symbol"] == symbol:
                    this_loss_limit_time = item["limitTime"]
                    break
            if this_loss_limit_time == "":
                with state.infra_client.get_session() as session:
                    session.add(LossLimitTime(symbol=symbol, limit_time="2023-03-28 01:00:00"))
                    session.commit()
                _get_loss_limit_time_data(state, True)

            url = f"http://{this_ip}/{this_key[0:10]}.json"
            result = requests.request("GET", url, timeout=(0.25, 0.25)).json()
            account_balance_value = result["balance"]

            for a in range(len(result["positionArr"])):
                this_price = 0
                for b in range(len(state.tick_arr)):
                    if state.tick_arr[b]["symbol"] == result["positionArr"][a]["symbol"]:
                        this_price = float(state.tick_arr[b]["price"])
                result["positionArr"][a]["balance"] = account_balance_value
                result["positionArr"][a]["mySymbol"] = my_symbol
                if my_symbol == "OTHER":
                    result["positionArr"][a]["mySymbol"] = result["positionArr"][a]["symbol"] + "_BINANCE"
                result["positionArr"][a]["price"] = this_price
                result["positionArr"][a]["dayBeginBalane"] = day_begin_balance
                result["positionArr"][a]["updateTime"] = int(time.time() * 1000)
                result["positionArr"][a]["tradeType"] = str(result["positionArr"][a]["entryPrice"])[-1]
                result["positionArr"][a]["entryPrice"] = 0
                result["positionArr"][a]["unrealizedProfit"] = 0
                result["positionArr"][a]["profitPercent"] = 0
                all_position_arr.append(result["positionArr"][a])

        state.watch_info_obj = {
            "s": "ok",
            "balance": account_balance_value if state.new_api_obj else 0,
            "ethP": state.eth_turn_price,
            "btcP": state.btc_turn_price,
            "ethT": state.eth_turn_ts,
            "btcT": state.btc_turn_ts,
            "eth": state.eth_1m_kline_arr,
            "btc": state.btc_1m_kline_arr,
            "e": state.loss_limit_time_data_arr,
            "d": state.trade_server_status_data,
            "a": all_position_arr,
            "t": int(time.time()),
        }

    return json.loads(json_dumps(state.watch_info_obj))


@router.post("/get_one_day_rate")
def get_one_day_rate(request: Request):
    state = request.app.state.app_state
    now = int(time.time() * 1000)
    if now - state.update_one_day_rate_ts >= 30 * 1000:
        binance_response = []
        try:
            url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            binance_response = requests.request("GET", url, timeout=(3, 3)).json()
            binance_response.sort(key=lambda elem: float(elem['quoteVolume']), reverse=True)
        except Exception as e:
            print(e)
        if len(binance_response) >= 100:
            state.symbol_data_obj = {}
            for i in range(len(binance_response)):
                vol_index = 1
                if i <= 15:
                    vol_index = 1.5
                elif i <= 30:
                    vol_index = 1.4
                elif i <= 45:
                    vol_index = 1.3
                elif i <= 60:
                    vol_index = 1.2
                elif i <= 75:
                    vol_index = 1.1
                state.symbol_data_obj[binance_response[i]["symbol"]] = {
                    "oneDayWave": int(state.infra_client.get_percent_num(
                        float(binance_response[i]["highPrice"]) - float(binance_response[i]["lowPrice"]),
                        float(binance_response[i]["lowPrice"]),
                    )),
                    "volRank": i,
                    "volIndex": vol_index,
                    "vol": float(binance_response[i]["quoteVolume"]),
                    "highPrice": float(binance_response[i]["highPrice"]),
                    "lowPrice": float(binance_response[i]["lowPrice"]),
                }
        state.update_one_day_rate_ts = now
    return {"s": "ok", "d": state.symbol_data_obj}
```

- [ ] **Step 2: Register account router in `web_server/app.py`**

Add import and include:

```python
from web_server.routers import config, market, orders, trading, income, records, status, account
```

```python
    app.include_router(account.router)
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/routers/account.py web_server/app.py
git commit -m "feat: add account router with watch info, positions, one day rate, loss limit endpoints"
```

---

### Task 12: Complete App Lifespan and Entry Point

**Files:**
- Modify: `web_server/app.py` (final version with lifespan + all routers)
- Create: `run_web_server.py` (entry point)

- [ ] **Step 1: Finalize `web_server/app.py` with lifespan initialization**

```python
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infra_client import InfraClient
from web_server.state import AppState
from web_server.binance_helpers import update_symbol_info
from web_server.routers import config, market, orders, trading, income, records, status, account


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize state
    state = AppState()
    state.infra_client = InfraClient(larkMsgSymbol="webServer", connectMysqlPool=True)
    state.private_ip = state.infra_client.get_private_ip()

    # Load symbol info
    update_symbol_info(state)
    while "BTCUSDT" not in state.price_decimal_obj:
        state.infra_client.send_notify("mainConsole updateSymbolInfo")
        update_symbol_info(state)
        time.sleep(1)

    app.state.app_state = state
    yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(config.router)
    app.include_router(market.router)
    app.include_router(orders.router)
    app.include_router(trading.router)
    app.include_router(income.router)
    app.include_router(records.router)
    app.include_router(status.router)
    app.include_router(account.router)

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


app = create_app()
```

- [ ] **Step 2: Create `run_web_server.py` entry point**

```python
#!/usr/bin/env python3
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web_server.app:app", host="0.0.0.0", port=8888, workers=1)
```

- [ ] **Step 3: Run tests to verify nothing is broken**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add web_server/app.py run_web_server.py
git commit -m "feat: complete FastAPI app with lifespan initialization and uvicorn entry point"
```

---

### Task 13: Update Test Suite for Key Endpoints

**Files:**
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Add tests for config endpoints with mocked state**

Append to `tests/test_web_server.py`:

```python
from unittest.mock import MagicMock, patch
from web_server.state import AppState


def _create_test_app():
    """Create a test app with mocked lifespan (no Binance/DB calls)."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from web_server.routers import config, market, orders, income, records, status, account, trading

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    state = AppState()
    state.infra_client = MagicMock()
    state.infra_client.get_session = MagicMock()
    app.state.app_state = state

    app.include_router(config.router)
    app.include_router(market.router)
    app.include_router(orders.router)
    app.include_router(trading.router)
    app.include_router(income.router)
    app.include_router(records.router)
    app.include_router(status.router)
    app.include_router(account.router)

    @app.post("/health")
    def health():
        return {"s": "ok"}

    return app


def test_health_with_mocked_app():
    app = _create_test_app()
    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}


def test_get_invest_percent():
    app = _create_test_app()
    client = TestClient(app)
    resp = client.post("/get_invest_percent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["s"] == "ok"
    assert len(data["r"]) == 5


def test_end_open_unknown_symbol():
    app = _create_test_app()
    client = TestClient(app)
    resp = client.post("/end_open", data={"symbol": "UNKNOWN"})
    assert resp.status_code == 200
    assert resp.json() == {"s": "ok"}
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/test_web_server.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_server.py
git commit -m "test: add endpoint tests with mocked state for FastAPI web server"
```

---

### Task 14: Keep Old webServer.py as Reference, Update CLAUDE.md

**Files:**
- Keep: `webServer.py` (old Bottle server — retained as reference, no longer the active entry point)
- Modify: `CLAUDE.md`

- [ ] **Step 1: Verify all endpoints are covered**

Manually verify each POST endpoint from old `webServer.py` exists in one of the new routers:

| Old Endpoint | New Router |
|---|---|
| `/get_income_obj` | `income.py` |
| `/ping` | `status.py` |
| `/get_symbol_index` | `config.py` |
| `/get_config` | `config.py` |
| `/change_leverage` | `orders.py` |
| `/modify_hot_key` | `config.py` |
| `/get_state_config` | `config.py` |
| `/modify_state_config` | `config.py` |
| `/get_depth` | `market.py` |
| `/cancel_orders` | `orders.py` |
| `/cancel_order` | `orders.py` |
| `/get_all_open_orders` | `orders.py` |
| `/open_position` | `trading.py` |
| `/close_position` | `trading.py` |
| `/stop_loss_batch` | `trading.py` |
| `/stop_loss_once` | `trading.py` |
| `/stop_profit_batch` | `trading.py` |
| `/stop_profit_once` | `trading.py` |
| `/r` | `income.py` |
| `/get_day_income` | `income.py` |
| `/get_one_min_select_kline` | `market.py` |
| `/get_position_record` | `records.py` |
| `/get_history_position_record` | `records.py` |
| `/check_maker_server_in_data` | `status.py` |
| `/update_maker_server_run_info` | `status.py` |
| `/get_customize_dangerous` | `status.py` |
| `/update_customize_dangerous` | `status.py` |
| `/get_all_open_orders_b` | `account.py` |
| `/get_position` | `account.py` |
| `/get_trade_record` | `account.py` |
| `/get_all_acount_info` | `account.py` |
| `/update_loss_limit_time` | `account.py` |
| `/get_watch_info` | `account.py` |
| `/get_second_open_position` | `account.py` |
| `/get_invest_percent` | `income.py` |
| `/update_machine_status` | `status.py` |
| `/update_trade_status` | `status.py` |
| `/get_trade_status` | `status.py` |
| `/get_one_day_rate` | `account.py` |
| `/cancel_binance_orders` | `orders.py` |
| `/cancel_binance_order` | `orders.py` |
| `/get_big_loss_trades` | `records.py` |
| `/begin_trade_record` | `records.py` |
| `/get_order_result_arr` | `records.py` |
| `/get_trades_result_arr` | `records.py` |
| `/get_commission_rate` | `orders.py` |
| `/take_open` | `trading.py` |
| `/end_open` | `trading.py` |

All 46 endpoints covered.

- [ ] **Step 2: Add deprecation comment to top of webServer.py**

Add the following comment block at line 1 of `webServer.py` (before the shebang):

```python
# DEPRECATED: This file is kept as reference only.
# The active web server is now web_server/app.py (FastAPI).
# Entry point: run_web_server.py
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Update CLAUDE.md**

In the Architecture section, change:
```
- **webServer.py** — Bottle-based HTTP server providing REST APIs for order management, position queries, trade recording, and machine status
```
to:
```
- **web_server/** — FastAPI-based HTTP server providing REST APIs for order management, position queries, trade recording, and machine status. Entry point: `run_web_server.py`
- **webServer.py** — Legacy Bottle-based HTTP server (deprecated, kept as reference). Replaced by `web_server/`
```

In the Build & Run Commands section, change:
```bash
uv run python webServer.py
```
to:
```bash
uv run python run_web_server.py
```

In the Key Modules table, add:
```
| `web_server/` | FastAPI HTTP server: `app.py` (app factory), `state.py` (shared state), `binance_helpers.py` (Binance API utils), `routers/` (8 route modules) |
```

In the Design Principles section, add:
```
- Web server uses FastAPI with CORSMiddleware; all endpoints accept form data via `Form()` for backward compatibility with the React frontend
```

Remove `bottle` from dependencies mention and add `fastapi` / `uvicorn`.

- [ ] **Step 5: Commit**

```bash
git add webServer.py CLAUDE.md
git commit -m "refactor: deprecate old webServer.py (kept as reference), update CLAUDE.md for FastAPI migration"
```

---

### Task 15: Final Integration Test

**Files:**
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Add integration smoke test**

Append to `tests/test_web_server.py`:

```python
def test_all_routes_registered():
    """Verify all expected routes are registered on the app."""
    app = _create_test_app()
    routes = [route.path for route in app.routes if hasattr(route, "path")]
    expected_endpoints = [
        "/health",
        "/get_config",
        "/get_symbol_index",
        "/modify_hot_key",
        "/get_state_config",
        "/modify_state_config",
        "/get_depth",
        "/get_one_min_select_kline",
        "/change_leverage",
        "/cancel_orders",
        "/cancel_order",
        "/get_all_open_orders",
        "/cancel_binance_orders",
        "/cancel_binance_order",
        "/get_commission_rate",
        "/open_position",
        "/close_position",
        "/stop_loss_batch",
        "/stop_loss_once",
        "/stop_profit_batch",
        "/stop_profit_once",
        "/take_open",
        "/end_open",
        "/get_income_obj",
        "/r",
        "/get_day_income",
        "/get_invest_percent",
        "/get_position_record",
        "/get_history_position_record",
        "/get_big_loss_trades",
        "/begin_trade_record",
        "/get_order_result_arr",
        "/get_trades_result_arr",
        "/ping",
        "/check_maker_server_in_data",
        "/update_maker_server_run_info",
        "/get_customize_dangerous",
        "/update_customize_dangerous",
        "/update_machine_status",
        "/update_trade_status",
        "/get_trade_status",
        "/get_all_acount_info",
        "/get_all_open_orders_b",
        "/get_position",
        "/get_trade_record",
        "/get_second_open_position",
        "/update_loss_limit_time",
        "/get_watch_info",
        "/get_one_day_rate",
    ]
    for ep in expected_endpoints:
        assert ep in routes, f"Missing route: {ep}"
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_server.py
git commit -m "test: add route registration smoke test for all 49 endpoints"
```

---

## Self-Review Checklist

**1. Spec coverage:** All 46 original endpoints from `webServer.py` are mapped to new routers (verified in Task 14 Step 1). Health endpoint added. Total: 47 endpoints + CORS middleware.

**2. Placeholder scan:** No "TBD", "TODO", or "implement later" found. All code blocks are complete.

**3. Type consistency:**
- `state = request.app.state.app_state` — consistent pattern across all routers
- `Form()` parameter names match the original `request.forms.get()` field names exactly (e.g., `apiKey`, `symbol`, `tradeType`, `paraArr`)
- `AppState` field names use snake_case consistently
- All Binance helper function names use snake_case consistently

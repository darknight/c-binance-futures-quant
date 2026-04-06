# Remove Aliyun ECS Discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all Aliyun ECS API calls (service discovery + server name lookup) with environment variables, removing the `aliyun-python-sdk-core` and `aliyun-python-sdk-ecs` dependencies.

**Architecture:** Add `server_name`, `machine_index`, and service host list fields to `Settings` (pydantic-settings). Remove three ECS methods from `InfraClient`. Update 11 caller files to read from `settings` or `InfraClient.serverName` attribute instead of calling ECS API. Mark `dataPy/uploadDataPy.py` as deprecated.

**Tech Stack:** pydantic-settings, pytest, existing SQLModel/PostgreSQL stack

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `settings.py` | Modify | Add new env vars, remove Aliyun config |
| `infra_client.py` | Modify | Remove ECS methods + imports, read `server_name` from settings |
| `simpleTrade.py` | Modify | Use `InfraClient.serverName` attribute |
| `keyPy/positionRisk.py` | Modify | Use `settings.machine_index` |
| `keyPy/checkTimeoutOrders.py` | Modify | Use `settings.machine_index` + `settings.second_open_hosts` |
| `keyPy/commission.py` | Modify | Use `settings.machine_index` |
| `keyPy/wsPosition.py` | Modify | Use `settings.machine_index` |
| `keyPy/makerStopLoss.py` | Modify | Use `settings.machine_index` |
| `keyPy/getBinancePosition.py` | Modify | Use `settings.machine_index` |
| `dataPy/tickToWs.py` | Modify | Use `settings.machine_index` + `settings.tick_instance_count` |
| `dataPy/specialOneMinKlineToWs.py` | Modify | Use `settings.vol_rate_host_a/b` |
| `dataPy/uploadDataPy.py` | Modify | Mark deprecated, replace ECS calls with settings |
| `.env.example` | Modify | Add new vars, remove Aliyun vars |
| `tests/test_settings.py` | Create | Test new settings fields load correctly |
| `tests/test_infra_client.py` | Create | Test InfraClient init without Aliyun |

---

### Task 1: Add New Environment Variables to Settings

**Files:**
- Modify: `settings.py`
- Modify: `.env.example`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write failing test for new settings fields**

Create `tests/test_settings.py`:

```python
import os
import pytest


def test_settings_has_server_name():
    """server_name field exists and defaults to empty string."""
    os.environ.pop("SERVER_NAME", None)
    # Re-import to pick up fresh defaults
    import importlib
    import settings as settings_mod
    importlib.reload(settings_mod)
    s = settings_mod.Settings(_env_file=None)
    assert s.server_name == ""


def test_settings_has_machine_index():
    """machine_index field exists and defaults to 0."""
    s = _make_settings()
    assert s.machine_index == 0


def test_settings_has_service_host_fields():
    """Service host fields exist with correct defaults."""
    s = _make_settings()
    assert s.tick_instance_count == 1
    assert s.vol_rate_host_a == ""
    assert s.vol_rate_host_b == ""
    assert s.second_open_hosts == "[]"


def test_settings_no_aliyun_fields():
    """Aliyun fields should no longer exist."""
    s = _make_settings()
    assert not hasattr(s, "aliyun_api_key")
    assert not hasattr(s, "aliyun_api_secret")
    assert not hasattr(s, "aliyun_point")


def _make_settings():
    from settings import Settings
    return Settings(_env_file=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_settings.py -v`
Expected: FAIL — `Settings` has no `server_name` field, and still has `aliyun_*` fields.

- [ ] **Step 3: Update settings.py — add new fields, remove Aliyun**

Replace `settings.py` contents with:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://localhost:5432/quant"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # WebSocket Server
    ws_address_a: str = ""
    ws_address_b: str = ""

    # Binance API
    binance_api_arr: str = "[]"  # JSON array: [{"apiKey":"...","apiSecret":"...","apiDescribe":"..."}]

    # Web Server
    web_address: str = ""
    cancel_web_address: str = ""

    # Service Identity (replaces Aliyun ECS getServerName)
    server_name: str = ""
    machine_index: int = 0

    # Service Hosts (replaces Aliyun ECS get_aliyun_private_ip_arr_by_name)
    tick_instance_count: int = 1
    vol_rate_host_a: str = ""
    vol_rate_host_b: str = ""
    second_open_hosts: str = "[]"  # JSON array: ["10.0.0.1","10.0.0.2"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

Key changes:
- Removed `aliyun_api_key`, `aliyun_api_secret`, `aliyun_point`
- Added `server_name`, `machine_index` (identity)
- Added `tick_instance_count`, `vol_rate_host_a`, `vol_rate_host_b`, `second_open_hosts` (service hosts)
- `tick_instance_count` replaces `len(TICK_PRIVATE_IP_ARR)` — the tick sharding only needs total count + own index

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_settings.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Update .env.example**

Replace `.env.example` contents with:

```
DATABASE_URL=postgresql://user:password@localhost:5432/quant

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

BINANCE_API_ARR=[{"apiKey":"your_key","apiSecret":"your_secret","apiDescribe":"main"}]

WS_ADDRESS_A=ws://172.0.0.0:3698
WS_ADDRESS_B=

WEB_ADDRESS=172.0.0.0
CANCEL_WEB_ADDRESS=172.0.0.0

# Service Identity (set per instance at deployment time)
SERVER_NAME=simpleTrade_0
MACHINE_INDEX=0

# Service Hosts (set per instance at deployment time)
TICK_INSTANCE_COUNT=1
VOL_RATE_HOST_A=
VOL_RATE_HOST_B=
SECOND_OPEN_HOSTS=[]
```

- [ ] **Step 6: Commit**

```bash
git add settings.py .env.example tests/test_settings.py
git commit -m "refactor: replace Aliyun config with service identity and host env vars in settings"
```

---

### Task 2: Remove Aliyun ECS Methods from InfraClient

**Files:**
- Modify: `infra_client.py`
- Create: `tests/test_infra_client.py`

- [ ] **Step 1: Write failing test for InfraClient without Aliyun**

Create `tests/test_infra_client.py`:

```python
import os
import pytest


def test_infra_client_has_no_aliyun_imports():
    """infra_client.py should not import any aliyun SDK modules."""
    import inspect
    import infra_client as mod
    source = inspect.getsource(mod)
    assert "aliyunsdkcore" not in source
    assert "aliyunsdkecs" not in source
    assert "AcsClient" not in source
    assert "DescribeInstancesRequest" not in source


def test_infra_client_has_no_ecs_methods():
    """InfraClient should not have ECS discovery methods."""
    from infra_client import InfraClient
    assert not hasattr(InfraClient, "getServerName")
    assert not hasattr(InfraClient, "get_aliyun_private_ip_arr_by_name")
    assert not hasattr(InfraClient, "get_aliyun_public_ip_arr_by_name")


def test_infra_client_reads_server_name_from_settings(monkeypatch):
    """InfraClient.__init__ should read serverName from settings, not ECS API."""
    monkeypatch.setenv("SERVER_NAME", "test_machine_42")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    # Reload settings to pick up env
    import importlib
    import settings as settings_mod
    importlib.reload(settings_mod)
    from infra_client import InfraClient
    client = InfraClient(larkMsgSymbol="test")
    assert client.serverName == "test_machine_42"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_infra_client.py -v`
Expected: FAIL — `aliyunsdkcore` still imported, `getServerName` still exists.

- [ ] **Step 3: Remove Aliyun imports from infra_client.py**

Remove lines 12-16 (the 5 aliyun import lines):

```python
# DELETE these lines:
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkcore.acs_exception.exceptions import ClientException
from aliyunsdkcore.acs_exception.exceptions import ServerException
from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest
```

- [ ] **Step 4: Change serverName init from ECS API to settings**

In `InfraClient.__init__`, change line 50:

```python
# OLD:
self.serverName = self.getServerName()

# NEW:
self.serverName = settings.server_name
```

- [ ] **Step 5: Delete three ECS methods**

Delete the following methods entirely:
- `get_aliyun_public_ip_arr_by_name` (lines 189-212)
- `get_aliyun_private_ip_arr_by_name` (lines 214-237)
- `getServerName` (lines 320-347)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_infra_client.py -v`
Expected: 3 tests PASS.

Also run existing tests to check nothing broke:

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS.

- [ ] **Step 7: Commit**

```bash
git add infra_client.py tests/test_infra_client.py
git commit -m "refactor: remove Aliyun ECS discovery from InfraClient, read server_name from settings"
```

---

### Task 3: Update keyPy/ Services to Use settings.machine_index

All 6 keyPy files follow the same pattern:
```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()
MACHINE_INDEX = int(SERVER_NAME.replace("xxx_",""))
```
Replace with:
```python
from settings import settings
MACHINE_INDEX = settings.machine_index
```

**Files:**
- Modify: `keyPy/positionRisk.py` (lines 23-25)
- Modify: `keyPy/commission.py` (lines 36-38)
- Modify: `keyPy/wsPosition.py` (lines 25-27)
- Modify: `keyPy/makerStopLoss.py` (lines 23-25)
- Modify: `keyPy/getBinancePosition.py` (lines 49-51)
- Modify: `keyPy/checkTimeoutOrders.py` (lines 33-35, plus lines 22-26, 48-75)

Note: `simpleTrade.py` also calls `getServerName()` but only assigns it — never uses the value. It will be handled in Task 4.

- [ ] **Step 1: Update keyPy/positionRisk.py**

Change lines 23-25 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()

MACHINE_INDEX = int(SERVER_NAME.replace("positionRisk_",""))
```

To:

```python
MACHINE_INDEX = settings.machine_index
```

Note: `from settings import settings` already exists at line 16.

- [ ] **Step 2: Update keyPy/commission.py**

Change lines 36-38 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()

MACHINE_INDEX = int(SERVER_NAME.replace("commission_",""))
```

To:

```python
MACHINE_INDEX = settings.machine_index
```

Note: `from settings import settings` already exists at line 16.

- [ ] **Step 3: Update keyPy/wsPosition.py**

Change lines 25-27 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()

MACHINE_INDEX = int(SERVER_NAME.replace("wsPosition_",""))
```

To:

```python
MACHINE_INDEX = settings.machine_index
```

Note: `from settings import settings` already exists at line 20.

- [ ] **Step 4: Update keyPy/makerStopLoss.py**

Change lines 23-25 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()

MACHINE_INDEX = int(SERVER_NAME.replace("makerStopLoss_",""))
```

To:

```python
MACHINE_INDEX = settings.machine_index
```

Note: `from settings import settings` already exists at line 16.

- [ ] **Step 5: Update keyPy/getBinancePosition.py**

Change lines 49-51 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()

MACHINE_INDEX = int(SERVER_NAME.replace("getBinancePosition_",""))
```

To:

```python
MACHINE_INDEX = settings.machine_index
```

Note: `from settings import settings` already exists at line 18.

- [ ] **Step 6: Update keyPy/checkTimeoutOrders.py — remove Aliyun imports**

Delete lines 22-26 (Aliyun SDK imports):

```python
# DELETE these lines:
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from aliyunsdkcore.acs_exception.exceptions import ClientException
from aliyunsdkcore.acs_exception.exceptions import ServerException
from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest
```

- [ ] **Step 7: Update keyPy/checkTimeoutOrders.py — replace getServerName**

Change lines 33-35 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()

MACHINE_INDEX = int(SERVER_NAME.replace("checkTimeoutOrders_",""))
```

To:

```python
MACHINE_INDEX = settings.machine_index
```

Note: `from settings import settings` already exists at line 20.

- [ ] **Step 8: Update keyPy/checkTimeoutOrders.py — replace ECS discovery with env var**

Replace lines 48-75 (the entire `SERVER_IP_ARR` while loop):

```python
# OLD (lines 48-75): ECS API query for "secondOpen" instances with MACHINE_INDEX-based partitioning
SERVER_IP_ARR = []
nowPage =1
emptyReq =False
while  not emptyReq:
    client =  AcsClient(settings.aliyun_api_key, settings.aliyun_api_secret,settings.aliyun_point)
    # ... 28 lines of ECS API code ...
    nowPage = nowPage+1
```

With:

```python
SERVER_IP_ARR = json.loads(settings.second_open_hosts)
```

This single line replaces the entire ECS query + partitioning logic. Each `checkTimeoutOrders` instance's `.env` now directly contains only the trade server IPs it is responsible for.

- [ ] **Step 9: Verify no Aliyun references remain in keyPy/**

Run: `grep -r "aliyunsdkcore\|aliyunsdkecs\|AcsClient\|getServerName\|get_aliyun" keyPy/`
Expected: No output.

- [ ] **Step 10: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 11: Commit**

```bash
git add keyPy/positionRisk.py keyPy/commission.py keyPy/wsPosition.py keyPy/makerStopLoss.py keyPy/getBinancePosition.py keyPy/checkTimeoutOrders.py
git commit -m "refactor: replace Aliyun ECS calls with settings.machine_index in keyPy services"
```

---

### Task 4: Update simpleTrade.py and dataPy/ Files

**Files:**
- Modify: `simpleTrade.py` (line 30)
- Modify: `dataPy/tickToWs.py` (lines 15-18, 103-120)
- Modify: `dataPy/specialOneMinKlineToWs.py` (lines 142, 158)
- Modify: `dataPy/uploadDataPy.py` (lines 14-22, add deprecation)

- [ ] **Step 1: Update simpleTrade.py — remove getServerName call**

Change line 30 from:

```python
SERVER_NAME = FUNCTION_CLIENT.getServerName()
```

To (delete the line entirely, or if SERVER_NAME is used elsewhere for display purposes):

```python
SERVER_NAME = FUNCTION_CLIENT.serverName
```

`simpleTrade.py` calls `getServerName()` at line 30 but grep shows `SERVER_NAME` is never used after that. However, keeping the attribute read is safer in case it's referenced in code we haven't checked. The attribute `serverName` is set in `__init__` from `settings.server_name`.

- [ ] **Step 2: Update dataPy/tickToWs.py — replace IP array with settings**

The tick sharding logic (lines 103-120) uses `TICK_PRIVATE_IP_ARR` for two things:
1. `len(TICK_PRIVATE_IP_ARR)` — total instance count for time-slot calculation
2. Finding self index by matching `privateIP` in the array

Replace lines 15-18:

```python
# OLD:
privateIP = FUNCTION_CLIENT.get_private_ip()

# 此处是通过阿里云命名带有 tickToWs 后，如tickToWs_1,tickToWs_2,调用api进行搜索，如非阿里云需自行替换相关api，或者直接手动写入所有tickToWs服务器的私有地址
TICK_PRIVATE_IP_ARR = FUNCTION_CLIENT.get_aliyun_private_ip_arr_by_name("tickToWs")
```

With:

```python
privateIP = FUNCTION_CLIENT.get_private_ip()
```

Then replace lines 102-120 (the sharding calculation):

```python
# OLD:
nowMillisecondLimitAllArr = []
for i in range(len(TICK_PRIVATE_IP_ARR)):
    nowMillisecondLimitAllArr.append([])

oneServerOneSecondRequestsTime  = 8
requestsLimitTs = 1000/oneServerOneSecondRequestsTime

for a in range(len(TICK_PRIVATE_IP_ARR)):
    for b in range(oneServerOneSecondRequestsTime):
        nowMillisecondLimitAllArr[a].append([int(a*1000/len(TICK_PRIVATE_IP_ARR)/oneServerOneSecondRequestsTime+1000/oneServerOneSecondRequestsTime*b),int((a+1)*1000/len(TICK_PRIVATE_IP_ARR)/oneServerOneSecondRequestsTime+1000/oneServerOneSecondRequestsTime*b)])

nowMillisecondLimitArrIndex = -1
for i in range(len(TICK_PRIVATE_IP_ARR)):
    if privateIP==TICK_PRIVATE_IP_ARR[i]:
        nowMillisecondLimitArrIndex = i

nowMillisecondLimitArr = nowMillisecondLimitAllArr[nowMillisecondLimitArrIndex]
```

With:

```python
TICK_INSTANCE_COUNT = settings.tick_instance_count
TICK_MACHINE_INDEX = settings.machine_index

nowMillisecondLimitAllArr = []
for i in range(TICK_INSTANCE_COUNT):
    nowMillisecondLimitAllArr.append([])

oneServerOneSecondRequestsTime  = 8
requestsLimitTs = 1000/oneServerOneSecondRequestsTime

for a in range(TICK_INSTANCE_COUNT):
    for b in range(oneServerOneSecondRequestsTime):
        nowMillisecondLimitAllArr[a].append([int(a*1000/TICK_INSTANCE_COUNT/oneServerOneSecondRequestsTime+1000/oneServerOneSecondRequestsTime*b),int((a+1)*1000/TICK_INSTANCE_COUNT/oneServerOneSecondRequestsTime+1000/oneServerOneSecondRequestsTime*b)])

nowMillisecondLimitArr = nowMillisecondLimitAllArr[TICK_MACHINE_INDEX]
```

Note: `from settings import settings` already exists at line 6. The sharding math is identical — only the data source changed (env var instead of IP array).

- [ ] **Step 3: Update dataPy/specialOneMinKlineToWs.py — replace ECS calls with settings**

Change line 142 from:

```python
VOL_IP_A = FUNCTION_CLIENT.get_aliyun_private_ip_arr_by_name("volAndRate_1")[0]
```

To:

```python
VOL_IP_A = settings.vol_rate_host_a
```

Change line 158 from:

```python
VOL_IP_B = FUNCTION_CLIENT.get_aliyun_private_ip_arr_by_name("volAndRate_2")[0]
```

To:

```python
VOL_IP_B = settings.vol_rate_host_b
```

Note: Add `from settings import settings` at the top if not already present. Check first.

- [ ] **Step 4: Update dataPy/uploadDataPy.py — mark deprecated, replace ECS calls**

Add deprecation notice at top of file (after shebang):

```python
#!/usr/bin/env python3
# encoding:utf-8
# DEPRECATED: This SSH-based deployment tool is superseded by Dokploy container deployment.
# Kept as reference only. Will be removed in a future cleanup.
```

Replace lines 16-20:

```python
# OLD:
TICK_PRIVATE_IP_ARR = FUNCTION_CLIENT.get_aliyun_private_ip_arr_by_name("tickToWs")

ONE_MIN_PRIVATE_IP_ARR = FUNCTION_CLIENT.get_aliyun_private_ip_arr_by_name("oneMinKlineToWs_")

SPECIAL_ONE_MIN_PRIVATE_IP_ARR = FUNCTION_CLIENT.get_aliyun_private_ip_arr_by_name("specialOneMinKlineToWs_")
```

With:

```python
TICK_PRIVATE_IP_ARR = json.loads(settings.tick_to_ws_hosts) if hasattr(settings, 'tick_to_ws_hosts') else []

ONE_MIN_PRIVATE_IP_ARR = json.loads(settings.one_min_kline_hosts) if hasattr(settings, 'one_min_kline_hosts') else []

SPECIAL_ONE_MIN_PRIVATE_IP_ARR = json.loads(settings.special_kline_hosts) if hasattr(settings, 'special_kline_hosts') else []
```

Wait — these host list fields weren't added to settings in Task 1 because `uploadDataPy.py` is being deprecated. Since this file is deprecated and the hosts are deployment-specific, use a simpler approach:

```python
# DEPRECATED: These IP arrays were previously discovered via Aliyun ECS API.
# Configure manually if you still need to use this script.
TICK_PRIVATE_IP_ARR = []
ONE_MIN_PRIVATE_IP_ARR = []
SPECIAL_ONE_MIN_PRIVATE_IP_ARR = []
```

This avoids adding settings fields only for a deprecated file.

- [ ] **Step 5: Verify no Aliyun references remain in dataPy/ or simpleTrade.py**

Run: `grep -r "aliyunsdkcore\|aliyunsdkecs\|AcsClient\|getServerName\|get_aliyun" dataPy/ simpleTrade.py`
Expected: No output.

- [ ] **Step 6: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add simpleTrade.py dataPy/tickToWs.py dataPy/specialOneMinKlineToWs.py dataPy/uploadDataPy.py
git commit -m "refactor: replace Aliyun ECS calls with env vars in simpleTrade and dataPy services"
```

---

### Task 5: Remove Aliyun SDK Dependencies from pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Remove Aliyun SDK dependencies**

In `pyproject.toml`, remove these two lines from `dependencies`:

```toml
    "aliyun-python-sdk-core",
    "aliyun-python-sdk-ecs",
```

Keep `oss2` for now — it will be removed in Phase 2 (OSS → R2 migration).

- [ ] **Step 2: Run uv lock to regenerate lockfile**

Run: `uv lock`
Expected: Lockfile regenerated without Aliyun SDK packages.

- [ ] **Step 3: Run uv sync to update environment**

Run: `uv sync`
Expected: Aliyun SDK packages removed from virtual environment.

- [ ] **Step 4: Run all tests to verify nothing depends on removed packages**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Final verification — grep for any remaining Aliyun references**

Run: `grep -r "aliyunsdkcore\|aliyunsdkecs\|AcsClient\|DescribeInstances\|get_aliyun\|getServerName" --include="*.py" . --exclude-dir=.venv`

Expected: Only matches in `webServer.py` (deprecated, will be deleted in Phase 3).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: remove aliyun-python-sdk-core and aliyun-python-sdk-ecs dependencies"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update InfraClient description**

In the Architecture section, update the `infra_client.py` bullet point. Change:

```
- **infra_client.py** — `InfraClient` class providing PostgreSQL via SQLAlchemy/SQLModel, WebSocket (A/B channels), Telegram notifications, Aliyun ECS discovery, Aliyun OSS, and Binance order routing
```

To:

```
- **infra_client.py** — `InfraClient` class providing PostgreSQL via SQLAlchemy/SQLModel, WebSocket (A/B channels), Telegram notifications, Aliyun OSS, and Binance order routing
```

(Only remove "Aliyun ECS discovery" — OSS removal is Phase 2.)

- [ ] **Step 2: Update dataPy/ description**

In the Key Modules table, update the `dataPy/` row. Change:

```
| `dataPy/` | Distributed data collectors (tick, kline) that feed into wsServer. Use Aliyun server naming conventions (e.g., `tickToWs_1`) for auto-discovery |
```

To:

```
| `dataPy/` | Distributed data collectors (tick, kline) that feed into wsServer. Each instance identified by `SERVER_NAME` and `MACHINE_INDEX` env vars |
```

- [ ] **Step 3: Update Important Notes — remove ECS naming convention note**

In the Important Notes section, change:

```
- Data collectors use Aliyun ECS naming conventions for auto-discovery (e.g., `tickToWs_1`, `tickToWs_2`). The `get_aliyun_private_ip_arr_by_name()` function in `infra_client.py` handles this
```

To:

```
- Data collectors are configured via environment variables (`SERVER_NAME`, `MACHINE_INDEX`, `TICK_INSTANCE_COUNT`) for multi-instance sharding
```

- [ ] **Step 4: Run all tests one final time**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect Aliyun ECS removal"
```

---

## Verification Checklist (end-to-end)

After all tasks are complete:

1. **No Aliyun SDK references in active code:**
   ```bash
   grep -r "aliyunsdkcore\|aliyunsdkecs\|AcsClient\|DescribeInstances\|get_aliyun\|getServerName" --include="*.py" . --exclude-dir=.venv
   ```
   Expected: Only matches in `webServer.py` (deprecated).

2. **All tests pass:**
   ```bash
   uv run pytest tests/ -v
   ```

3. **Settings load correctly:**
   ```bash
   uv run python -c "from settings import settings; print(settings.model_dump())"
   ```
   Expected: Shows `server_name`, `machine_index`, no `aliyun_*` fields.

4. **InfraClient initializes without Aliyun:**
   ```bash
   SERVER_NAME=test_0 MACHINE_INDEX=0 DATABASE_URL=sqlite:// uv run python -c "from infra_client import InfraClient; c = InfraClient(larkMsgSymbol='test'); print(c.serverName)"
   ```
   Expected: Prints `test_0`.

5. **No Aliyun packages installed:**
   ```bash
   uv run pip list | grep -i aliyun
   ```
   Expected: No output.

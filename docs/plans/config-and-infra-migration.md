# 配置管理 + 基础设施迁移计划

> **Status: COMPLETED** (Step 1-6 全部完成，commit 45d7cac)

## Context

当前项目配置硬编码在 `config.py`，包含数据库密码、飞书密钥、阿里云凭证等敏感信息。项目深度依赖阿里云（ECS 自动发现 + OSS 对象存储）和飞书通知。用户要迁移到 DigitalOcean + Dokploy 部署，需要：

1. `config.py` → `.env` + `pydantic-settings`（配置管理现代化）
2. 飞书 → Telegram Bot（完全移除飞书代码和配置）
3. `commonFunction.py` → `infra_client.py`（重命名，`FunctionClient` → `InfraClient`）
4. MySQL → PostgreSQL（数据库迁移，后续独立任务）
5. 阿里云依赖评估（ECS 发现 + OSS，后续独立任务）

本计划覆盖 **1、2、3**。数据库迁移和阿里云替换影响面更大，单独立计划。

## 影响分析

### config.py 引用链
```
config.py
  └→ commonFunction.py (FunctionClient.__init__)  ← 核心汇聚点
       └→ 22 个业务文件通过 FunctionClient 间接使用配置
```

**直接引用 config 变量的文件：**
- `commonFunction.py` — MYSQL_CONFIG, FEISHU_*, WS_ADDRESS_*, ALIYUN_*, 全部变量
- `checkTimeoutOrders.py` — ALIYUN_API_KEY, ALIYUN_API_SECRET, ALIYUN_POINT
- 其余 20 个文件 — 只 `from config import *` 但通过 FunctionClient 间接使用

### 飞书调用链
```
commonFunction.py
  ├─ send_notify(content)          # 行 65-99
  └─ send_notify_limit_one_min(content)  # 行 101-105，60秒限流

调用方（发送告警/状态更新）：
  ├─ commonFunction.py 自身  — MySQL 连接失败、WS 连接失败
  ├─ keyPy/positionRisk.py  — 持仓风控告警（7处调用）
  ├─ keyPy/checkTimeoutOrders.py  — 超时订单告警（4+处调用）
  ├─ afterTrade/positionRecord.py  — 持仓记录异常（2处）
  ├─ afterTrade/tradesUpdate.py  — 交易记录异常（1处）
  └─ afterTrade/webOssUpdate.py  — OSS 更新异常（3处）
```

### commonFunction.py → infra_client.py 重命名
```
引用 commonFunction 的文件（import FunctionClient 或从 commonFunction 导入工具函数）：
  ├─ webServer.py
  ├─ simpleTrade.py
  ├─ keyPy/positionRisk.py
  ├─ keyPy/checkTimeoutOrders.py
  ├─ keyPy/commission.py
  ├─ keyPy/makerStopLoss.py
  ├─ keyPy/getBinancePosition.py
  ├─ keyPy/wsPosition.py
  ├─ keyPy/binanceTradesRecord.py
  ├─ keyPy/binanceOrdersRecord.py
  ├─ dataPy/tickToWs.py
  ├─ dataPy/oneMinKlineToWs.py
  ├─ dataPy/specialOneMinKlineToWs.py
  ├─ dataPy/uploadDataPy.py
  ├─ dataPy/useData.py
  ├─ afterTrade/webOssUpdate.py
  ├─ afterTrade/tradesUpdate.py
  ├─ afterTrade/positionRecord.py
  └─ updateSymbol/updateTradeSymbol.py
```

## 实施步骤

### Step 1: 引入 pydantic-settings，创建 settings.py

**新建 `settings.py`：**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_host: str = "localhost"
    database_port: int = 3306
    database_user: str = ""
    database_password: str = ""
    database_name: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # WebSocket Server
    ws_address_a: str = ""
    ws_address_b: str = ""

    # Aliyun (保留，后续迁移时再移除)
    aliyun_api_key: str = ""
    aliyun_api_secret: str = ""
    aliyun_point: str = "ap-northeast-1"

    # Web Server
    web_address: str = ""
    cancel_web_address: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

settings = Settings()
```

**新建 `.env.example`（提交到 git，作为模板）：**
```
DATABASE_HOST=localhost
DATABASE_PORT=3306
DATABASE_USER=root
DATABASE_PASSWORD=
DATABASE_NAME=quant

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

WS_ADDRESS_A=ws://172.0.0.0:3698
WS_ADDRESS_B=

ALIYUN_API_KEY=
ALIYUN_API_SECRET=
ALIYUN_POINT=ap-northeast-1

WEB_ADDRESS=172.0.0.0
CANCEL_WEB_ADDRESS=172.0.0.0
```

**添加依赖：**
- `uv add pydantic-settings`

**更新 `.gitignore`：**
- 添加 `.env`

### Step 2: 重命名 commonFunction.py → infra_client.py，FunctionClient → InfraClient

**文件重命名：**
- `commonFunction.py` → `infra_client.py`

**类重命名：**
- `FunctionClient` → `InfraClient`

**直接更新所有引用**，不保留兼容垫片。22 个文件的 import 在 Step 5 中一并修改。

### Step 3: 移除飞书，实现 Telegram 通知

**完全删除飞书相关代码：**
- 删除 `send_notify` 方法中的飞书 API 调用逻辑
- 删除 `__init__` 中的 `self.larkAppID` 和 `self.larkAppSecret`
- 删除 `from config import *` 中对 `FEISHU_APP_ID`、`FEISHU_APP_SECRET` 的依赖

**将 `send_notify` 方法体替换为 Telegram 实现（保留方法名，调用方零改动）：**
```python
def send_notify(self, content):
    """发送通知消息（通过 Telegram）"""
    if not self._telegram_bot_token or not self._telegram_chat_id:
        return
    url = f"https://api.telegram.org/bot{self._telegram_bot_token}/sendMessage"
    data = {
        "chat_id": self._telegram_chat_id,
        "text": f"【{self.msgSymbol}】{content}【{self.privateIP}】",
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception:
        pass

def send_notify_limit_one_min(self, content):
    """发送通知消息，60秒限流"""
    now = int(time.time())
    if now - self._last_notify_ts > 60:
        self._last_notify_ts = now
        self.send_notify(content)
```

**22 个调用方需同步修改：** 将所有 `send_notify` / `send_notify_limit_one_min` 的调用从旧方法名 (`send_lark_msg` / `send_lark_msg_limit_one_min`) 更新过来。可通过全局搜索替换完成。

### Step 4: 修改 InfraClient.__init__ 使用 settings

```python
from settings import settings

class InfraClient:
    def __init__(self, **params):
        self.msgSymbol = params.get("larkMsgSymbol", "")  # 保留参数名兼容调用方

        # Telegram
        self._telegram_bot_token = settings.telegram_bot_token
        self._telegram_chat_id = settings.telegram_chat_id

        # MySQL
        mysql_config = {
            "host": settings.database_host,
            "port": settings.database_port,
            "user": settings.database_user,
            "password": settings.database_password,
            "database": settings.database_name,
            "charset": "utf8mb4",
        }
        self.mysqlConnect = {}
        if params.get("connectMysql"):
            self.mysqlConnect = mysql.connector.connect(**mysql_config)
        self._mysql_config = mysql_config  # 保存用于重连

        self.mysqlPoolConnect = {}
        if params.get("connectMysqlPool"):
            self.mysqlPoolConnect = MySQLConnectionPool(
                pool_name="mypool", pool_size=30, **mysql_config
            )

        # WebSocket
        self.wsConnectionA = {}
        if params.get("connectWsA"):
            self.wsConnectionA = create_connection(settings.ws_address_a)
        self.wsConnectionB = {}
        if params.get("connectWsB"):
            self.wsConnectionB = create_connection(settings.ws_address_b)

        # ... 其余初始化保持不变，变量引用改为 settings.xxx ...
```

**MySQL 重连处也要改：** 将所有 `mysql.connector.connect(**MYSQL_CONFIG)` 替换为 `mysql.connector.connect(**self._mysql_config)`，消除对全局 config 的依赖。

**WebSocket 重连也要改：** 将 `create_connection(WS_ADDRESS_A)` 替换为 `create_connection(settings.ws_address_a)`。

### Step 5: 修改所有业务文件的 import

22 个文件需要一次性修改：

```python
# 旧
from commonFunction import FunctionClient
from config import *
# ...
fc = FunctionClient(...)

# 新
from infra_client import InfraClient
# ...
fc = InfraClient(...)
```

对于直接使用 config 变量的文件（如 `checkTimeoutOrders.py` 使用 `ALIYUN_*`）：
```python
# 旧
from config import *
client = AcsClient(ALIYUN_API_KEY, ALIYUN_API_SECRET, ALIYUN_POINT)

# 新
from settings import settings
client = AcsClient(settings.aliyun_api_key, settings.aliyun_api_secret, settings.aliyun_point)
```

### Step 6: 清理

- 删除 `commonFunction.py`（已重命名为 infra_client.py，无兼容垫片）
- 删除 `config.py`（已被 settings.py + .env 替代）

## 需要修改的文件清单

| 文件 | 修改内容 |
|------|---------|
| **新建** `settings.py` | pydantic-settings 配置类 |
| **新建** `.env.example` | 配置模板 |
| **新建** `infra_client.py` | 由 commonFunction.py 重命名而来 |
| `.gitignore` | 添加 `.env` |
| **删除** `commonFunction.py` | 已重命名为 infra_client.py |
| **删除** `config.py` | 已被 settings.py + .env 替代 |
| `pyproject.toml` | 添加 pydantic-settings 依赖 |
| 22 个业务文件 | import 语句更新：`commonFunction` → `infra_client`，`FunctionClient` → `InfraClient`，`config` → `settings` |

## 验证

1. `uv run python -c "from settings import settings; print(settings.model_dump())"` — 配置加载成功
2. `uv run python -c "from infra_client import InfraClient"` — 新模块可导入
3. 用 Telegram BotFather 创建测试 bot，验证 `send_notify` 通过 Telegram 发送成功
4. 确认 `.env` 不在 git 跟踪中
5. `grep -r "commonFunction\|FunctionClient\|from config import\|FEISHU" --include="*.py" .` — 确认无残留引用
6. 各模块 import 无报错

## 后续独立任务（不在本计划范围）

1. **MySQL → PostgreSQL**：修改 infra_client.py 的数据库连接和 SQL 语法
2. **阿里云 ECS 发现 → 静态配置/DNS**：改用环境变量配置服务器 IP
3. **阿里云 OSS → DigitalOcean Spaces**：API 兼容 S3，换 endpoint + bucket name
4. **方法重命名**：将 `send_notify` / `send_notify_limit_one_min` 改为更通用的名字（如已完成则跳过）

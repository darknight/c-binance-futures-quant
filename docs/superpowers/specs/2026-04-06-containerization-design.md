# 容器化设计 (Docker + Dokploy)

## Context

Phase 1-3 已完成去阿里云依赖。所有配置通过环境变量管理，存储使用 Cloudflare R2。现在需要容器化，为 DigitalOcean + Dokploy 部署做准备。

## 目标

- 为所有 Python 服务和 Rust ws-server 创建 Docker 镜像
- 用 docker-compose.yml 编排全部 ~17 个服务（含 PostgreSQL）
- Docker 内部 DNS 替代手动 IP 配置
- 先支持单服务器部署，后续可扩展到多服务器

## 新增文件

```
Dockerfile                  # 所有 Python 服务共用
ws-server/Dockerfile        # Rust ws-server 多阶段构建
docker-compose.yml          # 全部服务编排
```

## Dockerfile（Python 服务）

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
```

所有 Python 服务共用此镜像，通过 docker-compose 的 `command` 指定不同入口。

## ws-server/Dockerfile（Rust 服务）

```dockerfile
FROM rust:1-slim AS builder
WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
COPY --from=builder /app/target/release/ws-server /usr/local/bin/
EXPOSE 3698
CMD ["ws-server", "--port", "3698", "--log-level", "info"]
```

多阶段构建：编译阶段用完整 Rust 工具链，运行阶段只保留 binary。

## docker-compose.yml 服务编排

### 基础设施层

| 服务 | 镜像 | 端口 | 持久化 |
|------|------|------|--------|
| `postgres` | postgres:16-alpine | 5432 | volume `pgdata` |
| `ws-server` | 本地构建 (ws-server/Dockerfile) | 3698 | - |

### 应用层

| 服务 | command | 端口 | depends_on |
|------|---------|------|------------|
| `web-server` | `uv run python run_web_server.py` | 8888 | postgres, ws-server |
| `tick-to-ws` | `uv run python dataPy/tickToWs.py` | - | postgres, ws-server |
| `one-min-kline` | `uv run python dataPy/oneMinKlineToWs.py` | - | postgres, ws-server |
| `special-kline` | `uv run python dataPy/specialOneMinKlineToWs.py` | - | postgres, ws-server |
| `simple-trade` | `uv run python simpleTrade.py` | - | postgres, ws-server, web-server |
| `get-position` | `uv run python keyPy/getBinancePosition.py` | - | postgres, ws-server |
| `check-timeout` | `uv run python keyPy/checkTimeoutOrders.py` | - | postgres |
| `commission` | `uv run python keyPy/commission.py` | - | postgres |
| `ws-position` | `uv run python keyPy/wsPosition.py` | - | postgres |
| `maker-stop-loss` | `uv run python keyPy/makerStopLoss.py` | - | postgres |
| `position-risk` | `uv run python keyPy/positionRisk.py` | - | postgres |
| `web-oss-update` | `uv run python afterTrade/webOssUpdate.py` | - | postgres |
| `position-record` | `uv run python afterTrade/positionRecord.py` | - | postgres |
| `trades-update` | `uv run python afterTrade/tradesUpdate.py` | - | postgres |

### 网络

所有服务在默认 compose network 中，用服务名互访：

| 环境变量 | 容器化后的值 |
|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://quant:quant@postgres:5432/quant` |
| `WS_ADDRESS_A` | `ws://ws-server:3698` |
| `WEB_ADDRESS` | `web-server` |
| `CANCEL_WEB_ADDRESS` | `web-server` |

### 环境变量

- `env_file: .env` 加载共享配置
- 每个服务用 `environment` 覆盖个性化配置（`SERVER_NAME`、`MACHINE_INDEX`）
- `.env` 不提交 git

### 数据持久化

```yaml
volumes:
  pgdata:
```

### 启动顺序

`depends_on` + postgres `healthcheck`（`pg_isready`）确保依赖顺序：
1. postgres（健康检查通过）
2. ws-server
3. web-server
4. 其余服务并行启动

### Alembic 迁移

在 `web-server` 启动前或作为单独 init 容器运行 `uv run alembic upgrade head`。

## .dockerignore

```
.venv/
.env
.git/
__pycache__/
*.pyc
react-front/node_modules/
ws-server/target/
```

## 验证

1. `docker compose build` 成功
2. `docker compose up postgres ws-server` → 等待健康检查
3. `docker compose up web-server` → `curl http://localhost:8888/health` 返回 ok
4. `docker compose up` 全部启动，查看日志确认无崩溃
5. 前端访问 R2 数据确认端到端流程

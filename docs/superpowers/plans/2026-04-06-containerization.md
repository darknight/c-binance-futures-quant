# Containerization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create Docker images and docker-compose.yml to containerize all services (PostgreSQL, Rust ws-server, 14 Python services) for Dokploy deployment.

**Architecture:** Single Python Dockerfile shared by all Python services via different `command` entries. Rust ws-server uses multi-stage build. docker-compose.yml orchestrates everything with Docker internal DNS for service discovery. Environment variables loaded from `.env` file.

**Tech Stack:** Docker, docker-compose, python:3.14-slim, rust:1-slim, postgres:16-alpine, uv

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `Dockerfile` | Create | Python services image (shared) |
| `ws-server/Dockerfile` | Create | Rust ws-server multi-stage build |
| `.dockerignore` | Create | Exclude unnecessary files from build context |
| `docker-compose.yml` | Create | Full service orchestration |
| `.env.example` | Modify | Add docker-specific example values |
| `CLAUDE.md` | Modify | Add Docker build/run commands |

---

### Task 1: Create .dockerignore

**Files:**
- Create: `.dockerignore`

- [ ] **Step 1: Create .dockerignore**

```
.venv/
.env
.git/
__pycache__/
*.pyc
*.pyo
react-front/node_modules/
ws-server/target/
.claude/
docs/
tests/
*.md
!pyproject.toml
```

- [ ] **Step 2: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for Docker builds"
```

---

### Task 2: Create Python Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.14-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Default command (overridden by docker-compose per service)
CMD ["uv", "run", "python", "run_web_server.py"]
```

- [ ] **Step 2: Verify the image builds**

Run: `docker build -t quant-python .`
Expected: Build succeeds, image created.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: add Python Dockerfile for all Python services"
```

---

### Task 3: Create Rust ws-server Dockerfile

**Files:**
- Create: `ws-server/Dockerfile`

- [ ] **Step 1: Create ws-server/Dockerfile**

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

- [ ] **Step 2: Verify the image builds**

Run: `docker build -t quant-ws-server ws-server/`
Expected: Build succeeds (may take a few minutes for Rust compilation).

- [ ] **Step 3: Commit**

```bash
git add ws-server/Dockerfile
git commit -m "feat: add Rust ws-server Dockerfile with multi-stage build"
```

---

### Task 4: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
services:
  # === Infrastructure ===

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: quant
      POSTGRES_PASSWORD: quant
      POSTGRES_DB: quant
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U quant"]
      interval: 5s
      timeout: 3s
      retries: 5

  ws-server:
    build:
      context: ./ws-server
      dockerfile: Dockerfile
    ports:
      - "3698:3698"
    restart: unless-stopped

  # === API ===

  web-server:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python run_web_server.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
      WEB_ADDRESS: web-server
      CANCEL_WEB_ADDRESS: web-server
    ports:
      - "8888:8888"
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped

  # === Data Collectors ===

  tick-to-ws:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python dataPy/tickToWs.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
      SERVER_NAME: tickToWs_0
      MACHINE_INDEX: "0"
      TICK_INSTANCE_COUNT: "1"
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped

  one-min-kline:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python dataPy/oneMinKlineToWs.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
      SERVER_NAME: oneMinKlineToWs_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped

  special-kline:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python dataPy/specialOneMinKlineToWs.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
      SERVER_NAME: specialOneMinKlineToWs_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped

  # === Trading ===

  simple-trade:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python simpleTrade.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
      WEB_ADDRESS: web-server
      CANCEL_WEB_ADDRESS: web-server
      SERVER_NAME: secondOpen_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
      web-server:
        condition: service_started
    restart: unless-stopped

  # === Risk Control ===

  get-position:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python keyPy/getBinancePosition.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
      SERVER_NAME: getBinancePosition_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped

  check-timeout:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python keyPy/checkTimeoutOrders.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WEB_ADDRESS: web-server
      CANCEL_WEB_ADDRESS: web-server
      SERVER_NAME: checkTimeoutOrders_0
      MACHINE_INDEX: "0"
      SECOND_OPEN_HOSTS: '["simple-trade"]'
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  commission:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python keyPy/commission.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      SERVER_NAME: commission_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  ws-position:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python keyPy/wsPosition.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      SERVER_NAME: wsPosition_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  maker-stop-loss:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python keyPy/makerStopLoss.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      SERVER_NAME: makerStopLoss_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  position-risk:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python keyPy/positionRisk.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      SERVER_NAME: positionRisk_0
      MACHINE_INDEX: "0"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  # === Post-Trade ===

  web-oss-update:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python afterTrade/webOssUpdate.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  position-record:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python afterTrade/positionRecord.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
      WS_ADDRESS_A: ws://ws-server:3698
    depends_on:
      postgres:
        condition: service_healthy
      ws-server:
        condition: service_started
    restart: unless-stopped

  trades-update:
    build:
      context: .
      dockerfile: Dockerfile
    command: uv run python afterTrade/tradesUpdate.py
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg://quant:quant@postgres:5432/quant
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
```

- [ ] **Step 2: Verify compose config is valid**

Run: `docker compose config --quiet`
Expected: No errors (exits 0).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose.yml with all 16 services"
```

---

### Task 5: Update .env.example and CLAUDE.md

**Files:**
- Modify: `.env.example`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update .env.example with Docker-friendly example values**

Add a comment block at the top of `.env.example`:

```
# === Docker Compose Defaults ===
# When using docker-compose, DATABASE_URL, WS_ADDRESS_A, WEB_ADDRESS,
# and CANCEL_WEB_ADDRESS are overridden per-service in docker-compose.yml.
# The values below are for local (non-Docker) development.
```

- [ ] **Step 2: Add Docker section to CLAUDE.md**

In CLAUDE.md, after the "React Frontend" section, add:

```markdown
### Docker (all services)
```bash
# Build all images
docker compose build

# Start infrastructure first
docker compose up -d postgres ws-server

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
```

- [ ] **Step 3: Run existing tests to make sure nothing broke**

Run: `uv run pytest tests/ -v`
Expected: All 150 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add .env.example CLAUDE.md
git commit -m "docs: add Docker build/run commands to CLAUDE.md and .env.example"
```

---

### Task 6: Build and Smoke Test

This task verifies everything works end-to-end. No code changes — only verification commands.

- [ ] **Step 1: Build all images**

Run: `docker compose build`
Expected: All images build successfully.

- [ ] **Step 2: Start PostgreSQL and verify health**

Run: `docker compose up -d postgres`
Then: `docker compose ps`
Expected: postgres shows "healthy".

- [ ] **Step 3: Start ws-server**

Run: `docker compose up -d ws-server`
Then: `docker compose logs ws-server`
Expected: Logs show server listening on port 3698.

- [ ] **Step 4: Run Alembic migrations**

Run: `docker compose run --rm web-server uv run alembic upgrade head`
Expected: Migrations applied successfully.

- [ ] **Step 5: Start web-server and test health endpoint**

Run: `docker compose up -d web-server`
Then: `curl http://localhost:8888/health`
Expected: `{"s":"ok"}`

- [ ] **Step 6: Start all remaining services**

Run: `docker compose up -d`
Then: `docker compose ps`
Expected: All 16 services running (postgres healthy, others "Up").

- [ ] **Step 7: Check for crashes**

Run: `docker compose ps --format json | python3 -c "import sys,json; services=json.loads(sys.stdin.read()); [print(f'WARN: {s[\"Name\"]} exited') for s in services if 'Exit' in s.get('State','')]"`
Expected: No warnings. (Some services may exit if Binance API keys are not configured — that's expected.)

- [ ] **Step 8: Clean up**

Run: `docker compose down`
Expected: All containers stopped and removed.

---

## Verification Checklist (end-to-end)

After all tasks are complete:

1. **Docker images build:**
   ```bash
   docker compose build
   ```

2. **Compose config valid:**
   ```bash
   docker compose config --quiet
   ```

3. **Health endpoint works:**
   ```bash
   docker compose up -d postgres ws-server web-server
   curl http://localhost:8888/health
   # {"s":"ok"}
   docker compose down
   ```

4. **All existing tests still pass:**
   ```bash
   uv run pytest tests/ -v
   ```

5. **No secrets in committed files:**
   ```bash
   grep -r "quant\.illuminating\|apiKey.*[A-Za-z0-9]{20}" --include="*.yml" --include="*.yaml" . --exclude-dir=.venv
   ```
   Expected: No output.

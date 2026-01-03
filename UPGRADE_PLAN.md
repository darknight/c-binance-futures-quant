# 项目基础架构升级计划

> 本文档描述了将 c-binance-futures-quant 项目从旧版本依赖升级到现代技术栈的完整计划。

---

## 一、升级概览

### 当前状态 vs 目标状态

| 组件 | 当前版本 | 目标版本 | 优先级 |
|-----|---------|---------|-------|
| **Python** | 3.10.6 | 3.12.x / 3.13.x | P0 |
| **包管理器** | 无（直接 import） | UV | P0 |
| **React** | 16.8.4 | 18.3.x | P0 |
| **构建工具** | Webpack 4 + Babel 6 | Vite 6.x | P0 |
| **UI 框架** | Antd 4.24.2 | Antd 5.x | P1 |
| **状态管理** | Mobx 5.9.4 | Mobx 6.x 或 Zustand | P1 |

---

## 二、Python 后端升级

### 2.1 Python 版本升级

**当前**: Python 3.10.6
**目标**: Python 3.12.x 或 3.13.x

#### 升级收益
- 性能提升 10-60%（特别是 3.11+ 的解释器优化）
- 更好的错误消息和调试体验
- 新语法特性：`match-case`、类型提示增强、`Self` 类型等
- 更好的异步支持

#### 兼容性检查
需要验证以下代码模式的兼容性：
- `commonFunction.py` 中的时间处理逻辑
- `binance_f/` 模块中的 WebSocket 实现
- 阿里云 SDK 的兼容性

### 2.2 切换到 UV 包管理器

**当前**: 无正式包管理（依赖通过 `import` 隐式管理）
**目标**: UV (Astral 出品的超快 Python 包管理器)

#### 为什么选择 UV
- 比 pip 快 10-100 倍
- 内置虚拟环境管理
- 兼容 `pyproject.toml` 和 `requirements.txt`
- 可替代 pip、pip-tools、pipx、poetry、pyenv、virtualenv

#### 实施步骤

```bash
# 1. 安装 UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 初始化项目
cd c-binance-futures-quant
uv init

# 3. 创建虚拟环境
uv venv

# 4. 激活虚拟环境
source .venv/bin/activate

# 5. 安装依赖
uv add <package>
```

#### 创建 pyproject.toml

```toml
[project]
name = "binance-futures-quant"
version = "2.0.0"
description = "Binance Futures Quantitative Trading System"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    # 数据库
    "mysql-connector-python>=9.0.0",

    # HTTP 客户端 (推荐替换 requests)
    "httpx>=0.28.0",

    # WebSocket
    "websockets>=14.0",

    # 阿里云 SDK
    "alibabacloud-ecs20140526>=3.0.0",
    "oss2>=2.19.0",

    # Web 框架 (推荐替换 bottle)
    "fastapi>=0.115.0",
    "uvicorn>=0.34.0",

    # 数据处理
    "numpy>=2.0.0",
    "pydantic>=2.10.0",

    # 工具
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "ruff>=0.8.0",
]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]

[tool.mypy]
python_version = "3.12"
strict = true
```

### 2.3 Python 依赖升级详情

#### 核心依赖变更

| 当前依赖 | 当前版本 | 推荐替代 | 目标版本 | 说明 |
|---------|---------|---------|---------|-----|
| `mysql.connector` | 未知 | `mysql-connector-python` | 9.x | 官方维护，性能更好 |
| `requests` | 未知 | `httpx` | 0.28.x | 支持 async/await，HTTP/2 |
| `websocket-client` | 未知 | `websockets` | 14.x | 现代异步 WebSocket 库 |
| `bottle` | 未知 | `FastAPI` | 0.115.x | 现代异步框架，自带类型验证 |
| `aliyunsdkcore` | 未知 | `alibabacloud-*-sdk` | 3.x | 阿里云官方 V2 SDK |
| `oss2` | 未知 | `oss2` | 2.19.x | 升级到最新版 |

#### 推荐新增依赖

| 依赖 | 版本 | 用途 |
|-----|------|-----|
| `pydantic` | 2.10.x | 数据验证和序列化 |
| `python-dotenv` | 1.0.x | 环境变量管理 |
| `structlog` | 24.x | 结构化日志 |
| `tenacity` | 9.x | 重试机制 |
| `orjson` | 3.x | 高性能 JSON 序列化 |

### 2.4 代码迁移指南

#### 2.4.1 HTTP 客户端迁移 (requests → httpx)

```python
# 旧代码 (requests)
import requests
response = requests.request("POST", url, timeout=3, headers=header, data=json.dumps(body))
result = response.json()

# 新代码 (httpx)
import httpx
async with httpx.AsyncClient() as client:
    response = await client.post(url, headers=header, json=body, timeout=3.0)
    result = response.json()
```

#### 2.4.2 WebSocket 迁移 (websocket-client → websockets)

```python
# 旧代码 (websocket-client)
from websocket import create_connection
ws = create_connection(WS_ADDRESS_A)
ws.send(msg)
result = ws.recv()

# 新代码 (websockets)
import websockets
async with websockets.connect(WS_ADDRESS_A) as ws:
    await ws.send(msg)
    result = await ws.recv()
```

#### 2.4.3 Web 框架迁移 (bottle → FastAPI)

```python
# 旧代码 (bottle)
from bottle import Bottle, request
app = Bottle()

@app.route('/update_machine_status', method='POST')
def update_machine_status():
    privateIP = request.forms.get('privateIP')
    # ...

# 新代码 (FastAPI)
from fastapi import FastAPI, Form

app = FastAPI()

@app.post("/update_machine_status")
async def update_machine_status(privateIP: str = Form(...)):
    # ...
```

#### 2.4.4 配置管理迁移

```python
# 旧代码 (config.py 硬编码)
MYSQL_CONFIG = {
    'host': '',
    'port': 3306,
    # ...
}

# 新代码 (python-dotenv + pydantic)
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mysql_host: str
    mysql_port: int = 3306
    mysql_user: str
    mysql_password: str
    mysql_database: str

    feishu_app_id: str
    feishu_app_secret: str

    ws_address_a: str
    ws_address_b: str

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 三、前端升级

### 3.1 构建工具迁移 (Webpack → Vite)

**当前**: Webpack 4 + Babel 6/7 + HappyPack
**目标**: Vite 6.x

#### 为什么选择 Vite
- 开发服务器启动速度快 10-100 倍
- 热更新几乎即时
- 原生 ESM 支持
- 内置 TypeScript 支持
- 更简洁的配置

#### 创建 vite.config.ts

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@config': path.resolve(__dirname, 'config'),
      '@components': path.resolve(__dirname, 'src/work/components'),
      '@images': path.resolve(__dirname, 'src/work/images'),
      '@style': path.resolve(__dirname, 'src/work/style'),
      '@server': path.resolve(__dirname, 'src/work/server'),
      '@common': path.resolve(__dirname, 'src/work/common'),
      '@store': path.resolve(__dirname, 'src/work/store'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8888',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          antd: ['antd', '@ant-design/icons'],
          charts: ['echarts', 'echarts-for-react'],
        },
      },
    },
  },
})
```

### 3.2 React 版本升级

**当前**: React 16.8.4
**目标**: React 18.3.x

#### 主要变更
- 新的并发特性 (Concurrent Features)
- 自动批处理 (Automatic Batching)
- Transitions API
- 新的 Suspense 功能
- 新的客户端和服务器渲染 API

#### 迁移步骤

```javascript
// 旧代码 (React 16)
import ReactDOM from 'react-dom';
ReactDOM.render(<App />, document.getElementById('root'));

// 新代码 (React 18)
import { createRoot } from 'react-dom/client';
const root = createRoot(document.getElementById('root'));
root.render(<App />);
```

### 3.3 前端依赖升级详情

#### package.json 升级

```json
{
  "name": "binance-futures-quant-frontend",
  "version": "2.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0"
  },
  "dependencies": {
    "@ant-design/charts": "^2.2.0",
    "@ant-design/icons": "^5.5.0",
    "antd": "^5.22.0",
    "axios": "^1.7.0",
    "dayjs": "^1.11.0",
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.28.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@typescript-eslint/eslint-plugin": "^8.15.0",
    "@typescript-eslint/parser": "^8.15.0",
    "@vitejs/plugin-react": "^4.3.0",
    "eslint": "^9.15.0",
    "eslint-plugin-react-hooks": "^5.0.0",
    "sass": "^1.82.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0"
  }
}
```

#### 依赖变更说明

| 当前依赖 | 目标替代 | 说明 |
|---------|---------|-----|
| `react@16.8.4` | `react@18.3.x` | 主要框架升级 |
| `react-dom@16.4.0` | `react-dom@18.3.x` | 配套升级 |
| `mobx@5.9.4` | `zustand@5.x` | 更轻量的状态管理 |
| `mobx-react@5.4.3` | 移除 | Zustand 不需要 |
| `redux@4.0.4` | 移除 | 使用 Zustand 替代 |
| `react-redux@7.1.0` | 移除 | 使用 Zustand 替代 |
| `redux-thunk@2.3.0` | 移除 | Zustand 原生支持异步 |
| `react-router@5.0.0` | `react-router-dom@6.28.x` | 路由升级 |
| `antd@4.24.2` | `antd@5.22.x` | UI 组件升级 |
| `moment@2.29.4` | `dayjs@1.11.x` | 更轻量的日期库 |
| `node-sass@4.14.1` | `sass@1.82.x` | Dart Sass 替代 |
| `axios@0.18.0` | `axios@1.7.x` | HTTP 客户端升级 |
| `webpack@4.7.0` | `vite@6.0.x` | 构建工具替换 |
| `babel-*` | 移除 | Vite 内置处理 |
| `happypack` | 移除 | Vite 不需要 |
| `uglifyjs-webpack-plugin` | 移除 | Vite 使用 esbuild |

#### 移除的依赖
```
- babel-cli, babel-core, babel-loader
- babel-preset-env, babel-preset-es2015, babel-preset-react
- babel-preset-stage-0, babel-preset-stage-2, babel-preset-latest
- babel-plugin-* (所有 babel 插件)
- happypack
- uglifyjs-webpack-plugin
- mini-css-extract-plugin
- html-webpack-plugin
- webpack, webpack-cli, webpack-dev-server
- node-sass (替换为 sass)
- css-loader, style-loader, less-loader, sass-loader (Vite 内置)
- moment (替换为 dayjs)
- redux, react-redux, redux-thunk (替换为 zustand)
- mobx, mobx-react (替换为 zustand)
```

### 3.4 状态管理迁移 (Mobx → Zustand)

```typescript
// 旧代码 (Mobx)
import { observable, action } from 'mobx';

class TradeStore {
  @observable positions = [];
  @observable balance = 0;

  @action
  updatePositions(positions) {
    this.positions = positions;
  }
}

export default new TradeStore();

// 新代码 (Zustand)
import { create } from 'zustand';

interface TradeState {
  positions: Position[];
  balance: number;
  updatePositions: (positions: Position[]) => void;
  updateBalance: (balance: number) => void;
}

export const useTradeStore = create<TradeState>((set) => ({
  positions: [],
  balance: 0,
  updatePositions: (positions) => set({ positions }),
  updateBalance: (balance) => set({ balance }),
}));
```

### 3.5 路由迁移 (React Router 5 → 6)

```jsx
// 旧代码 (React Router 5)
import { Switch, Route, Redirect } from 'react-router-dom';

<Switch>
  <Route exact path="/" component={Home} />
  <Route path="/trade" component={Trade} />
  <Redirect to="/" />
</Switch>

// 新代码 (React Router 6)
import { Routes, Route, Navigate } from 'react-router-dom';

<Routes>
  <Route path="/" element={<Home />} />
  <Route path="/trade" element={<Trade />} />
  <Route path="*" element={<Navigate to="/" replace />} />
</Routes>
```

### 3.6 Antd 升级 (v4 → v5)

#### 主要变更
- CSS-in-JS 替代 Less
- 移除 `~antd/dist/antd.less` 引入
- 新的 Design Token 系统
- 部分组件 API 变更

```jsx
// 旧代码 (Antd 4)
import { ConfigProvider } from 'antd';
import 'antd/dist/antd.less';

<ConfigProvider>
  <App />
</ConfigProvider>

// 新代码 (Antd 5)
import { ConfigProvider } from 'antd';
// 无需引入 CSS/Less

<ConfigProvider
  theme={{
    token: {
      colorPrimary: '#00558c',
      borderRadius: 2,
    },
  }}
>
  <App />
</ConfigProvider>
```

---

## 四、C++ WebSocket 服务器升级建议

### 4.1 依赖升级

**当前**:
- websocketpp
- boost

**建议**:
- 升级 Boost 到最新稳定版 (1.86.x)
- 考虑迁移到 `uWebSockets` 获得更高性能
- 或使用 Rust 重写核心逻辑

### 4.2 编译优化

```makefile
# 旧编译命令
g++ wsServer.cpp -o wsServer.out -lboost_system

# 新编译命令 (启用优化)
g++ -std=c++20 -O3 -march=native -flto \
    wsServer.cpp -o wsServer.out \
    -lboost_system -lpthread
```

---

## 五、升级实施计划

### Phase 1: 准备工作 (Week 1)

1. **创建升级分支**
   ```bash
   git checkout -b feature/infrastructure-upgrade
   ```

2. **设置 UV 和 Python 环境**
   - 安装 UV
   - 创建 `pyproject.toml`
   - 设置虚拟环境

3. **前端初始化**
   - 安装新版 Node.js (20.x LTS)
   - 初始化 Vite 项目结构

### Phase 2: Python 后端升级 (Week 2-3)

1. **迁移依赖管理**
   - 创建 `pyproject.toml`
   - 安装所有依赖

2. **升级核心模块**
   - `commonFunction.py` → 使用 httpx/websockets
   - `config.py` → 使用 pydantic-settings
   - `webServer.py` → 迁移到 FastAPI

3. **升级 binance_f 模块**
   - 更新 WebSocket 实现
   - 添加类型注解
   - 优化异步处理

### Phase 3: 前端升级 (Week 4-5)

1. **构建工具迁移**
   - 删除 Webpack 配置
   - 创建 Vite 配置
   - 迁移构建脚本

2. **框架升级**
   - React 16 → 18
   - React Router 5 → 6
   - Antd 4 → 5

3. **状态管理迁移**
   - Mobx/Redux → Zustand
   - 重构 store 结构

### Phase 4: 测试与优化 (Week 6)

1. **功能测试**
   - 验证所有 API 接口
   - 验证 WebSocket 连接
   - 验证前端功能

2. **性能测试**
   - 对比升级前后性能
   - 优化瓶颈

3. **文档更新**
   - 更新 README
   - 添加部署文档

---

## 六、风险与注意事项

### 6.1 高风险项

| 风险项 | 影响 | 缓解措施 |
|-------|------|---------|
| 阿里云 SDK 兼容性 | 可能导致云服务调用失败 | 先在测试环境验证 |
| WebSocket 连接稳定性 | 可能影响实时数据 | 保留回退方案 |
| 币安 API 变更 | 可能导致交易失败 | 同时维护旧版本 |

### 6.2 回滚策略

1. 保留原有代码分支
2. 使用 feature flag 控制新功能
3. 准备快速回滚脚本

### 6.3 测试环境要求

- 独立的测试服务器
- 币安测试网 API
- 完整的 CI/CD 流水线

---

## 七、预期收益

### 性能提升
- Python 3.12 比 3.10 快 10-25%
- Vite 开发体验提升 10x
- httpx 异步请求性能提升 3-5x

### 开发体验
- UV 包管理速度提升 100x
- 更好的类型提示和 IDE 支持
- 更清晰的错误消息

### 维护性
- 现代化的依赖管理
- 更少的第三方依赖
- 更好的文档和社区支持

---

## 八、后续扩展建议

1. **添加 TypeScript 支持** - 前端完全迁移到 TypeScript
2. **添加单元测试** - pytest + pytest-asyncio
3. **添加 CI/CD** - GitHub Actions
4. **添加监控** - Prometheus + Grafana
5. **容器化部署** - Docker + Docker Compose

---

*文档创建时间: 2026-01-03*
*最后更新: 2026-01-03*

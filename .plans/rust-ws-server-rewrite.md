# Rust 重写 wsServer.cpp 方案

## 背景

`wsServer.cpp` 是整个量化交易框架的数据聚合中枢，258 行 C++ 代码，基于 websocketpp + Boost 实现。
它本身不做任何交易逻辑，只负责：接收 Python 采集器推送的数据 → 存入内存 → 按需转发给交易服务器。

重写目标：用 Rust 替代 C++，保持核心"哑管道"设计，修复已知缺陷，提升可维护性。

## 现有架构分析

### 数据流

```
Python 数据采集器 ──写入──→ wsServer (端口 3698) ←──读取── 交易服务器
  tickToWs.py                  内存中的全局状态          simpleTrade.py
  oneMinKlineToWs.py                                    (发 "B" 获取快照)
  getBinancePosition.py
  ...
```

### 现有消息协议

#### 读取命令（客户端 → 服务器，单字符）

| 命令 | 含义 | 响应格式 |
|------|------|----------|
| `B` | 获取聚合快照 | `{K线}*{tick}*{持仓}*{禁止列表}*{余额}` |
| `A` | 获取全部1分钟K线 | `{sym0}@{sym1}@...@{symN}` |
| `E` | 获取持仓（JSON包装） | `{"s":"y","d":"{持仓}","i":"E"}` |
| `F` | 获取下一个1分钟索引 | 递增整数（轮询分配） |
| `G` | 获取下一个特殊1分钟索引 | 递增整数（轮询分配） |

#### 写入命令（客户端 → 服务器，16 字节前缀 + 数据）

| 前缀 | 含义 | 数据格式 |
|------|------|----------|
| `sjaiyhsaoyosauio` | 1分钟K线 | `[3位索引][K线JSON]` |
| `sajoiyfpdufiyiry` | 聚合1分钟K线 | `[3位索引][K线JSON]` |
| `sjaoihsoaitowljd` | tick数据 | `[13位时间戳][tick数据]` |
| `gggoihsoaitowljd` | 持仓数据 | `[13位时间戳][持仓数据]` |
| `fdsoihsoaitowljd` | 余额数据 | `[13位时间戳][余额数据]` |
| `abcoihsoaitowljd` | 禁止交易列表 | `[列表数据]` |
| `bbboiyfpdufiyuyu` | 设置symbol数量 | `[3位数字]` |

### 现有缺陷

1. **400 symbol 硬编码上限** — Binance Futures 已有 300+ 交易对，接近上限
2. **无错误处理** — atoi/atol 解析失败、客户端断连时发送都会导致未定义行为
3. **魔术字符串协议** — 16 字节前缀不可读，调试困难
4. **无认证** — 任何人连上端口就能读写
5. **无日志** — 除了一处 cout，完全没有运行时可观测性
6. **无优雅关闭** — Ctrl+C 直接杀进程
7. **无状态查询** — 无法得知服务器当前存了什么数据

## 重写方案

### 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 异步运行时 | `tokio` | Rust 生态标准，成熟稳定 |
| WebSocket | `tokio-tungstenite` | 基于 tokio 的轻量 WebSocket 库 |
| 日志 | `tracing` + `tracing-subscriber` | 结构化日志，支持不同级别 |
| 配置 | `clap` | 命令行参数解析（端口号等） |
| 序列化 | `serde` + `serde_json` | 仅用于状态查询响应 |

### 项目结构

```
ws-server/
  Cargo.toml
  src/
    main.rs           # 入口：解析参数、启动服务器
    server.rs         # WebSocket 服务器主循环
    state.rs          # MarketState：所有全局状态的封装
    protocol.rs       # 消息解析与序列化
    handler.rs        # 消息处理逻辑（读取/写入命令）
```

### 核心数据结构

```rust
// state.rs

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// 带时间戳保护的数据
struct TimestampedData {
    data: String,
    update_ts: i64,
}

/// 全局市场数据状态
struct MarketState {
    // K线数据：HashMap 替代固定数组，key 为 symbol 索引
    kline_1m: HashMap<u16, String>,
    kline_1m_agg: HashMap<u16, String>,     // 聚合1分钟（TWO_ONE_MIN）
    kline_15m: HashMap<u16, String>,
    kline_1h: HashMap<u16, String>,
    kline_4h: HashMap<u16, String>,
    kline_1d: HashMap<u16, String>,
    kline_1w: HashMap<u16, String>,
    kline_1M: HashMap<u16, String>,
    volume: HashMap<u16, String>,
    pole_1d: HashMap<u16, String>,

    // 带时间戳保护的数据
    tick: TimestampedData,
    position: TimestampedData,
    account_balance: TimestampedData,

    // 无时间戳保护
    ban_symbols: String,

    // 元数据
    symbol_count: u16,
    index_1m: u16,              // F 命令的轮询计数器
    index_special_1m: u16,      // G 命令的轮询计数器

    // 缓存：预拼接的聚合K线字符串（写入时更新，读取时直接返回）
    kline_1m_agg_joined: String,
}

// 用 Arc<RwLock<>> 包装，多个连接共享访问
type SharedState = Arc<RwLock<MarketState>>;
```

### 消息协议（新版）

#### 阶段一：兼容模式

保持与现有 C++ 完全相同的协议，Python 端零改动即可切换。
魔术字符串、分隔符、数据格式全部不变。

#### 阶段二：新协议（Python 端同步修改后切换）

用可读的文本前缀替换魔术字符串：

| 旧前缀 | 新前缀 | 含义 |
|--------|--------|------|
| `sjaiyhsaoyosauio` | `KLINE_1M\|` | 1分钟K线 |
| `sajoiyfpdufiyiry` | `KLINE_1M_AGG\|` | 聚合1分钟K线 |
| `sjaoihsoaitowljd` | `TICK\|` | tick数据 |
| `gggoihsoaitowljd` | `POSITION\|` | 持仓数据 |
| `fdsoihsoaitowljd` | `BALANCE\|` | 余额数据 |
| `abcoihsoaitowljd` | `BAN\|` | 禁止交易列表 |
| `bbboiyfpdufiyuyu` | `SYMBOL_COUNT\|` | symbol数量 |

新增命令：

| 命令 | 含义 | 响应 |
|------|------|------|
| `S` | 状态查询 | JSON 格式的服务器状态（连接数、symbol数、各数据最后更新时间、uptime） |

协议版本协商：客户端连接时发送 `V2` 表示使用新协议，不发则默认旧协议。这样可以新旧客户端共存。

### 新增功能

#### 1. 命令行参数

```bash
# 默认行为（兼容旧版）
./ws-server

# 自定义端口
./ws-server --port 3698

# 指定日志级别
./ws-server --port 3698 --log-level info

# 启用简单 token 认证
./ws-server --port 3698 --token "my_secret_token"
```

#### 2. 简单认证（可选）

启动时通过 `--token` 参数设置。客户端通过 URL query 传入：

```
ws://server:3698?token=my_secret_token
```

在 `validate` 阶段校验，未通过则拒绝连接。不设置 `--token` 则不启用认证（向后兼容）。

#### 3. 结构化日志

```
2026-04-01T09:00:00Z INFO  ws_server: listening on 0.0.0.0:3698
2026-04-01T09:00:01Z INFO  ws_server: client connected addr=192.168.1.10:52341
2026-04-01T09:00:01Z DEBUG ws_server: kline_1m updated index=3
2026-04-01T09:00:02Z WARN  ws_server: stale tick rejected incoming_ts=1707123456000 current_ts=1707123456789
2026-04-01T09:00:03Z INFO  ws_server: client disconnected addr=192.168.1.10:52341
```

#### 4. 优雅关闭

捕获 SIGTERM/SIGINT，执行：
1. 停止接受新连接
2. 向所有已连接客户端发送 close frame
3. 等待最多 5 秒让客户端断开
4. 退出

#### 5. 状态查询（S 命令）

```json
{
  "symbol_count": 312,
  "active_connections": 5,
  "tick_update_ts": 1707123456789,
  "position_update_ts": 1707123456100,
  "balance_update_ts": 1707123455000,
  "uptime_secs": 86400
}
```

### 不改变的设计

| 保留项 | 原因 |
|--------|------|
| 单线程异步模型 | 全是内存操作，多线程无收益。tokio 单线程 runtime 即可 |
| 文本协议 | Python 端处理方便，性能瓶颈不在序列化 |
| 不持久化 | 实时数据，重启后 Python 端会重新灌入 |
| 不解析数据内容 | "哑管道"设计正确，逻辑留给 Python |
| 端口 3698 | 保持默认值不变，通过参数可修改 |

## 实施步骤

### Step 1: 初始化 Rust 项目

在项目根目录创建 `ws-server/` 子目录，`cargo init`。
添加依赖：tokio, tokio-tungstenite, tracing, tracing-subscriber, clap, serde, serde_json。

### Step 2: 实现 state.rs

- MarketState 结构体及其方法
- TimestampedData 的更新逻辑（时间戳比较）
- 聚合 K 线的缓存重建
- 轮询索引的原子递增

### Step 3: 实现 protocol.rs

- 旧协议解析器：识别单字符命令和 16 字节前缀
- 消息类型枚举：

```rust
enum ClientMessage {
    // 读取命令
    GetSnapshot,           // B
    GetAllKline1m,         // A
    GetPosition,           // E
    NextIndex1m,           // F
    NextIndexSpecial1m,    // G
    GetStatus,             // S (新增)

    // 写入命令
    UpdateKline1m { index: u16, data: String },
    UpdateKline1mAgg { index: u16, data: String },
    UpdateTick { ts: i64, data: String },
    UpdatePosition { ts: i64, data: String },
    UpdateBalance { ts: i64, data: String },
    UpdateBanSymbols { data: String },
    SetSymbolCount { count: u16 },

    // 无法识别
    Unknown(String),
}
```

### Step 4: 实现 handler.rs

- 对每种 ClientMessage 分发处理
- 读取命令：从 SharedState 读取并格式化响应
- 写入命令：更新 SharedState

### Step 5: 实现 server.rs

- tokio WebSocket 服务器主循环
- 连接管理（on_open, on_close, on_message）
- 可选的 token 认证（在 HTTP upgrade 阶段校验 query 参数）
- 优雅关闭（tokio::signal 捕获 Ctrl+C）

### Step 6: 实现 main.rs

- clap 解析命令行参数
- 初始化 tracing 日志
- 启动服务器

### Step 7: 兼容性测试

- 用 Python websocket-client 编写测试脚本，模拟数据采集器和交易服务器
- 验证所有 7 种写入命令 + 5 种读取命令
- 验证时间戳竞争保护（发送旧时间戳，确认被拒绝）
- 验证轮询索引递增和环绕
- 验证聚合 K 线缓存在写入后立即更新

### Step 8: 集成测试

- 同时启动 Rust ws-server 和一个 Python 数据采集器
- 用另一个 Python 客户端发 "B" 读取快照，确认数据正确

### Step 9: 新协议（Step 7/8 通过后）

- 在 protocol.rs 中添加新协议解析器
- 通过连接时的 `V2` 消息自动切换协议版本
- 修改对应的 Python 数据采集器使用新协议

## 编译与运行

```bash
cd ws-server

# 开发
cargo run -- --port 3698 --log-level debug

# 生产构建
cargo build --release
# 产物在 ws-server/target/release/ws-server

# 部署（替代原来的 wsServer.out）
nohup ./ws-server --port 3698 --log-level info >/dev/null &
```

## 风险与注意事项

1. **协议兼容性是第一优先级。** 阶段一必须做到 Python 端零改动即可切换，否则整个框架无法运行
2. **聚合 K 线缓存的正确性。** 原 C++ 在每次写入 `sajoiyfpdufiyiry` 时都会遍历所有 symbol 重建拼接字符串，Rust 版必须保持相同行为
3. **轮询索引的语义。** F/G 命令的递增是全局的（不是 per-connection），多个采集器共享同一个计数器，Rust 版需要用 RwLock 保护
4. **性能不会是问题。** 原 C++ 单线程就够用，Rust 只会更快
5. **Python 端的 WebSocket 连接方式不变。** `websocket.create_connection("ws://host:3698")` 对 Rust 服务器完全透明

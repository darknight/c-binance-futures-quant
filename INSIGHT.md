# INSIGHT.md

本文记录我对当前仓库重构状态、交易系统架构、已达成目标和后续切入点的理解。时间点：2026-05-18。

## 先给结论

这个项目已经从“原作者的阿里云 + MySQL + Bottle + React 16 + C++ wsServer + 手工分发脚本”明显推进到了“PostgreSQL/SQLModel + FastAPI + React 19/Vite + Rust ws-server + Docker Compose + env 配置”的方向。

目前最重要的事实是：**基础设施现代化已经完成了大半，但策略层和实盘运行闭环还没有真正产品化**。也就是说，项目现在更像一个“现代化后的交易系统骨架和仪表盘”，还不是一套可以放心部署、观测、回测、灰度、实盘放量的策略平台。

后续最合理的切入点不是继续大面积重构，而是先把系统切成三层：

1. **数据层**：行情、持仓、余额、成交、收入流水是否稳定进入系统。
2. **执行层**：下单、撤单、止损、风控、订单超时处理是否可靠。
3. **策略层**：如何把自己的策略接入，并且能先模拟/小资金验证。

先让这三层形成一个最小可运行闭环，再继续删除遗留目录和做架构升级。

## 原始目标进度

### 1. 废弃旧技术栈，迁移到现代工具

状态：**大部分已达成，仍有尾巴。**

已经完成或基本完成：

- Python 包管理迁到 `uv`，依赖定义在 `pyproject.toml` 和 `uv.lock`。
- 配置从旧 `config.py` 迁到 `settings.py` + `.env`，使用 `pydantic-settings`。
- 数据库从 MySQL 迁到 PostgreSQL，ORM 使用 SQLModel/SQLAlchemy，迁移由 Alembic 管理。
- 旧 Bottle `webServer.py` 已被 `web_server/` 下的 FastAPI 模块化实现替代。
- 前端从 `react-front/` 的 React 16 老项目迁到 `web-front/` 的 React 19 + Vite + TypeScript + antd 5 + Zustand + ECharts。
- 测试体系已经有基础覆盖：settings、InfraClient、models、queries、web_server、dashboard。

未完成/需收尾：

- `webServer.py` 仍保留在仓库中，属于遗留参考，不应再作为主入口。
- `react-front/` 仍保留。`docs/frontend-parity-audit.md` 已说明新前端覆盖了旧前端当前 active dashboard route，但还需要 owner decision 后才能删除。
- README 仍大量描述旧架构，例如 C++、阿里云、OSS、MySQL、旧启动方式等。对新维护者会造成认知干扰。
- `web-front/README.md` 还是 Vite 模板文档，需要替换成真实项目说明。
- 代码风格上，很多 Python 服务仍是全局变量 + 无限循环 + 脚本式结构。技术栈现代化了，但应用结构还没完全现代化。

### 2. 移除阿里云依赖，转 Docker / DigitalOcean / Cloudflare

状态：**核心依赖已移除，部署与文档还需硬化。**

已经完成或基本完成：

- 阿里云 ECS 自动发现已由环境变量替代：`SERVER_NAME`、`MACHINE_INDEX`、`TICK_INSTANCE_COUNT`、`SECOND_OPEN_HOSTS` 等。
- 飞书通知已替换为 Telegram。
- 阿里云 OSS SDK `oss2` 已替换为 Cloudflare R2 兼容的 `boto3` S3 client。
- `docker-compose.yml` 已覆盖 PostgreSQL、Rust `ws-server`、FastAPI web-server、数据采集、交易、风控、post-trade 服务。
- `.env.example` 和 `CLAUDE.md` 已描述本地 Podman/Docker 启动方式。

未完成/需收尾：

- README 仍有旧阿里云部署说明。
- `dataPy/uploadDataPy.py` 仍存在，按现架构应视为 deprecated 或删除。
- R2 方法名仍叫 `oss_put_obj` / `oss_get_obj`，这是兼容旧调用方的合理过渡，但长期建议改名为 storage/client 语义。
- `afterTrade/webOssUpdate.py` 仍是“生成 JSON 上传对象存储给前端”的旧模式；新 `web-front` 已直接读 FastAPI API，这条链路后续要决定是保留做静态快照，还是完全废弃。
- DigitalOcean/Dokploy 的生产部署清单、健康检查、日志、备份、密钥管理还没有形成明确文档。

### 3. 理解交易系统，并实现自己的策略跑起来

状态：**理解入口已经清楚，但策略接入还没有抽象出来。**

当前系统的核心思路：

- `dataPy/` 负责采集行情，写入 ws 聚合服务器。
- `ws-server/` 只做内存聚合和分发，不做策略。
- `keyPy/` 负责关键风控和账户侧数据：持仓、余额、订单超时、止损、手续费/收入。
- `simpleTrade.py` 是交易服务器 demo：从 ws-server 拉快照，维护本地 1m K 线，根据简单条件下单。
- `web_server/` 既是前端 API，也是订单、止盈止损、记录交易、机器状态的 HTTP 控制面。
- `afterTrade/` 处理交易后数据、收益统计、持仓记录、展示数据。

策略真正该插入的位置是 `simpleTrade.py` 这一类“交易服务器”。原作者的设计不是提供一个策略框架，而是提供一套数据/风控/执行底座，策略需要自己在交易服务器里写。

当前 `simpleTrade.py` 的策略逻辑很薄：

- 每分钟同步一次完整 1m K 线。
- 高频从 ws-server 获取聚合快照 `B`，更新本地 tick 和本地 K 线。
- 对每个 symbol 计算最近 1m 涨跌幅。
- demo 中是“1m 下跌超过 1% 且无仓位则开多；1m 上涨超过 0.5% 且有仓位则平多”。
- 总浮亏低于 -100 时强制平仓。

问题是：这还不是一个适合持续迭代策略的接口。策略逻辑、数据同步、订单执行、风控、状态变量全部混在同一个脚本里。后续要做自己的量化，建议先抽出最小策略接口，而不是直接在 `simpleTrade.py` 里继续堆代码。

建议的策略接口方向：

```python
class Strategy:
    def on_market_snapshot(self, ctx) -> list[Signal]:
        ...
```

其中 `ctx` 包含 symbol、kline、tick、position、balance、ban list、精度信息；`Signal` 只表达开仓/平仓/撤单/止盈止损意图。下单、重试、风控、记录由执行层统一处理。

### 4. 移除 C++，用 Rust 替代

状态：**Rust 替代已完成第一阶段，但旧 C++ 文件还未删除。**

已经完成：

- `ws-server/` 已实现 Rust 版 WebSocket 聚合服务器。
- 使用 `tokio` + `tokio-tungstenite`。
- 兼容旧 C++ 协议，包括魔术字符串和 `A/B/E/F/G` 命令。
- 使用 HashMap 替代固定数组上限。
- 支持结构化日志、状态查询 `S`、可选 token auth、graceful shutdown。
- 有 Rust integration tests。
- Docker Compose 默认使用 Rust `ws-server`。

未完成/需收尾：

- `wsServer.cpp` 仍在仓库中。可以保留一段时间作为协议参考，但应标记为 legacy，最终删除。
- Python 客户端仍使用旧魔术字符串协议。Rust 文档里提到的新可读协议是 Phase 2，但当前仍以兼容模式为主。
- `CLAUDE.md` 已把 `wsServer.cpp` 标为 deprecated；README 还没有同步现代化。

### 5. 边修改边理解量化交易世界

状态：**系统层经验已经显露出来，研究层还需要补齐。**

这个项目真正值得学习的不是 demo 策略，而是这些工程判断：

- 高频不等于纳秒级 HFT；它追求的是低成本、低延迟、可横向扩展的“毫秒级/秒级”交易系统。
- 数据读取和交易执行分离，降低 Binance API rate limit 和单点延迟的影响。
- 多路径读取关键账户信息：positionRisk、account、WebSocket，用时间戳选择较新数据。
- 用独立服务处理订单超时、止损、手续费、持仓记录，避免交易策略脚本承担所有责任。
- 交易服务器可以分布式运行，同一个信号由多台机器抢先捕捉，或者统一经 web server 执行。
- 实盘里最重要的不只是策略收益，而是：数据延迟、错误接口、订单未成交、仓位异常、手续费、风控熔断、可观测性。

但要进入量化交易，还缺几个关键能力：

- 回测框架：当前没有严肃的历史数据回放和策略评估。
- 模拟交易/纸交易：当前 demo 直接调用真实 Binance 下单接口。
- 策略指标体系：胜率、盈亏比、最大回撤、手续费敏感性、滑点、成交率、资金利用率。
- 参数管理：策略参数没有版本化、没有实验记录。
- 实盘灰度：没有从 dry-run 到小资金再到放量的机制。

## 当前系统心智模型

可以把它理解成一个事件流系统：

```text
Binance 行情/账户 API
        |
        v
dataPy/keyPy 采集与风控服务
        |
        v
ws-server 内存聚合
        |
        v
交易服务器 simpleTrade.py / 未来 strategy runner
        |
        v
Binance Futures 下单
        |
        v
web_server + afterTrade + PostgreSQL + web-front 展示与审计
```

其中 `ws-server` 是“快数据平面”，PostgreSQL 是“慢数据和审计平面”，FastAPI 是“控制面和展示 API”，交易服务器是“策略和执行入口”。

这套系统最原始的优势在于：用多个廉价 IP/服务拆开 Binance API 权重压力，并把关键数据汇总到一个轻量内存中心。现代化重构后的重点应该是保留这个优势，同时补上现代工程里的可测试、可部署、可观测和可回滚能力。

## 建议的下一步路线

### Phase 1：清理认知负债

目标：让新旧架构边界清晰，不再 lost。

建议任务：

- 更新 README，明确新主路径：`uv`、PostgreSQL、FastAPI、Rust ws-server、web-front、Docker/Podman。
- 给 `webServer.py`、`wsServer.cpp`、`react-front/`、`dataPy/uploadDataPy.py` 加强 deprecated 标记，或建立删除 issue。
- 替换 `web-front/README.md` 模板内容。
- 在 `docs/` 里把已完成计划标注为 completed，未完成项转成一个短的 roadmap。
- 修复 `tests/test_web_server.py` 的 route 列表未包含 dashboard router 的认知偏差，或明确拆分 dashboard tests。

### Phase 2：跑通本地闭环

目标：不用真实下单，也能看到完整数据流和 dashboard。

建议任务：

- 固化一条本地启动脚本或 Makefile：启动 postgres、迁移、seed demo data、启动 backend、启动 frontend。
- 为 `ws-server` 增加一个 Python smoke producer/consumer：写入 tick/kline/position/balance，再读取 `B` 验证格式。
- 增加 dry-run 交易模式：策略产生订单意图，但不调用 Binance，只写入日志/数据库。
- 让 `simpleTrade.py` 在 dry-run 下可以运行至少一个完整循环。

### Phase 3：抽出策略运行器

目标：让“写自己的策略”变成明确接口，而不是改大脚本。

建议任务：

- 新建 `strategy/` 或 `trading/strategy_runner.py`。
- 从 `simpleTrade.py` 拆出三个边界：
  - market data adapter：负责从 ws-server 解析快照。
  - execution adapter：负责下单/撤单/重试/记录。
  - strategy：只根据上下文返回 signal。
- 保留 `simpleTrade.py` 作为 demo 策略，但让它调用新 runner。
- 增加策略单元测试：给定 kline/position，验证输出 signal。
- 增加 paper trading 模式，先生成模拟成交和 PnL。

### Phase 4：实盘前风控硬化

目标：不要让策略 bug 直接变成真实亏损。

建议任务：

- 全局交易开关：env 或 DB 控制 `TRADING_ENABLED=false` 默认关闭。
- 单 symbol 最大仓位、单次最大名义金额、总仓位上限。
- 每日亏损/连续亏损/接口异常熔断。
- 下单幂等：clientOrderId 规则、重复信号抑制。
- Binance testnet 或 dry-run 优先路径。
- 所有真实下单接口必须有结构化审计日志。

### Phase 5：部署与观测

目标：DigitalOcean/Dokploy 上能长期跑。

建议任务：

- 为每个 compose service 增加 healthcheck 和 restart policy 说明。
- 明确 `.env` 生产字段：Binance keys、Telegram、R2、database、ws token。
- PostgreSQL 备份/恢复文档。
- 日志聚合策略：至少先标准化 stdout，后续接 Grafana/Loki 或 Cloudflare/DigitalOcean 日志。
- WebSocket server token auth 在生产启用。
- 删除或隔离所有无需暴露公网的端口。

## 当前值得注意的风险

### 代码层风险

- `infra_client.py` 里 `open_take_binance_orders_by_web_server()` 和 `end_open_by_web_server()` 使用了 `TRADE_WEB_ADDRESS`，当前文件内看不到定义。这可能是旧配置迁移残留，后续需要修复为 `settings.web_address` 或删除死代码。
- `oss_put_obj()` / `oss_get_obj()` 在 R2 未配置时 `self.s3_client` 为 None，会吞异常打印。短期可接受，长期应显式返回错误或跳过。
- `simpleTrade.py` 仍有大量全局变量和脚本级请求，导入即执行，难测试、难复用。
- 后端启动会调用 Binance `exchangeInfo`，本地/CI 如果没有外网会卡住或失败。测试里通过 mock 绕过，但生产启动需要更好的降级策略。
- `tests/test_web_server.py` 的 `_create_test_app()` 没 include dashboard router，但 `test_dashboard.py` 单独覆盖了 dashboard。这不是错误，但容易让人误以为所有路由测试都集中在一个地方。

### 架构层风险

- 当前没有回测/模拟交易层，策略验证容易直接跳到实盘。
- 没有明确的策略参数版本管理和实验记录。
- 订单执行和策略逻辑耦合，后续多策略会互相污染。
- 对 Binance SDK 的 fork 依赖较深，升级成本未知。
- README 与实际架构不一致，会持续制造误解。

### 交易层风险

- demo 策略没有统计意义，不能作为盈利逻辑参考。
- 高频扫描会被手续费、滑点、未成交、接口错误显著影响。
- 分布式多交易服务器如果没有统一幂等和仓位约束，可能重复开仓。
- 风控服务必须比策略更稳定，否则策略正确也可能因执行异常亏损。

## 我建议你的切入点

如果你现在觉得 lost，建议不要再从“继续重构哪个旧文件”开始，而是按下面顺序推进：

1. **先更新 README 和路线图**：把当前真实架构写清楚，旧架构移到 legacy section。
2. **跑通本地 demo 闭环**：PostgreSQL + ws-server + backend + web-front + seed data。
3. **做 ws-server smoke test**：确认 Python 客户端和 Rust 聚合服务器协议稳定。
4. **给交易加 dry-run**：确保策略可以运行但不会真实下单。
5. **抽策略接口**：把 `simpleTrade.py` 改造成 demo strategy，而不是继续当主框架。
6. **写第一个你自己的策略**：从最简单的、可测试的信号开始，例如均线/动量/波动率过滤，不追求盈利，先追求可验证。
7. **再做回测/纸交易**：有结果记录后再考虑 testnet 或小资金实盘。

## 一个务实的近期任务清单

- [ ] 更新 README：新架构优先，旧架构标记 legacy。
- [ ] 更新 `web-front/README.md`：替换 Vite 模板。
- [ ] 为 `webServer.py`、`wsServer.cpp`、`react-front/`、`dataPy/uploadDataPy.py` 写明确删除标准。
- [ ] 修复 `infra_client.py` 中 `TRADE_WEB_ADDRESS` 残留。
- [ ] 增加 `TRADING_ENABLED` / dry-run 配置，默认禁止真实下单。
- [ ] 写一个 `scripts/ws_smoke_test.py`，验证 ws-server 写入和读取。
- [ ] 从 `simpleTrade.py` 抽出 `Strategy`/`Signal`/`ExecutionAdapter` 的最小接口。
- [ ] 给 demo 策略加单元测试。
- [ ] 写一篇 `docs/strategy-development.md`，说明如何新增自己的策略。

## 最后判断

这个项目现在不应该被看成“重构失败或半成品”，而应该看成“底座迁移基本成功，但策略平台化尚未开始”。你最初五个目标里，1、2、4 都已经有很大进展；3 和 5 才是后续真正有价值、也更难的部分。

继续做下去的关键，是把下一阶段目标从“替换旧技术”切换成“建立可验证的交易闭环”。只要 dry-run、策略接口、回测/纸交易、风控开关这几件事立起来，这个仓库就会从现代化迁移项目，变成你真正可以学习和迭代量化交易的系统。

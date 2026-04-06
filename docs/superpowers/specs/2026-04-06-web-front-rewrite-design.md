# 前端仪表盘重写设计 (web-front)

## Context

`react-front/` 使用 React 16 + Webpack 4 + Babel 6，在当前 Node 版本下无法运行（node-sass 编译失败）。逐个升级成本高于重写。用现代技术栈在 `web-front/` 重建仪表盘。

K 线图作为独立后续任务，不在此 spec 范围内。

## 技术栈

| 组件 | 选择 |
|------|------|
| 构建 | Vite |
| 框架 | React 19 + TypeScript |
| UI | antd 5（深/浅主题切换） |
| 状态 | Zustand |
| 图表 | ECharts (echarts-for-react) |
| 日期 | dayjs |
| HTTP | 原生 fetch |

## 功能范围

**保留：** 5 个 KPI 卡片、历史数据表（13 列可排序）、大亏交易表、余额趋势图、持仓价值趋势图、日收入图（柱/线切换）、深/浅主题切换

**去除：** 登录/注册、聊天/社交、多交易所支持、Redux 样板代码、TradingView K 线图（后续独立任务）、当前持仓表（数据来源于 wsServer 实时推送，不适合 API 轮询）

## 数据源（FastAPI 后端 API）

API 基础 URL 通过 `VITE_API_URL` 环境变量注入（`.env` 文件，不提交 git）。

所有请求使用 `POST` 方法，与现有后端端点风格一致。

### 新增端点（需后端开发）

| 端点 | 缓存策略 | 内容 |
|------|---------|------|
| `POST /get_dashboard_summary` | AppState 内存，10s TTL | KPI 数据：余额、持仓价值、今日 profit/commission、系统状态、运行时间 |
| `POST /get_profit_by_symbol` | AppState 内存，5min TTL（todayTs 变化时强制刷新） | 按 symbol 聚合 4 个时间段的 profit/commission/BNB volume |

### 复用现有端点（无需修改）

| 端点 | 内容 |
|------|------|
| `POST /get_big_loss_trades` | 大亏交易表（已有 60s 缓存） |
| `POST /get_day_income` | 日收入图数据（已有 300s 缓存） |
| `POST /get_position_record` | 持仓趋势图（余额/持仓价值绝对值记录） |

### 前端轮询策略

| 数据 | 端点 | 轮询频率 | 说明 |
|------|------|---------|------|
| KPI + 系统状态 | `/get_dashboard_summary` | 10s | 高频，保持实时感 |
| 历史利润表 | `/get_profit_by_symbol` | 5min | 计算量大，低频即可 |
| 大亏交易 | `/get_big_loss_trades` | 60s | 后端已有缓存 |
| 日收入图 | `/get_day_income` | 15min | 日粒度数据，低频 |
| 持仓趋势图 | `/get_position_record` | 5min | 按需刷新（切换时间范围时立即请求） |

## 后端端点设计

### POST /get_dashboard_summary

放在新 router `web_server/routers/dashboard.py` 中。

聚合已有数据源，返回仪表盘 KPI 所需的全部信息。

**响应格式：**
```json
{
  "s": "ok",
  "balance": 12345.67,
  "positionValue": 5678.90,
  "oneDayVol": 123.45,
  "oneDayProfit": 456.78,
  "systemStatus": "run",
  "systemUpdateTs": 1712345678,
  "runTime": "3d 12h",
  "t": 1712345678
}
```

**实现逻辑：**
1. 从 `PositionRecord` 表获取最新余额和持仓价值（复用 `/get_all_acount_info` 的查询逻辑）
2. 从 `AppState.income_obj["today"]` 获取今日 profit/commission（需先触发 income 更新）
3. 从 `AppState.trade_machine_status_data` 获取系统状态和运行时间
4. 缓存在 AppState 中，10s TTL

### POST /get_profit_by_symbol

复制 `afterTrade/webOssUpdate.py` 的 `getProfit()` 逻辑。

**响应格式：**
```json
{
  "s": "ok",
  "p": {"BTCUSDT": [100, 500, 2000, 8000], "all": [300, 1500, 6000, 24000]},
  "c": {"BTCUSDT": [10, 50, 200, 800], "all": [30, 150, 600, 2400]},
  "v": {"BTCUSDT": [0.5, 2.5, 10, 40], "all": [1.5, 7.5, 30, 120]},
  "t": 1712345678000
}
```

其中每个数组的 4 个值对应：`[昨日, 近7天, 近30天, 全部]`

**实现逻辑（从 `getProfit()` 移植）：**
1. 查询 `IncomeHistoryTake` 表，条件 `binance_ts < todayTs`
2. 遍历每条记录：
   - BNB 资产转 USDT：`realIncome = income * bnb_price`
   - `COMMISSION` 类型：`realIncome * 0.6` 计入 commission(c) 和 profit(p)；BNB 资产同时计入 volume(v)
   - `REALIZED_PNL` / `FUNDING_FEE` 类型：`realIncome` 计入 profit(p)
3. 按时间段分桶（昨日/7天/30天/全部）
4. 汇总 "all" 行（所有 symbol 求和）
5. 缓存在 AppState 中，5min TTL；todayTs 变化时强制刷新

## 布局

单列布局，从上到下：

1. **顶栏**：标题 + 主题切换按钮
2. **KPI 卡片区**（5 个）：总余额、持仓价值、24h 手续费、总利润、系统状态
3. **余额趋势图** + 时间范围选择器（最近一天/七天/一个月/全部）
4. **持仓价值趋势图**（共享余额趋势图的时间范围）
5. **日收入图**（柱/线切换）
6. **大亏交易表**（4 列：币种、时间、亏损金额、亏损比例）— 与 `/get_big_loss_trades` 返回字段一致
7. **历史数据表**（13 列：币种 + 4 个时间段 × 3 指标，可排序）

## 主题切换

- antd `ConfigProvider` + `theme.defaultAlgorithm` / `theme.darkAlgorithm`
- ECharts 通过 `theme` prop 切换 `'dark'` / `undefined`（light）
- 主题偏好存 `localStorage`，默认深色
- 页面顶部放切换按钮（太阳/月亮图标）

## 项目结构

```
web-front/
  public/
  src/
    main.tsx                    # 入口
    App.tsx                     # ConfigProvider + 轮询 + 布局
    vite-env.d.ts               # ImportMetaEnv with VITE_API_URL
    types/
      index.ts                  # 所有 TS 接口
    api/
      dashboard.ts              # 5 个 POST 请求函数
    stores/
      useThemeStore.ts          # 主题切换 + localStorage 持久化
      useDashboardStore.ts      # KPI 数据（来自 /get_dashboard_summary）
      useProfitStore.ts         # 历史利润表（来自 /get_profit_by_symbol）
      useDayIncomeStore.ts      # 日收入图（来自 /get_day_income）
      useChartStore.ts          # 持仓趋势图（来自 /get_position_record）
    hooks/
      usePolling.ts             # 多频率轮询生命周期管理
    utils/
      format.ts                 # 时间格式化 + 数字格式化
    components/
      ThemeToggle.tsx           # 主题切换按钮
      KpiCards.tsx              # 5 个 KPI 卡片
      BalanceChart.tsx          # 余额趋势折线图 + 范围选择器
      PositionValueChart.tsx    # 持仓价值趋势折线图
      DayIncomeChart.tsx        # 日收入柱/线切换图
      BigLossTable.tsx          # 大亏交易表
      HistoryTable.tsx          # 历史数据表 (13 列可排序)
    styles/
      global.css                # 全局样式
  .env.example                  # VITE_API_URL=
  index.html
  vite.config.ts
  tsconfig.json
```

## Stores 设计

### useThemeStore
- `isDark: boolean`（默认 true，持久化到 localStorage）
- `toggle()`: 翻转 isDark

### useDashboardStore
- 状态：`balance`, `positionValue`, `oneDayVol`, `oneDayProfit`, `systemStatus`, `systemUpdateTs`, `runTime`
- Action `fetchSummary()`: 调 `/get_dashboard_summary`，更新全部字段

### useProfitStore
- 状态：`profitData: { p, c, v, t }`, `historyRows: HistoryRow[]`
- Action `fetchProfit()`: 调 `/get_profit_by_symbol`，转换为 historyRows（13 列表格数据）
- `allProfit` 计算：`dashboard.oneDayProfit + profitData.p["all"][3]`（今日利润 + 历史全部利润）

### useDayIncomeStore
- 状态：`chartType`（bar/line，持久化到 localStorage）、`timeArr`, `barArr`, `lineArr`, `updateTime`
- Action `fetchDayIncome()`: 调 `/get_day_income`，累加计算 lineArr

### useChartStore
- 状态：`range`（lastOneDay/lastSevenDays/lastOneMonth/all）、`timeArr`, `balanceArr`, `positionValueArr`, `minBalance`, `minPositionValue`
- Action `fetchPositionRecord(range)`: 根据 range 计算 beginTs/endTs，调 `/get_position_record`（`symbol=ALL`），直接用返回的绝对值

## 关键数据转换逻辑

### historyRows 转换（从 /get_profit_by_symbol 响应）
```typescript
// 遍历 response.p 的每个 key (symbol)
// 对每个 symbol，从 p/v/c 中提取 [yesterday, week, month, all] 四个周期数据
// 生成 13 列行对象，"all" key 显示为 "全部"
```

### dayIncome 累加
```typescript
// 输入：response.d[] 数组，每项包含 dayBeginTime, netProfit
// barArr = 每日 netProfit
// lineArr = 累加值（折线图）
```

### positionRecord 处理
```typescript
// 输入：/get_position_record 返回的绝对值记录数组
// 直接提取 time, balance, positionValue 用于图表
// 计算 minBalance, minPositionValue 用于 Y 轴最小值
```

### allProfit 计算
```typescript
// allProfit = useDashboardStore.oneDayProfit + useProfitStore.profitData.p["all"][3]
// （今日实时利润 + 历史全部利润）
```

## 环境变量

```
# web-front/.env（不提交 git）
VITE_API_URL=http://localhost:8000
```

```
# web-front/.env.example（提交 git）
VITE_API_URL=
```

## 验证

1. `npm run dev` 启动后浏览器可访问
2. KPI 卡片显示非零数值（如果后端可用）
3. 余额趋势图和持仓价值趋势图正确渲染
4. 日收入图柱/线切换正常
5. 历史表 13 列均可排序
6. 大亏交易表正确显示或显示"暂无数据"
7. 时间范围选择器切换后图表数据更新
8. 深/浅主题切换正常，刷新后保持
9. 轮询：KPI 10s 更新，利润表 5min 更新
10. `npm run build` 生产构建成功
11. `npx tsc --noEmit` 零 TypeScript 错误

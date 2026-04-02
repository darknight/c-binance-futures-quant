# 重写 react-front → web-front

## Context

`react-front/` 是对外量化交易数据展示面板，从阿里云 OSS 读取 JSON 数据展示持仓、盈亏、图表。技术栈严重过时（React 16 + Webpack 4 + Babel 6 + Redux），在当前 Node v25 下无法运行（node-sass 编译失败）。逐个升级成本高于重写，因此用现代技术栈在 `web-front/` 重建。

## 技术栈

| 组件 | 选择 |
|------|------|
| 构建 | Vite |
| 框架 | React 19 + TypeScript |
| UI | antd 5 |
| 状态 | Zustand |
| 图表 | ECharts (echarts-for-react) |
| K线 | TradingView (复制旧项目静态库) |
| 日期 | dayjs |
| HTTP | 原生 fetch |

## 功能范围

**保留：** KPI 卡片(5个)、持仓表、历史数据表(13列)、大亏交易表、余额趋势图、持仓价值趋势图、日收入图(柱/线切换)、TradingView
**去除：** 登录/注册、聊天/社交、WebSocket 实时行情、多交易所支持、Redux 样板代码

## 数据源（全部从 OSS 读取，无后端 API）

1. `https://zuibite-api.oss-cn-hongkong.aliyuncs.com/cQuant/{lastMinTime}.json` — 主数据（3s 轮询，分钟变化时刷新）
2. `https://zuibite-api.oss-cn-hongkong.aliyuncs.com/cQuant_day_income/data.json` — 日收入（15分钟轮询）
3. `https://zuibite-api.oss-cn-hongkong.aliyuncs.com/cQuant_change/{type}Arr.json` — 持仓历史（随主数据刷新）
4. `https://zuibite-api.oss-cn-hongkong.aliyuncs.com/investor/{lastMinTime}.json` — 投资者历史数据

## 项目结构

```
web-front/
  public/
    charting_library/           # 从 react-front/pubilc/charting_library/ 复制
  src/
    main.tsx                    # 入口
    App.tsx                     # 根组件：ConfigProvider + 轮询 + 布局
    types/
      index.ts                  # 所有 TS 接口
      tradingview.d.ts          # TradingView 全局类型声明
    api/
      oss.ts                    # 4 个 OSS fetch 函数
    stores/
      useQuantStore.ts          # 主数据：KPI、持仓、历史表、大亏交易、系统状态
      useDayIncomeStore.ts      # 日收入数据
      useChartStore.ts          # 持仓历史（余额/持仓价值趋势图）
    hooks/
      usePolling.ts             # 通用轮询 hook
    utils/
      format.ts                 # turnTsToTime (dayjs 重写) + 数字格式化
    components/
      KpiCards.tsx              # 5 个 KPI 卡片
      PositionTable.tsx         # 持仓表 (4列)
      HistoryTable.tsx          # 历史数据表 (13列可排序)
      BigLossTable.tsx          # 大亏交易表 (5列)
      BalanceChart.tsx          # 余额趋势 ECharts 折线图
      PositionValueChart.tsx    # 持仓价值趋势 ECharts 折线图
      DayIncomeChart.tsx        # 日收入 ECharts 柱/线图
      TradingViewChart.tsx      # TradingView K线图容器
    styles/
      global.css                # 全局样式
  index.html                    # 含 TradingView script 标签
  vite.config.ts
  tsconfig.json
```

## 实施步骤

### Step 1: 项目初始化
- `npm create vite@latest web-front -- --template react-ts`
- 安装依赖：`antd@5 @ant-design/icons dayjs zustand echarts echarts-for-react`
- 配置 vite.config.ts（路径别名 `@/` → `src/`）
- 配置 tsconfig 路径别名
- 复制 TradingView 静态库：`cp -r react-front/pubilc/charting_library/ web-front/public/charting_library/`

### Step 2: 类型定义 + 工具函数
- `src/types/index.ts` — 所有接口（QuantDataResponse, PositionItem, HistoryTableRow, BigLossTradeRow 等）
- `src/types/tradingview.d.ts` — TradingView 全局类型
- `src/utils/format.ts` — 移植 `turnTsToTime`（用 dayjs 重写）和数字格式化
- `src/styles/global.css` — 最小全局样式

### Step 3: API 层 + Zustand Stores
- `src/api/oss.ts` — 4 个 fetch 函数，附 `Math.random()` 缓存击穿
- `src/stores/useQuantStore.ts` — 移植 Show.js `getQuantData()` 的数据转换逻辑（行 248-389）
  - `bigLossTradeArr` → `BigLossTradeRow[]` 转换
  - `secondOpenObjArr` → `HistoryTableRow[]` 转换（遍历 p/v/c 对象）
  - `systemStatus` 正常判断（5分钟超时检测）
- `src/stores/useDayIncomeStore.ts` — 移植 `getDayIncomeData()`（行 411-442），累加计算折线图数据
- `src/stores/useChartStore.ts` — 移植 `getPositionRecord()`（行 443-493），累加 delta 数组

### Step 4: Hooks + 组件
- `src/hooks/usePolling.ts` — setInterval + cleanup + 立即首次调用
- 7 个展示组件（KpiCards, PositionTable, HistoryTable, BigLossTable, BalanceChart, PositionValueChart, DayIncomeChart）
- 每个组件从对应 Zustand store 读数据，纯展示

### Step 5: TradingView 集成
- `src/components/TradingViewChart.tsx` — 挂载容器 div + 初始化 widget
- TradingView datafeeds 适配器用 TS 重写（简化版，去掉 WebSocket 实时推送和历史回放）
- `index.html` 加 `<script src="/charting_library/charting_library.min.js">`

### Step 6: App 组装
- `src/App.tsx` — ConfigProvider + 两个轮询（3s 主数据 + 15min 日收入）+ 页面布局
- `src/main.tsx` — ReactDOM.createRoot 挂载
- 布局复刻 Show.js render()：标题 → KPI 卡片 → 图表区 → 大亏表 → 历史表

## 关键数据转换逻辑（必须精确移植）

### lastMinTime 计算
```
参考: react-front/src/work/constants/commonFunction.js:122-179 (turnTsToTime)
nowTs = Date.now() - 60000 → turnTsToTime(nowTs, "1m") → "YYYY-MM-DD HH:mm:00"
```

### secondOpenObjArr → historyTableArr
```
参考: react-front/src/work/constainers/Show.js:274-299
遍历 secondOpenObjArr["p"] 的 key，对每个 symbol 构建包含 p/v/c 四个周期数据的行
```

### positionRecord delta 累加
```
参考: react-front/src/work/constainers/Show.js:463-483
positionRecordObjArr 是 [positionDelta, balanceDelta, tsDelta] 数组
逐项累加得到绝对值序列，用于余额和持仓价值趋势图
```

## 验证

1. `npm run dev` 启动后浏览器可访问
2. KPI 卡片显示非零数值（如果 OSS 数据可用）
3. 余额趋势图和持仓价值趋势图正确渲染
4. 日收入图柱/线切换正常
5. 历史表 13 列均可排序
6. 持仓表显示当前持仓（如有）
7. 大亏交易表正确显示或显示"暂无数据"
8. 时间区间选择器切换后图表数据更新
9. `npm run build` 生产构建成功
10. TypeScript 编译零错误：`npx tsc --noEmit`

## 风险

1. **OSS CORS** — 旧代码设置的 `Access-Control-*` 是响应头，客户端设置无效。如果 OSS bucket 未配 CORS，fetch 会失败。备选方案：Vite dev server 配代理
2. **TradingView 版本** — 旧静态库可能与新浏览器不兼容。如果加载失败，TradingView 可降级为后续阶段
3. **OSS 数据格式** — 类型定义基于对 Show.js 的逆向推断，实际 JSON 结构可能有出入。需要在开发时对照真实响应调整

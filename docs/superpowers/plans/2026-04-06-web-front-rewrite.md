# Web Frontend Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the legacy `react-front/` (React 16 + Webpack 4) as `web-front/` using Vite + React 19 + TypeScript + antd 5 + Zustand + ECharts, preserving all dashboard functionality.

**Architecture:** Single-page app reading JSON from Cloudflare R2 via `VITE_CDN_URL` env var. Zustand stores manage data fetching and transformation. Polling hook handles 3s/15min intervals. antd provides UI components and dark/light theme switching.

**Tech Stack:** Vite, React 19, TypeScript, antd 5, Zustand, ECharts (echarts-for-react), dayjs

**Reference file:** `react-front/src/work/constainers/Show.js` — the original 839-line monolithic component containing all data fetching, transformation, and rendering logic that must be faithfully reproduced.

---

## File Structure

```
web-front/
  public/
  src/
    main.tsx                    # ReactDOM.createRoot entry
    App.tsx                     # ConfigProvider + usePolling + layout
    vite-env.d.ts               # ImportMetaEnv with VITE_CDN_URL
    types/
      index.ts                  # All TS interfaces
    api/
      cdn.ts                    # 4 fetch functions
    stores/
      useThemeStore.ts          # Dark/light + localStorage
      useQuantStore.ts          # Main data: KPI, positions, tables
      useDayIncomeStore.ts      # Day income chart data
      useChartStore.ts          # Balance/position trend data
    hooks/
      usePolling.ts             # 3s + 15min polling lifecycle
    utils/
      format.ts                 # Timestamp formatting + data transformations
    components/
      ThemeToggle.tsx           # Sun/moon switch
      KpiCards.tsx              # 5 KPI stat cards
      BalanceChart.tsx          # Balance trend line chart + range selector
      PositionValueChart.tsx    # Position value trend line chart
      DayIncomeChart.tsx        # Day income bar/line toggle chart
      BigLossTable.tsx          # Big loss trades table (6 cols)
      HistoryTable.tsx          # History data table (13 cols, sortable)
    styles/
      global.css                # Minimal global styles
  .env.example                  # VITE_CDN_URL=
  index.html
  vite.config.ts
  tsconfig.json
  tsconfig.app.json
```

---

### Task 1: Project Scaffolding

**Goal**: `web-front/` runs `npm run dev` and shows a blank page with antd configured.

**Files to create**: `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/vite-env.d.ts`, `src/styles/global.css`, `.env.example`

- [ ] **Step 1: Create project with Vite**

Run: `npm create vite@latest web-front -- --template react-ts`
Then: `cd web-front && npm install`

- [ ] **Step 2: Install dependencies**

Run: `npm install antd @ant-design/icons zustand echarts echarts-for-react dayjs`

- [ ] **Step 3: Create .env.example**

```
VITE_CDN_URL=
```

- [ ] **Step 4: Create src/vite-env.d.ts with VITE_CDN_URL type**

```typescript
/// <reference types="vite/client" />
interface ImportMetaEnv {
  readonly VITE_CDN_URL: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

- [ ] **Step 5: Create minimal App.tsx with antd ConfigProvider**

```tsx
import { ConfigProvider, theme } from 'antd'

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <div style={{ padding: 24, color: '#fff' }}>CQuant Dashboard</div>
    </ConfigProvider>
  )
}
```

- [ ] **Step 6: Create src/styles/global.css**

```css
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
#root { min-height: 100vh; }
```

- [ ] **Step 7: Update root .gitignore**

Add `web-front/node_modules/` and `web-front/dist/`.

- [ ] **Step 8: Verify and commit**

Run: `cd web-front && npm run dev` — browser shows "CQuant Dashboard" with dark background.
Run: `npx tsc --noEmit` — zero errors.

```bash
git add web-front/ .gitignore
git commit -m "feat(web-front): scaffold Vite + React 19 + TypeScript + antd 5 project"
```

---

### Task 2: Types + Utils + API Layer

**Goal**: All TypeScript interfaces, data transformation utilities, and fetch functions.

**Files to create**: `src/types/index.ts`, `src/utils/format.ts`, `src/api/cdn.ts`

- [ ] **Step 1: Create src/types/index.ts**

Define all interfaces: `QuantResponse`, `DayIncomeResponse`, `PositionRecordDelta`, `PositionItem`, `BigLossRow`, `HistoryRow`, `ChartData`, `DayIncomeData`, `SystemStatus`, `HistoryRangeType`, `DayIncomeChartType`.

Key types from Show.js analysis:
- `QuantResponse.bigLossTradeArr`: `[string, string, number, string, number, string][]` — [symbol, time, profit, percentByBalance, priceRate, direction]
- `QuantResponse.secondOpenObjArr`: `{ p: Record<string, number[]>, v: Record<string, number[]>, c: Record<string, number[]>, t: number }`
- `PositionRecordDelta`: `[number, number, number]` — [positionDelta, balanceDelta, tsDelta]

- [ ] **Step 2: Create src/utils/format.ts**

Functions:
- `getLastMinTime()`: `dayjs(Date.now() - 60000).format('YYYY-MM-DD HH:mm:00')`
- `formatTimestamp(ts: number)`: if `ts < 100_000_000_000` multiply by 1000, then `dayjs(ts).format('YYYY-MM-DD HH:mm:ss')`
- `transformBigLossArr(raw)`: map Show.js lines 261-269
- `transformHistoryArr(raw)`: map Show.js lines 277-296
- `transformPositionRecord(deltas)`: cumulative sum, Show.js lines 463-483
- `transformDayIncome(response)`: cumulative line values, Show.js lines 428-433
- `evaluateSystemStatus(systemUpdateTs, systemStatus, runTime)`: 5-min timeout check, Show.js lines 314-329

- [ ] **Step 3: Create src/api/cdn.ts**

```typescript
const cdnBase = import.meta.env.VITE_CDN_URL

export async function fetchQuantData(lastMinTime: string): Promise<QuantResponse> {
  const res = await fetch(`${cdnBase}/cQuant/${lastMinTime}.json?t=${Date.now()}`)
  return res.json()
}
// + fetchDayIncome, fetchPositionRecord, fetchInvestorData
```

Use `Date.now()` as cache buster (replaces old `Math.random()`).

- [ ] **Step 4: Verify and commit**

Run: `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/types/ web-front/src/utils/ web-front/src/api/
git commit -m "feat(web-front): add types, utils, and CDN API layer"
```

---

### Task 3: Zustand Stores (4 stores)

**Goal**: All state management with data fetch actions.

**Files to create**: `src/stores/useThemeStore.ts`, `src/stores/useQuantStore.ts`, `src/stores/useDayIncomeStore.ts`, `src/stores/useChartStore.ts`

- [ ] **Step 1: Create useThemeStore.ts**

```typescript
// isDark: boolean (default true, persisted to localStorage 'theme')
// toggle(): flip isDark, write to localStorage
```

- [ ] **Step 2: Create useQuantStore.ts**

State: `balance`, `positionValue`, `oneDayVol`, `oneDayProfit`, `allProfit`, `systemStatus`, `lastMinTime`, `bigLossRows`, `historyRows`, `historyUpdateTime`, `positionArr`

Action `fetchQuantData()`:
1. Call `api/cdn.fetchQuantData(getLastMinTime())`
2. Transform bigLossTradeArr → bigLossRows
3. Transform secondOpenObjArr → historyRows
4. Calculate allProfit = `response.todayProfit + secondOpenObjArr.p['all'][3]` (Show.js line 276+297-299)
5. Evaluate system status
6. Set all state

- [ ] **Step 3: Create useDayIncomeStore.ts**

State: `chartType` (persisted to localStorage), `data: DayIncomeData | null`
Actions: `setChartType()`, `fetchDayIncome()`

- [ ] **Step 4: Create useChartStore.ts**

State: `historyRange: HistoryRangeType` (default 'all'), `chartData: ChartData | null`
Actions: `setHistoryRange(range)` (triggers fetch), `fetchPositionRecord()`

- [ ] **Step 5: Verify and commit**

Run: `npx tsc --noEmit` — zero errors.

```bash
git add web-front/src/stores/
git commit -m "feat(web-front): add 4 Zustand stores for data management"
```

---

### Task 4: Polling Hook + App Shell

**Goal**: Automatic data fetching lifecycle and basic layout structure.

**Files to create/modify**: `src/hooks/usePolling.ts`, update `src/App.tsx`

- [ ] **Step 1: Create usePolling.ts**

```typescript
// On mount: fetch all 3 data sources
// Every 3s: if getLastMinTime() !== store.lastMinTime → fetch quant + chart
// Every 15min: fetch dayIncome
// Cleanup intervals on unmount
```

- [ ] **Step 2: Update App.tsx with theme + polling + layout shell**

```tsx
// ConfigProvider with dynamic theme based on useThemeStore.isDark
// Call usePolling() hook
// Layout: header (title + ThemeToggle) → placeholder sections for components
```

- [ ] **Step 3: Verify and commit**

Run: `npm run dev` — polling visible in browser Network tab.

```bash
git add web-front/src/hooks/ web-front/src/App.tsx
git commit -m "feat(web-front): add polling hook and app shell layout"
```

---

### Task 5: KPI Cards + Theme Toggle

**Goal**: 5 KPI cards and dark/light theme switch.

**Files to create**: `src/components/ThemeToggle.tsx`, `src/components/KpiCards.tsx`

- [ ] **Step 1: Create ThemeToggle.tsx**

antd `Button` with `SunOutlined`/`MoonOutlined` icon, reads `useThemeStore`.

- [ ] **Step 2: Create KpiCards.tsx**

5 antd `Statistic` cards in flex row:
1. "总价值" — `balance` (integer USD)
2. "当前持仓价值" — `positionValue`
3. "24小时手续费" — `oneDayVol`
4. "发布至今净利润" — `allProfit`
5. "系统状态" — conditional: normal → green check + runTime text; abnormal → status + updateTime

Match Show.js lines 633-706 layout and labels.

- [ ] **Step 3: Wire into App.tsx, verify and commit**

```bash
git add web-front/src/components/ThemeToggle.tsx web-front/src/components/KpiCards.tsx web-front/src/App.tsx
git commit -m "feat(web-front): add KPI cards and theme toggle"
```

---

### Task 6: Chart Components (3 charts)

**Goal**: Balance, position value, and day income charts.

**Files to create**: `src/components/BalanceChart.tsx`, `src/components/PositionValueChart.tsx`, `src/components/DayIncomeChart.tsx`

- [ ] **Step 1: Create BalanceChart.tsx**

ECharts line chart with:
- Data: `useChartStore.chartData.balanceArr` / `timeArr`
- Y-axis min: `chartData.minBalance`
- Above chart: antd `Select` for history range (5 options from `HISTORY_TABLE_TYPE`)
- `notMerge={true}` on ReactECharts
- Theme-aware colors via `useThemeStore.isDark`

Range labels: `{ fromLastInvestor: '参与者变化后', lastOneDay: '最近一天', lastSevenDays: '最近七天', lastOneMonth: '最近一个月', all: '全部' }`

- [ ] **Step 2: Create PositionValueChart.tsx**

Same structure as BalanceChart but plots `positionValueArr`, Y-axis min `minPositionValue`. Shares same range state (changing range in BalanceChart also updates this chart).

- [ ] **Step 3: Create DayIncomeChart.tsx**

ECharts chart with:
- Data: `useDayIncomeStore.data`
- Toggle via antd `Select`: bar("分段柱形图") / line("总和折线图")
- Bar mode: `type: 'bar'`, data = `barArr`
- Line mode: `type: 'line'`, data = `lineArr`
- Display update time

- [ ] **Step 4: Wire into App.tsx, verify and commit**

```bash
git add web-front/src/components/BalanceChart.tsx web-front/src/components/PositionValueChart.tsx web-front/src/components/DayIncomeChart.tsx web-front/src/App.tsx
git commit -m "feat(web-front): add balance, position value, and day income charts"
```

---

### Task 7: Table Components

**Goal**: BigLoss and History tables with sorting.

**Files to create**: `src/components/BigLossTable.tsx`, `src/components/HistoryTable.tsx`

- [ ] **Step 1: Create BigLossTable.tsx**

antd `Table` with 6 columns (Show.js lines 132-160):
- 时间(time), 交易对(symbol), 方向(direction), 收益金额(profit, sortable), 收益占余额比例(profitPercentByBalance, sortable), 价格波动率(priceRate)
- Sorter: numeric parse for profit and profitPercentByBalance
- Pagination: 10 per page
- Empty state: show message if no data

- [ ] **Step 2: Create HistoryTable.tsx**

antd `Table` with 13 columns (Show.js lines 53-129):
- 交易对, 昨日利润, 昨日BNB, 昨日手续费, 周利润, 周BNB, 周手续费, 月利润, 月BNB, 月手续费, 总利润, 总BNB, 总手续费
- All columns except 交易对 are sortable: `(a, b) => parseFloat(a.field) - parseFloat(b.field)`
- No pagination (`pagination={false}`)
- Header with update time from `useQuantStore.historyUpdateTime`

- [ ] **Step 3: Wire into App.tsx, verify and commit**

```bash
git add web-front/src/components/BigLossTable.tsx web-front/src/components/HistoryTable.tsx web-front/src/App.tsx
git commit -m "feat(web-front): add big loss and history data tables"
```

---

### Task 8: Final Assembly + Polish + Docs

**Goal**: Everything wired, responsive, production build works.

- [ ] **Step 1: Final App.tsx assembly**

Replace all placeholders with real components in order:
Header → KpiCards → BalanceChart → PositionValueChart → DayIncomeChart → BigLossTable → HistoryTable

Add antd `Divider` between sections. Add loading `Spin` for initial data fetch.

- [ ] **Step 2: Responsive polish**

- KPI cards: flex-wrap on narrow screens
- Tables: `scroll={{ x: true }}` for horizontal scrolling
- Charts: responsive width via `style={{ width: '100%' }}`

- [ ] **Step 3: Update CLAUDE.md**

Add `web-front/` section to Key Modules table and Build & Run Commands.

- [ ] **Step 4: Production build verification**

Run: `npm run build` — builds to `web-front/dist/`
Run: `npx tsc --noEmit` — zero TS errors

- [ ] **Step 5: Commit**

```bash
git add web-front/ CLAUDE.md
git commit -m "feat(web-front): complete dashboard rewrite with all components"
```

---

## Verification Checklist

1. `npm run dev` starts without errors
2. All 5 KPI cards show live data (if CDN configured)
3. Balance chart loads, range selector works (5 options)
4. Position value chart updates with range changes
5. Day income chart toggles bar/line
6. BigLoss table sorts, shows empty state when no data
7. History table 13 columns all sortable
8. Dark/light theme toggle works, persists across reload
9. Polling: data updates when minute changes (3s check)
10. Day income refreshes every 15 minutes
11. `npm run build` succeeds
12. `npx tsc --noEmit` zero errors

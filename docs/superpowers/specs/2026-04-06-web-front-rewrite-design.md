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

**保留：** 5 个 KPI 卡片、当前持仓表、历史数据表（13 列可排序）、大亏交易表、余额趋势图、持仓价值趋势图、日收入图（柱/线切换）、深/浅主题切换

**去除：** 登录/注册、聊天/社交、多交易所支持、Redux 样板代码、TradingView K 线图（后续独立任务）

## 数据源（全部从 R2 读取）

CDN 基础 URL 通过 `VITE_CDN_URL` 环境变量注入（`.env` 文件，不提交 git）。

| 端点 | 轮询频率 | 内容 |
|------|---------|------|
| `${VITE_CDN_URL}/cQuant/{lastMinTime}.json` | 3s 检查分钟变化 | 主数据：KPI、持仓、历史表、大亏交易、系统状态 |
| `${VITE_CDN_URL}/cQuant_day_income/data.json` | 15min | 日收入柱/线图数据 |
| `${VITE_CDN_URL}/cQuant_change/{type}Arr.json` | 随主数据 | 持仓历史：余额/持仓价值趋势图 |
| `${VITE_CDN_URL}/investor/{lastMinTime}.json` | 随主数据 | 投资者历史 |

## 布局

单列布局，从上到下：

1. **顶栏**：标题 + 主题切换按钮
2. **KPI 卡片区**（5 个）：总余额、持仓价值、24h 手续费、总利润、系统状态
3. **余额趋势图** + 时间范围选择器（投资者起始/1天/7天/1月/全部）
4. **持仓价值趋势图**
5. **日收入图**（柱/线切换）
6. **大亏交易表**（5 列：时间、币种、方向、亏损、亏损比例）
7. **历史数据表**（13 列：币种 + 4 个时间段 × 3 指标，可排序）

## 主题切换

- antd `ConfigProvider` + `theme.defaultAlgorithm` / `theme.darkAlgorithm`
- ECharts 通过 `theme` prop 切换 `'dark'` / `undefined`（light）
- 主题偏好存 `localStorage`，默认深色
- 页面顶部放切换按钮（太阳/月亮图标）

## 项目结构

```
web-front/
  public/                       # 静态资源
  src/
    main.tsx                    # 入口
    App.tsx                     # ConfigProvider + 轮询 + 布局
    types/
      index.ts                  # 所有 TS 接口
    api/
      cdn.ts                    # 4 个 fetch 函数
    stores/
      useQuantStore.ts          # 主数据：KPI、持仓、历史表、大亏交易
      useDayIncomeStore.ts      # 日收入
      useChartStore.ts          # 持仓历史（余额/持仓价值趋势）
      useThemeStore.ts          # 主题切换 + localStorage 持久化
    hooks/
      usePolling.ts             # 通用轮询 hook
    utils/
      format.ts                 # turnTsToTime (dayjs) + 数字格式化
    components/
      ThemeToggle.tsx           # 主题切换按钮
      KpiCards.tsx              # 5 个 KPI 卡片
      PositionTable.tsx         # 当前持仓表
      HistoryTable.tsx          # 历史数据表 (13 列可排序)
      BigLossTable.tsx          # 大亏交易表
      BalanceChart.tsx          # 余额趋势折线图
      PositionValueChart.tsx    # 持仓价值趋势折线图
      DayIncomeChart.tsx        # 日收入柱/线切换图
    styles/
      global.css                # 全局样式
  .env.example                  # VITE_CDN_URL=
  index.html
  vite.config.ts
  tsconfig.json
```

## 关键数据转换逻辑（从 Show.js 精确移植）

### lastMinTime 计算
```typescript
// nowTs = Date.now() - 60000
// lastMinTime = dayjs(nowTs).format('YYYY-MM-DD HH:mm:00')
```

### secondOpenObjArr → historyTableArr
```
遍历 response.secondOpenObjArr["p"] 的 key
对每个 symbol，从 p/v/c 中提取 [yesterday, week, month, all] 四个周期数据
生成 13 列行对象
```

### positionRecordObjArr 累加
```
输入：[positionDelta, balanceDelta, tsDelta][] 数组
逐项累加得到绝对值序列：timeArr, balanceArr, positionValueArr
记录 minBalance 和 minPositionValue 用于图表 Y 轴最小值
```

### dayIncomeData 累加
```
输入：[date, value][] 数组
dayIncomeValueBarArr = 每日值
dayIncomeValueLineArr = 累加值（折线图）
```

## 环境变量

```
# web-front/.env（不提交 git）
VITE_CDN_URL=https://your-cdn-domain.com
```

```
# web-front/.env.example（提交 git）
VITE_CDN_URL=
```

## 验证

1. `npm run dev` 启动后浏览器可访问
2. KPI 卡片显示非零数值（如果 CDN 数据可用）
3. 余额趋势图和持仓价值趋势图正确渲染
4. 日收入图柱/线切换正常
5. 历史表 13 列均可排序
6. 大亏交易表正确显示或显示"暂无数据"
7. 时间范围选择器切换后图表数据更新
8. 深/浅主题切换正常，刷新后保持
9. `npm run build` 生产构建成功
10. `npx tsc --noEmit` 零 TypeScript 错误

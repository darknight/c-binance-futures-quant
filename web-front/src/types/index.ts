// --- API Response Types ---

export interface DashboardSummaryResponse {
  s: string
  balance: number
  positionValue: number
  oneDayVol: number
  oneDayProfit: number
  systemStatus: string
  systemUpdateTs: number
  runTime: number
  t: number
}

export interface ProfitBySymbolResponse {
  s: string
  p: Record<string, number[]> // [yesterday, week, month, all]
  c: Record<string, number[]>
  v: Record<string, number[]>
  t: number
}

export interface BigLossTradeItem {
  symbol: string
  time: string
  profit: number
  profitPercentByBalance: string
  priceRate: string
  direction: string
}

export interface BigLossResponse {
  s: string
  d: BigLossTradeItem[]
}

export interface DayIncomeItem {
  allNetProfit: number
  dayBeginTime: string
  dayEndTime: string
  binanceCommission: number
  netProfit: number
  profit: number
  zjyCommission: number
}

export interface DayIncomeResponse {
  s: string
  d: DayIncomeItem[]
  u: number
}

export interface PositionRecordItem {
  positionAmt: number
  positionValue: number
  balance: number
  time: string
  profit: number
  commission: number
  makerCommission: number
  price: null
  entryPrice: null
  unrealizedProfit: number
  maintMargin: null
}

export interface PositionRecordResponse {
  s: string
  d: PositionRecordItem[]
  symbol: string
}

// --- Frontend Display Types ---

export interface HistoryRow {
  key: string
  symbol: string
  yesterdayProfit: string
  yesterdayVol: string
  yesterdayCommission: string
  weekProfit: string
  weekVol: string
  weekCommission: string
  monthProfit: string
  monthVol: string
  monthCommission: string
  allProfit: string
  allVol: string
  allCommission: string
}

export interface ChartData {
  timeArr: string[]
  balanceArr: number[]
  positionValueArr: number[]
  minBalance: number
  minPositionValue: number
}

export interface DayIncomeChartData {
  timeArr: string[]
  barArr: number[]
  lineArr: number[]
  updateTime: string
}

export type ChartRangeType = 'fromLastInvestor' | 'lastOneDay' | 'lastSevenDays' | 'lastOneMonth' | 'all'

export type DayIncomeChartType = 'bar' | 'line'

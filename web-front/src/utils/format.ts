import dayjs from 'dayjs'
import type {
  ProfitBySymbolResponse,
  HistoryRow,
  DayIncomeItem,
  DayIncomeChartData,
  PositionRecordItem,
  ChartData,
  ChartRangeType,
} from '../types'

export function formatTimestamp(ts: number): string {
  const normalized = ts < 100_000_000_000 ? ts * 1000 : ts
  return dayjs(normalized).format('YYYY-MM-DD HH:mm:ss')
}

export function transformProfitToHistoryRows(resp: ProfitBySymbolResponse): HistoryRow[] {
  const rows: HistoryRow[] = []
  for (const key of Object.keys(resp.p)) {
    const pArr = resp.p[key] || [0, 0, 0, 0]
    const vArr = resp.v[key] || [0, 0, 0, 0]
    const cArr = resp.c[key] || [0, 0, 0, 0]
    rows.push({
      key,
      symbol: key === 'all' ? '全部' : key,
      yesterdayProfit: pArr[0].toFixed(6),
      yesterdayVol: vArr[0].toFixed(6),
      yesterdayCommission: cArr[0].toFixed(6),
      weekProfit: pArr[1].toFixed(3),
      weekVol: vArr[1].toFixed(3),
      weekCommission: cArr[1].toFixed(3),
      monthProfit: pArr[2].toFixed(3),
      monthVol: vArr[2].toFixed(3),
      monthCommission: cArr[2].toFixed(3),
      allProfit: pArr[3].toFixed(3),
      allVol: vArr[3].toFixed(3),
      allCommission: cArr[3].toFixed(3),
    })
  }
  return rows
}

export function transformDayIncome(items: DayIncomeItem[]): DayIncomeChartData {
  const timeArr: string[] = []
  const barArr: number[] = []
  const lineArr: number[] = []
  let cumulative = 0
  for (const item of items) {
    timeArr.push(item.dayBeginTime)
    barArr.push(item.netProfit)
    cumulative += item.netProfit
    lineArr.push(cumulative)
  }
  return { timeArr, barArr, lineArr, updateTime: '' }
}

export function transformPositionRecord(items: PositionRecordItem[]): ChartData {
  const timeArr: string[] = []
  const balanceArr: number[] = []
  const positionValueArr: number[] = []
  let minBalance = Infinity
  let minPositionValue = Infinity

  for (const item of items) {
    timeArr.push(item.time)
    balanceArr.push(item.balance)
    positionValueArr.push(item.positionValue)
    if (item.balance < minBalance) minBalance = item.balance
    if (item.positionValue < minPositionValue) minPositionValue = item.positionValue
  }

  return { timeArr, balanceArr, positionValueArr, minBalance, minPositionValue }
}

export function getRangeTimestamps(range: ChartRangeType): { beginTs: number; endTs: number } {
  const now = Math.floor(Date.now() / 1000)
  const endTs = now
  let beginTs: number
  switch (range) {
    case 'lastOneDay':
      beginTs = now - 86400
      break
    case 'lastSevenDays':
      beginTs = now - 7 * 86400
      break
    case 'lastOneMonth':
      beginTs = now - 30 * 86400
      break
    case 'all':
    default:
      beginTs = 0
      break
  }
  return { beginTs, endTs }
}

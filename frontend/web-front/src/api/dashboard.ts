import type {
  DashboardSummaryResponse,
  ProfitBySymbolResponse,
  BigLossResponse,
  DayIncomeResponse,
  PositionRecordResponse,
} from '../types'

const apiBase = import.meta.env.VITE_API_URL

async function post<T>(path: string, body?: Record<string, string>): Promise<T> {
  const formData = new URLSearchParams()
  if (body) {
    for (const [key, value] of Object.entries(body)) {
      formData.append(key, value)
    }
  }
  const res = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData,
  })
  return res.json()
}

export function fetchDashboardSummary(): Promise<DashboardSummaryResponse> {
  return post('/get_dashboard_summary')
}

export function fetchProfitBySymbol(): Promise<ProfitBySymbolResponse> {
  return post('/get_profit_by_symbol')
}

export function fetchBigLossTrades(): Promise<BigLossResponse> {
  return post('/get_big_loss_trades')
}

export function fetchDayIncome(): Promise<DayIncomeResponse> {
  return post('/get_day_income')
}

export function fetchPositionRecord(
  symbol: string,
  beginTs: number,
  endTs: number,
): Promise<PositionRecordResponse> {
  return post('/get_position_record', {
    symbol,
    beginTs: String(beginTs),
    endTs: String(endTs),
  })
}

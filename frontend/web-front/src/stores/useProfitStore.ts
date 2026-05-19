import { create } from 'zustand'
import { fetchProfitBySymbol } from '../api/dashboard'
import { transformProfitToHistoryRows } from '../utils/format'
import type { HistoryRow, ProfitBySymbolResponse } from '../types'

interface ProfitState {
  profitData: ProfitBySymbolResponse | null
  historyRows: HistoryRow[]
  historyUpdateTime: string
  fetchProfit: () => Promise<void>
}

export const useProfitStore = create<ProfitState>((set) => ({
  profitData: null,
  historyRows: [],
  historyUpdateTime: '',
  fetchProfit: async () => {
    try {
      const data = await fetchProfitBySymbol()
      if (data.s === 'ok') {
        const rows = transformProfitToHistoryRows(data)
        const updateTime = data.t
          ? new Date(data.t).toLocaleString('zh-CN', { timeZone: 'UTC' })
          : ''
        set({ profitData: data, historyRows: rows, historyUpdateTime: updateTime })
      }
    } catch {
      // silently fail, will retry on next poll
    }
  },
}))

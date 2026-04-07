import { create } from 'zustand'
import { fetchPositionRecord } from '../api/dashboard'
import { transformPositionRecord, getRangeTimestamps } from '../utils/format'
import type { ChartData, ChartRangeType } from '../types'

interface ChartState {
  range: ChartRangeType
  chartData: ChartData | null
  setRange: (range: ChartRangeType) => void
  fetchPositionRecord: () => Promise<void>
}

export const useChartStore = create<ChartState>((set, get) => ({
  range: 'all',
  chartData: null,
  setRange: (range) => {
    set({ range })
    get().fetchPositionRecord()
  },
  fetchPositionRecord: async () => {
    try {
      const { beginTs, endTs } = getRangeTimestamps(get().range)
      const data = await fetchPositionRecord('ALL', beginTs, endTs)
      if (data.s === 'ok') {
        const chartData = transformPositionRecord(data.d)
        set({ chartData })
      }
    } catch {
      // silently fail
    }
  },
}))

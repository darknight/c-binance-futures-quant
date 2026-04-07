import { create } from 'zustand'
import { fetchDayIncome } from '../api/dashboard'
import { transformDayIncome } from '../utils/format'
import type { DayIncomeChartData, DayIncomeChartType } from '../types'

interface DayIncomeState {
  chartType: DayIncomeChartType
  chartData: DayIncomeChartData | null
  setChartType: (type: DayIncomeChartType) => void
  fetchDayIncome: () => Promise<void>
}

export const useDayIncomeStore = create<DayIncomeState>((set) => ({
  chartType: (localStorage.getItem('dayIncomeChartType') as DayIncomeChartType) || 'bar',
  chartData: null,
  setChartType: (type) => {
    localStorage.setItem('dayIncomeChartType', type)
    set({ chartType: type })
  },
  fetchDayIncome: async () => {
    try {
      const data = await fetchDayIncome()
      if (data.s === 'ok') {
        const chartData = transformDayIncome(data.d)
        set({ chartData })
      }
    } catch {
      // silently fail
    }
  },
}))

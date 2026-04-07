import { create } from 'zustand'
import { fetchDashboardSummary } from '../api/dashboard'

interface DashboardState {
  balance: number
  positionValue: number
  oneDayVol: number
  oneDayProfit: number
  systemStatus: string
  systemUpdateTs: number
  runTime: number
  loading: boolean
  fetchSummary: () => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set) => ({
  balance: 0,
  positionValue: 0,
  oneDayVol: 0,
  oneDayProfit: 0,
  systemStatus: '',
  systemUpdateTs: 0,
  runTime: 0,
  loading: true,
  fetchSummary: async () => {
    try {
      const data = await fetchDashboardSummary()
      if (data.s === 'ok') {
        set({
          balance: data.balance,
          positionValue: data.positionValue,
          oneDayVol: data.oneDayVol,
          oneDayProfit: data.oneDayProfit,
          systemStatus: data.systemStatus,
          systemUpdateTs: data.systemUpdateTs,
          runTime: data.runTime,
          loading: false,
        })
      }
    } catch {
      set({ loading: false })
    }
  },
}))

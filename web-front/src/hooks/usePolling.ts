import { useEffect, useRef } from 'react'
import { useDashboardStore } from '../stores/useDashboardStore'
import { useProfitStore } from '../stores/useProfitStore'
import { useDayIncomeStore } from '../stores/useDayIncomeStore'
import { useChartStore } from '../stores/useChartStore'

export function usePolling() {
  const fetchSummary = useDashboardStore((s) => s.fetchSummary)
  const fetchProfit = useProfitStore((s) => s.fetchProfit)
  const fetchDayIncome = useDayIncomeStore((s) => s.fetchDayIncome)
  const fetchPositionRecord = useChartStore((s) => s.fetchPositionRecord)
  const mounted = useRef(false)

  useEffect(() => {
    if (mounted.current) return
    mounted.current = true

    // Initial fetch all
    fetchSummary()
    fetchProfit()
    fetchDayIncome()
    fetchPositionRecord()

    // KPI: 10s
    const summaryTimer = setInterval(fetchSummary, 10_000)
    // Profit table: 5min
    const profitTimer = setInterval(fetchProfit, 5 * 60_000)
    // Day income: 15min
    const dayIncomeTimer = setInterval(fetchDayIncome, 15 * 60_000)
    // Position record: 5min
    const chartTimer = setInterval(fetchPositionRecord, 5 * 60_000)

    return () => {
      clearInterval(summaryTimer)
      clearInterval(profitTimer)
      clearInterval(dayIncomeTimer)
      clearInterval(chartTimer)
    }
  }, [fetchSummary, fetchProfit, fetchDayIncome, fetchPositionRecord])
}

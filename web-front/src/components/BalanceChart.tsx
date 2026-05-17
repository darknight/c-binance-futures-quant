import { Select } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useChartStore } from '../stores/useChartStore'
import { useThemeStore } from '../stores/useThemeStore'
import type { ChartRangeType } from '../types'

const RANGE_OPTIONS: { value: ChartRangeType; label: string }[] = [
  { value: 'fromLastInvestor', label: '参与者变化后' },
  { value: 'lastOneDay', label: '最近一天' },
  { value: 'lastSevenDays', label: '最近七天' },
  { value: 'lastOneMonth', label: '最近一个月' },
  { value: 'all', label: '全部' },
]

export default function BalanceChart() {
  const { range, setRange, chartData } = useChartStore()
  const isDark = useThemeStore((s) => s.isDark)

  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: chartData?.timeArr ?? [] },
    yAxis: { type: 'value' as const, min: chartData?.minBalance },
    series: [{ data: chartData?.balanceArr ?? [], type: 'line' }],
  }

  return (
    <div>
      <Select
        value={range}
        onChange={(val) => setRange(val)}
        style={{ width: 200, marginBottom: 16 }}
        options={RANGE_OPTIONS}
      />
      <ReactECharts
        option={option}
        notMerge
        theme={isDark ? 'dark' : undefined}
        style={{ width: '100%', height: 400 }}
      />
    </div>
  )
}

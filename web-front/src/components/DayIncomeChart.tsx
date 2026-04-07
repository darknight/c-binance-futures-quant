import { Select } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useDayIncomeStore } from '../stores/useDayIncomeStore'
import { useThemeStore } from '../stores/useThemeStore'
import type { DayIncomeChartType } from '../types'

const TYPE_OPTIONS: { value: DayIncomeChartType; label: string }[] = [
  { value: 'bar', label: '分段柱形图' },
  { value: 'line', label: '总和折线图' },
]

export default function DayIncomeChart() {
  const { chartType, setChartType, chartData } = useDayIncomeStore()
  const isDark = useThemeStore((s) => s.isDark)

  const dataArr = chartType === 'bar' ? chartData?.barArr : chartData?.lineArr

  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: chartData?.timeArr ?? [] },
    yAxis: { type: 'value' as const },
    series: [{ data: dataArr ?? [], type: chartType }],
  }

  return (
    <div>
      <Select
        value={chartType}
        onChange={(val) => setChartType(val)}
        style={{ width: 200, marginBottom: 16 }}
        options={TYPE_OPTIONS}
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

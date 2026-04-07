import ReactECharts from 'echarts-for-react'
import { useChartStore } from '../stores/useChartStore'
import { useThemeStore } from '../stores/useThemeStore'

export default function PositionValueChart() {
  const chartData = useChartStore((s) => s.chartData)
  const isDark = useThemeStore((s) => s.isDark)

  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: chartData?.timeArr ?? [] },
    yAxis: { type: 'value' as const, min: chartData?.minPositionValue },
    series: [{ data: chartData?.positionValueArr ?? [], type: 'line' }],
  }

  return (
    <ReactECharts
      option={option}
      notMerge
      theme={isDark ? 'dark' : undefined}
      style={{ width: '100%', height: 400 }}
    />
  )
}

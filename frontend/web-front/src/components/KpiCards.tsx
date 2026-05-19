import { Card, Statistic, Space, Tag } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { useDashboardStore } from '../stores/useDashboardStore'
import { useProfitStore } from '../stores/useProfitStore'
import { formatTimestamp } from '../utils/format'

export default function KpiCards() {
  const { balance, positionValue, oneDayVol, oneDayProfit, systemStatus, systemUpdateTs, runTime } =
    useDashboardStore()
  const profitData = useProfitStore((s) => s.profitData)

  const historicalProfit = profitData?.p?.['all']?.[3] ?? 0
  const allProfit = oneDayProfit + historicalProfit

  const isNormal =
    systemUpdateTs > 0 && Date.now() / 1000 - systemUpdateTs < 5 * 60

  return (
    <Space size={16} wrap>
      <Card>
        <Statistic title="总价值" value={Math.round(balance)} suffix="USD" />
      </Card>
      <Card>
        <Statistic title="当前持仓价值" value={Math.round(positionValue)} suffix="USD" />
      </Card>
      <Card>
        <Statistic title="24小时手续费" value={Math.round(oneDayVol)} suffix="USD" />
      </Card>
      <Card>
        <Statistic title="发布至今净利润" value={Math.round(allProfit)} suffix="USD" />
      </Card>
      <Card>
        <Statistic
          title="系统状态"
          valueRender={() =>
            isNormal ? (
              <span>
                <CheckOutlined style={{ color: 'green', marginRight: 8 }} />
                近一分钟检索全币种 {runTime} 次
              </span>
            ) : systemUpdateTs === 0 ? (
              <Tag>加载中</Tag>
            ) : (
              <span>
                <Tag color="red">
                  {systemStatus === 'stopByAccountBalanceValue'
                    ? '亏损停机'
                    : systemStatus === 'bug'
                      ? '系统意外崩溃'
                      : systemStatus === 'maintain'
                        ? '维护中'
                        : systemStatus}
                </Tag>
                {formatTimestamp(systemUpdateTs)}
              </span>
            )
          }
        />
      </Card>
    </Space>
  )
}

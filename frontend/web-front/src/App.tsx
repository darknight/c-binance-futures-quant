import { ConfigProvider, theme, Layout, Typography, Divider, Spin } from 'antd'
import { useThemeStore } from './stores/useThemeStore'
import { useDashboardStore } from './stores/useDashboardStore'
import { usePolling } from './hooks/usePolling'
import ThemeToggle from './components/ThemeToggle'
import KpiCards from './components/KpiCards'
import BalanceChart from './components/BalanceChart'
import PositionValueChart from './components/PositionValueChart'
import DayIncomeChart from './components/DayIncomeChart'
import BigLossTable from './components/BigLossTable'
import HistoryTable from './components/HistoryTable'

const { Header, Content } = Layout

export default function App() {
  const isDark = useThemeStore((s) => s.isDark)
  const loading = useDashboardStore((s) => s.loading)
  usePolling()

  return (
    <ConfigProvider
      theme={{ algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm }}
    >
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 24px',
          }}
        >
          <Typography.Title level={3} style={{ margin: 0, color: isDark ? '#fff' : undefined }}>
            CQuant Dashboard
          </Typography.Title>
          <ThemeToggle />
        </Header>
        <Content style={{ padding: 24, maxWidth: 1400, margin: '0 auto', width: '100%' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 100 }}>
              <Spin size="large" />
            </div>
          ) : (
            <>
              <KpiCards />

              <Divider>余额和持仓价值</Divider>
              <BalanceChart />
              <PositionValueChart />

              <Divider>净利润日变化</Divider>
              <DayIncomeChart />

              <Divider>大额亏损交易</Divider>
              <BigLossTable />

              <Divider>历史数据</Divider>
              <HistoryTable />
            </>
          )}
        </Content>
      </Layout>
    </ConfigProvider>
  )
}

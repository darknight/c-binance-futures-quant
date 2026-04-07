import { ConfigProvider, theme, Layout, Typography } from 'antd'
import { useThemeStore } from './stores/useThemeStore'
import { usePolling } from './hooks/usePolling'
import ThemeToggle from './components/ThemeToggle'

const { Header, Content } = Layout

export default function App() {
  const isDark = useThemeStore((s) => s.isDark)
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
        <Content style={{ padding: 24 }}>
          {/* Components will be wired in final assembly */}
        </Content>
      </Layout>
    </ConfigProvider>
  )
}

import { ConfigProvider, theme } from 'antd'

export default function App() {
  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <div style={{ padding: 24, color: '#fff' }}>CQuant Dashboard</div>
    </ConfigProvider>
  )
}

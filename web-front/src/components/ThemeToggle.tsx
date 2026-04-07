import { Button } from 'antd'
import { SunOutlined, MoonOutlined } from '@ant-design/icons'
import { useThemeStore } from '../stores/useThemeStore'

export default function ThemeToggle() {
  const { isDark, toggle } = useThemeStore()
  return (
    <Button
      type="text"
      icon={isDark ? <SunOutlined /> : <MoonOutlined />}
      onClick={toggle}
      style={{ color: isDark ? '#fff' : undefined }}
    />
  )
}

import { create } from 'zustand'

interface ThemeState {
  isDark: boolean
  toggle: () => void
}

export const useThemeStore = create<ThemeState>((set) => ({
  isDark: localStorage.getItem('theme') !== 'light',
  toggle: () =>
    set((state) => {
      const next = !state.isDark
      localStorage.setItem('theme', next ? 'dark' : 'light')
      return { isDark: next }
    }),
}))

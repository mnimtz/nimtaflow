import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type ThemeStore = {
  dark: boolean
  toggle: () => void
}

export const useTheme = create<ThemeStore>()(
  persist(
    (set) => ({
      dark: window.matchMedia('(prefers-color-scheme: dark)').matches,
      toggle: () =>
        set((s) => {
          const next = !s.dark
          document.documentElement.classList.toggle('dark', next)
          return { dark: next }
        }),
    }),
    { name: 'photoflow-theme' },
  ),
)

// Apply on load
const stored = JSON.parse(localStorage.getItem('photoflow-theme') || '{}')
if (stored?.state?.dark) document.documentElement.classList.add('dark')

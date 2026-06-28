import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Night between 19:00 and 07:00 → dark; daytime → light. */
function isNight(): boolean {
  const h = new Date().getHours()
  return h < 7 || h >= 19
}

type ThemeStore = {
  dark: boolean
  auto: boolean            // follow time of day until the user manually toggles
  toggle: () => void       // manual override (turns auto off)
  setAuto: (b: boolean) => void
}

function apply(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
}

export const useTheme = create<ThemeStore>()(
  persist(
    (set, get) => ({
      dark: isNight(),
      auto: true,
      toggle: () =>
        set(() => {
          const next = !get().dark
          apply(next)
          return { dark: next, auto: false }   // manual choice sticks
        }),
      setAuto: (b: boolean) =>
        set(() => {
          const dark = b ? isNight() : get().dark
          apply(dark)
          return { auto: b, dark }
        }),
    }),
    { name: 'photoflow-theme' },
  ),
)

// Apply on load. Existing users who previously toggled manually keep their stored
// choice (they have `dark` but no `auto` flag → treat as manual). Fresh users → auto.
const st = JSON.parse(localStorage.getItem('photoflow-theme') || '{}')?.state
const auto: boolean = st?.auto ?? (st?.dark === undefined)
const dark: boolean = auto ? isNight() : !!st?.dark
apply(dark)
useTheme.setState({ dark, auto })

// While the tab stays open, follow the day/night boundary (only in auto mode).
setInterval(() => {
  const s = useTheme.getState()
  if (s.auto) {
    const d = isNight()
    if (d !== s.dark) { apply(d); useTheme.setState({ dark: d }) }
  }
}, 15 * 60 * 1000)

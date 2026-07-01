import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Ambient-KI-Assistent — gemeinsamer Zustand.
 * `resultIds` = aktives Ergebnis-Set, das die Galerie (und später Karte etc.) als
 * Filter anzeigt. Der Assistent schiebt seine Antwort hier rein statt in die Chat-Blase.
 * `enabled` = Master-Schalter aus den Einstellungen (persistiert).
 */
type AssistantStore = {
  open: boolean
  resultIds: number[] | null
  resultQuery: string | null
  enabled: boolean
  setOpen: (b: boolean) => void
  toggle: () => void
  setResult: (ids: number[], query: string) => void
  clearResult: () => void
  setEnabled: (b: boolean) => void
}

export const useAssistant = create<AssistantStore>()(
  persist(
    (set) => ({
      open: false,
      resultIds: null,
      resultQuery: null,
      enabled: true,
      setOpen: (b) => set({ open: b }),
      toggle: () => set((s) => ({ open: !s.open })),
      setResult: (ids, query) => set({ resultIds: ids, resultQuery: query }),
      clearResult: () => set({ resultIds: null, resultQuery: null }),
      setEnabled: (b) => set({ enabled: b }),
    }),
    { name: 'pf-assistant', partialize: (s) => ({ enabled: s.enabled }) },
  ),
)

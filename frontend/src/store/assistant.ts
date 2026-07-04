import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type AssistantGalleryFilter = {
  personId?: number
  dateFrom?: string
  dateTo?: string
  mediaType?: string
  label: string
}

export type AssistantMapFilter = {
  personId?: number
  dateFrom?: string
  dateTo?: string
  label: string
}

type AssistantStore = {
  open: boolean
  resultIds: number[] | null
  resultQuery: string | null
  galleryFilter: AssistantGalleryFilter | null
  mapFilter: AssistantMapFilter | null
  enabled: boolean
  setOpen: (b: boolean) => void
  toggle: () => void
  setResult: (ids: number[], query: string) => void
  setGalleryFilter: (f: AssistantGalleryFilter | null) => void
  setMapFilter: (f: AssistantMapFilter | null) => void
  clearResult: () => void
  setEnabled: (b: boolean) => void
}

export const useAssistant = create<AssistantStore>()(
  persist(
    (set) => ({
      open: false,
      resultIds: null,
      resultQuery: null,
      galleryFilter: null,
      mapFilter: null,
      enabled: true,
      setOpen: (b) => set({ open: b }),
      toggle: () => set((s) => ({ open: !s.open })),
      setResult: (ids, query) => set({ resultIds: ids, resultQuery: query }),
      setGalleryFilter: (f) => set({ galleryFilter: f }),
      setMapFilter: (f) => set({ mapFilter: f }),
      clearResult: () => set({ resultIds: null, resultQuery: null, galleryFilter: null, mapFilter: null }),
      setEnabled: (b) => set({ enabled: b }),
    }),
    { name: 'pf-assistant', partialize: (s) => ({ enabled: s.enabled }) },
  ),
)

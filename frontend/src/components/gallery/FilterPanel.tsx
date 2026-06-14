import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, Camera, Calendar, Heart, Video, MapPin, SlidersHorizontal } from 'lucide-react'
import { api, type PhotoStats } from '../../lib/api'

export type Filters = {
  search: string
  dateFrom: string
  dateTo: string
  camera: string
  mediaType: '' | 'photo' | 'video' | 'raw'
  favorites: boolean
  hasGps: boolean | null
}

export const DEFAULT_FILTERS: Filters = {
  search: '',
  dateFrom: '',
  dateTo: '',
  camera: '',
  mediaType: '',
  favorites: false,
  hasGps: null,
}

function isActive(f: Filters) {
  return f.search || f.dateFrom || f.dateTo || f.camera || f.mediaType || f.favorites || f.hasGps !== null
}

type Props = {
  filters: Filters
  onChange: (f: Filters) => void
}

export default function FilterPanel({ filters, onChange }: Props) {
  const [open, setOpen] = useState(false)

  const { data: stats } = useQuery<PhotoStats>({
    queryKey: ['photo-stats'],
    queryFn: () => api.get('/photos/stats').then(r => r.data),
    staleTime: 60_000,
  })

  const active = isActive(filters)

  function set(partial: Partial<Filters>) {
    onChange({ ...filters, ...partial })
  }

  function clear() {
    onChange(DEFAULT_FILTERS)
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          active
            ? 'bg-indigo-600 text-white'
            : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
        }`}
      >
        <SlidersHorizontal size={15} />
        Filter
        {active && (
          <span className="bg-white/30 rounded-full w-4 h-4 flex items-center justify-center text-[10px] font-bold">
            {[filters.search, filters.dateFrom || filters.dateTo, filters.camera, filters.mediaType, filters.favorites, filters.hasGps !== null].filter(Boolean).length}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 z-30 w-72 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl p-4 space-y-4">

            {/* Search */}
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Suche</label>
              <input
                value={filters.search}
                onChange={e => set({ search: e.target.value })}
                placeholder="Beschreibung, Ort..."
                className="mt-1 w-full px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            {/* Date range */}
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                <Calendar size={12} /> Zeitraum
              </label>
              <div className="flex gap-2 mt-1">
                <input type="date" value={filters.dateFrom} onChange={e => set({ dateFrom: e.target.value })}
                  className="flex-1 px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                <span className="text-gray-400 self-center">–</span>
                <input type="date" value={filters.dateTo} onChange={e => set({ dateTo: e.target.value })}
                  className="flex-1 px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              </div>
            </div>

            {/* Camera */}
            {stats && stats.cameras.length > 0 && (
              <div>
                <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                  <Camera size={12} /> Kamera
                </label>
                <select
                  value={filters.camera}
                  onChange={e => set({ camera: e.target.value })}
                  className="mt-1 w-full px-3 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="">Alle Kameras</option>
                  {stats.cameras.map(c => (
                    <option key={c.model} value={c.model}>{c.model} ({c.count})</option>
                  ))}
                </select>
              </div>
            )}

            {/* Media type */}
            <div>
              <label className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide flex items-center gap-1">
                <Video size={12} /> Medientyp
              </label>
              <div className="flex gap-2 mt-1 flex-wrap">
                {(['', 'photo', 'video', 'raw'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => set({ mediaType: t })}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      filters.mediaType === t
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                    }`}
                  >
                    {t === '' ? 'Alle' : t === 'photo' ? 'Fotos' : t === 'video' ? 'Videos' : 'RAW'}
                  </button>
                ))}
              </div>
            </div>

            {/* Toggles */}
            <div className="space-y-2">
              <label className="flex items-center gap-3 cursor-pointer">
                <div
                  onClick={() => set({ favorites: !filters.favorites })}
                  className={`w-9 h-5 rounded-full transition-colors relative ${filters.favorites ? 'bg-red-500' : 'bg-gray-200 dark:bg-gray-700'}`}
                >
                  <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${filters.favorites ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </div>
                <span className="text-sm text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                  <Heart size={13} className="text-red-400" /> Nur Favoriten
                  {stats && <span className="text-xs text-gray-400">({stats.favorites})</span>}
                </span>
              </label>

              <label className="flex items-center gap-3 cursor-pointer">
                <div
                  onClick={() => set({ hasGps: filters.hasGps === true ? null : true })}
                  className={`w-9 h-5 rounded-full transition-colors relative ${filters.hasGps === true ? 'bg-indigo-500' : 'bg-gray-200 dark:bg-gray-700'}`}
                >
                  <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${filters.hasGps === true ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </div>
                <span className="text-sm text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                  <MapPin size={13} className="text-green-500" /> Mit GPS
                  {stats && <span className="text-xs text-gray-400">({stats.with_gps})</span>}
                </span>
              </label>
            </div>

            {/* Clear */}
            {active && (
              <button
                onClick={clear}
                className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
              >
                <X size={14} /> Filter zurücksetzen
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

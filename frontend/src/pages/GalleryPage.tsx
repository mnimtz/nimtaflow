import { useState, useEffect } from 'react'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid, Clock, Sparkles, Search, X, Heart, Archive, Trash2 } from 'lucide-react'
import { api, type Photo, type TimelineGroup, type PhotoStats } from '../lib/api'
import JustifiedGrid from '../components/gallery/JustifiedGrid'
import TimelineView from '../components/gallery/TimelineView'
import PhotoLightbox from '../components/gallery/PhotoLightbox'
import FilterPanel, { DEFAULT_FILTERS, type Filters } from '../components/gallery/FilterPanel'

type ViewMode = 'grid' | 'timeline' | 'memories'

type PhotoListResponse = {
  total: number
  page: number
  limit: number
  items: Photo[]
}

type MemoryGroup = {
  years_ago: number
  date: string
  photos: Photo[]
}

const ROW_HEIGHT = 200
const PAGE_SIZE = 100

function useRowHeight() {
  const [h, setH] = useState(() => (typeof window !== 'undefined' && window.innerWidth < 640 ? 120 : 200))
  useEffect(() => {
    const onResize = () => setH(window.innerWidth < 640 ? 120 : 200)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return h
}

function buildFilterParams(f: Filters) {
  const p: Record<string, string> = {}
  if (f.search) p.search = f.search
  if (f.dateFrom) p.date_from = f.dateFrom
  if (f.dateTo) p.date_to = f.dateTo
  if (f.camera) p.camera = f.camera
  if (f.mediaType) p.media_type = f.mediaType
  if (f.favorites) p.favorites = 'true'
  if (f.hasGps === true) p.has_gps = 'true'
  return p
}

function MemoriesView({ onPhotoClick }: { onPhotoClick: (photos: Photo[], i: number) => void }) {
  const { data } = useQuery<MemoryGroup[]>({
    queryKey: ['memories'],
    queryFn: () => api.get('/photos/memories').then(r => r.data),
    staleTime: 3600_000,
  })

  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <Sparkles size={48} className="text-gray-300 dark:text-gray-600 mb-4" />
        <p className="text-gray-500 dark:text-gray-400 text-sm">Keine Erinnerungen gefunden.</p>
        <p className="text-gray-400 dark:text-gray-600 text-xs mt-1">
          Fotos mit Datum von früheren Jahren erscheinen hier.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-10">
      {data.map(group => (
        <div key={group.years_ago}>
          <div className="flex items-center gap-3 mb-3">
            <Sparkles size={16} className="text-yellow-400" />
            <h2 className="font-semibold text-gray-900 dark:text-white">
              Vor {group.years_ago} {group.years_ago === 1 ? 'Jahr' : 'Jahren'}
            </h2>
            <span className="text-sm text-gray-400">
              {new Date(group.date).toLocaleDateString('de', { day: 'numeric', month: 'long', year: 'numeric' })}
            </span>
          </div>
          <div
            className="grid gap-1"
            style={{
              gridTemplateColumns: `repeat(auto-fill, minmax(${Math.floor(ROW_HEIGHT * 1.33)}px, 1fr))`,
              gridAutoRows: `${ROW_HEIGHT}px`,
            }}
          >
            {group.photos.map((photo, i) => (
              <div
                key={photo.id}
                className="relative overflow-hidden rounded bg-gray-100 dark:bg-gray-800 cursor-pointer group"
                onClick={() => onPhotoClick(group.photos, i)}
              >
                <img
                  src={`/api/photos/${photo.id}/thumbnail?size=medium`}
                  alt={photo.filename}
                  className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  loading="lazy"
                />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function GalleryPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [lightbox, setLightbox] = useState<{ photos: Photo[]; index: number } | null>(null)
  const [searchDraft, setSearchDraft] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [lastIndex, setLastIndex] = useState<number | null>(null)
  const rowHeight = useRowHeight()
  const qc = useQueryClient()

  const filterParams = buildFilterParams(filters)

  const infiniteQuery = useInfiniteQuery({
    queryKey: ['photos', 'grid', filterParams],
    queryFn: ({ pageParam = 1 }) =>
      api.get('/photos', { params: { ...filterParams, page: pageParam, limit: PAGE_SIZE } })
        .then(r => r.data as PhotoListResponse),
    getNextPageParam: (last) =>
      last.page * last.limit < last.total ? last.page + 1 : undefined,
    initialPageParam: 1,
    enabled: viewMode === 'grid',
  })

  const timelineQuery = useQuery<TimelineGroup[]>({
    queryKey: ['photos', 'timeline', filterParams],
    queryFn: () =>
      api.get('/photos/timeline', { params: { ...filterParams, limit_per_group: 40 } })
        .then(r => r.data),
    enabled: viewMode === 'timeline',
  })

  const { data: stats } = useQuery<PhotoStats>({
    queryKey: ['photo-stats'],
    queryFn: () => api.get('/photos/stats').then(r => r.data),
    staleTime: 60_000,
  })

  const favMutation = useMutation({
    mutationFn: (id: number) => api.patch(`/photos/${id}/favorite`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['photos'] }),
  })

  const batchMutation = useMutation({
    mutationFn: (action: string) => api.post('/photos/batch', { ids: [...selected], action }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['photos'] })
      clearSelection()
    },
  })

  const allGridPhotos = infiniteQuery.data?.pages.flatMap(p => p.items) ?? []
  const total = infiniteQuery.data?.pages[0]?.total ?? 0

  function clearSelection() { setSelected(new Set()); setLastIndex(null) }

  function toggleSelect(photo: Photo, index: number, shift: boolean) {
    setSelected(prev => {
      const next = new Set(prev)
      if (shift && lastIndex !== null) {
        const [a, b] = [Math.min(lastIndex, index), Math.max(lastIndex, index)]
        for (let i = a; i <= b; i++) if (allGridPhotos[i]) next.add(allGridPhotos[i].id)
      } else if (next.has(photo.id)) {
        next.delete(photo.id)
      } else {
        next.add(photo.id)
      }
      return next
    })
    setLastIndex(index)
  }

  // Esc clears selection
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') clearSelection() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const selectionCount = selected.size

  function submitSearch(e: React.FormEvent) {
    e.preventDefault()
    setFilters(f => ({ ...f, search: searchDraft }))
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="shrink-0 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm px-4 py-2 flex items-center gap-3 flex-wrap">
        {/* View tabs */}
        <div className="flex rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5">
          {([
            { id: 'grid', icon: LayoutGrid, label: 'Raster' },
            { id: 'timeline', icon: Clock, label: 'Timeline' },
            { id: 'memories', icon: Sparkles, label: 'Erinnerungen' },
          ] as const).map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => setViewMode(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === id
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>

        {/* Search */}
        {viewMode !== 'memories' && (
          <form onSubmit={submitSearch} className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={searchDraft}
              onChange={e => setSearchDraft(e.target.value)}
              placeholder="Suchen..."
              className="pl-8 pr-7 py-1.5 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500 w-48"
            />
            {searchDraft && (
              <button
                type="button"
                onClick={() => { setSearchDraft(''); setFilters(f => ({ ...f, search: '' })) }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                <X size={13} />
              </button>
            )}
          </form>
        )}

        <div className="flex-1" />

        {stats && viewMode === 'grid' && total > 0 && (
          <span className="text-xs text-gray-400 hidden md:block">
            {total.toLocaleString('de')} Fotos
          </span>
        )}

        {viewMode !== 'memories' && (
          <FilterPanel filters={filters} onChange={setFilters} />
        )}
      </div>

      {/* Gallery area */}
      <div className="flex-1 overflow-y-auto p-4">
        {viewMode === 'grid' && (
          <>
            {allGridPhotos.length === 0 && !infiniteQuery.isLoading && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <LayoutGrid size={48} className="text-gray-300 dark:text-gray-600 mb-4" />
                <p className="text-gray-500 dark:text-gray-400 text-sm">Keine Fotos gefunden.</p>
              </div>
            )}
            <JustifiedGrid
              photos={allGridPhotos}
              rowHeight={rowHeight}
              gap={4}
              onPhotoClick={(_, i) => setLightbox({ photos: allGridPhotos, index: i })}
              onFavoriteToggle={photo => favMutation.mutate(photo.id)}
              selectable
              selected={selected}
              onToggleSelect={toggleSelect}
            />
            {infiniteQuery.hasNextPage && (
              <div className="flex justify-center py-6">
                <button
                  onClick={() => infiniteQuery.fetchNextPage()}
                  disabled={infiniteQuery.isFetchingNextPage}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-50 transition-colors"
                >
                  {infiniteQuery.isFetchingNextPage ? 'Lade...' : 'Mehr laden'}
                </button>
              </div>
            )}
          </>
        )}

        {viewMode === 'timeline' && (
          <>
            {timelineQuery.isLoading && (
              <div className="flex justify-center py-12 text-gray-400 text-sm">Lade Timeline...</div>
            )}
            {timelineQuery.data && (
              <TimelineView
                groups={timelineQuery.data}
                rowHeight={ROW_HEIGHT}
                onPhotoClick={(_, allPhotos, i) => setLightbox({ photos: allPhotos, index: i })}
                onFavoriteToggle={photo => favMutation.mutate(photo.id)}
              />
            )}
            {timelineQuery.data?.length === 0 && !timelineQuery.isLoading && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <Clock size={48} className="text-gray-300 dark:text-gray-600 mb-4" />
                <p className="text-gray-500 dark:text-gray-400 text-sm">Keine Fotos in der Timeline.</p>
              </div>
            )}
          </>
        )}

        {viewMode === 'memories' && (
          <MemoriesView onPhotoClick={(photos, i) => setLightbox({ photos, index: i })} />
        )}
      </div>

      {/* Selection action bar */}
      {selectionCount > 0 && (
        <div className="fixed bottom-20 md:bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-1 px-2 py-1.5 rounded-2xl bg-zinc-900/95 dark:bg-zinc-800/95 backdrop-blur-md shadow-2xl ring-1 ring-white/10 animate-[fadeIn_180ms_ease]">
          <button onClick={clearSelection} className="p-2 rounded-xl text-zinc-300 hover:bg-white/10 transition-colors" title="Auswahl aufheben">
            <X size={18} />
          </button>
          <span className="px-2 text-sm font-semibold text-white tabular-nums">{selectionCount}</span>
          <div className="w-px h-6 bg-white/15 mx-1" />
          <button onClick={() => batchMutation.mutate('favorite')} disabled={batchMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title="Favorisieren">
            <Heart size={16} /> <span className="hidden sm:inline">Favorit</span>
          </button>
          <button onClick={() => batchMutation.mutate('archive')} disabled={batchMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title="Archivieren">
            <Archive size={16} /> <span className="hidden sm:inline">Archiv</span>
          </button>
          <button onClick={() => batchMutation.mutate('trash')} disabled={batchMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-red-300 hover:bg-red-500/20 transition-colors disabled:opacity-50" title="In Papierkorb">
            <Trash2 size={16} /> <span className="hidden sm:inline">Papierkorb</span>
          </button>
        </div>
      )}

      {/* Lightbox */}
      {lightbox && (
        <PhotoLightbox
          photos={lightbox.photos}
          initialIndex={lightbox.index}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  )
}

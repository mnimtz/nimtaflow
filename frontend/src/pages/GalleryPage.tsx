import { useState, useEffect, useRef } from 'react'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid, Sparkles, Search, X, Heart, Archive, Trash2, Calendar, Minus, Plus, Rows3, Columns3, FolderPlus } from 'lucide-react'
import { api, thumbUrl, type Photo, type PhotoStats } from '../lib/api'
import Gallery, { type LayoutMode } from '../components/gallery/Gallery'
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import DateScrubber from '../components/gallery/DateScrubber'
import FilterPanel, { DEFAULT_FILTERS, type Filters } from '../components/gallery/FilterPanel'
import { Modal, useToast } from '../components/ui/dialogs'

type ViewMode = 'grid' | 'memories'

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
const isMobile = () => typeof window !== 'undefined' && window.innerWidth < 640

function buildFilterParams(f: Filters) {
  const p: Record<string, string> = {}
  if (f.search) p.search = f.search
  if (f.dateFrom) p.date_from = f.dateFrom
  if (f.dateTo) p.date_to = f.dateTo
  if (f.camera) p.camera = f.camera
  if (f.mediaType) p.media_type = f.mediaType
  if (f.favorites) p.favorites = 'true'
  if (f.hasGps === true) p.has_gps = 'true'
  if (f.personId != null) p.person_id = String(f.personId)
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
                  src={thumbUrl(photo, 'medium')}
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
  const [lightbox, setLightbox] = useState<{ photos: Photo[]; index: number; live?: boolean } | null>(null)
  const [albumModal, setAlbumModal] = useState(false)
  const [scrollEl, setScrollEl] = useState<HTMLElement | null>(null)
  const [searchDraft, setSearchDraft] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [lastIndex, setLastIndex] = useState<number | null>(null)
  const [library, setLibrary] = useState<'library' | 'favorites' | 'archive' | 'trash'>('library')
  const [sort, setSort] = useState<'newest' | 'oldest' | 'added' | 'name'>('newest')
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE)
  const [zoom, setZoom] = useState<number>(() => Number(localStorage.getItem('gallery.zoom')) || (isMobile() ? 140 : 210))
  const [groupBy, setGroupBy] = useState<'none' | 'day' | 'month'>(() => (localStorage.getItem('gallery.groupBy') as any) || 'day')
  const [layout, setLayout] = useState<LayoutMode>(() => (localStorage.getItem('gallery.layout') as LayoutMode) || 'rows')
  useEffect(() => { localStorage.setItem('gallery.zoom', String(zoom)) }, [zoom])
  useEffect(() => { localStorage.setItem('gallery.groupBy', groupBy) }, [groupBy])
  useEffect(() => { localStorage.setItem('gallery.layout', layout) }, [layout])
  const rowHeight = zoom
  const qc = useQueryClient()

  const filterParams = { ...buildFilterParams(filters), view: library, sort }

  const infiniteQuery = useInfiniteQuery({
    queryKey: ['photos', 'grid', filterParams, pageSize],
    queryFn: ({ pageParam = 1 }) =>
      api.get('/photos', { params: { ...filterParams, page: pageParam, limit: pageSize } })
        .then(r => r.data as PhotoListResponse),
    getNextPageParam: (last) =>
      last.page * last.limit < last.total ? last.page + 1 : undefined,
    initialPageParam: 1,
    enabled: viewMode === 'grid',
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

  function selectMany(ids: number[], on: boolean) {
    setSelected(prev => { const n = new Set(prev); ids.forEach(id => on ? n.add(id) : n.delete(id)); return n })
  }

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

  // Infinite scroll: auto-load next page when the sentinel scrolls into view
  const sentinelRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting && infiniteQuery.hasNextPage && !infiniteQuery.isFetchingNextPage) {
        infiniteQuery.fetchNextPage()
      }
    }, { rootMargin: '600px' })
    io.observe(el)
    return () => io.disconnect()
  }, [infiniteQuery.hasNextPage, infiniteQuery.isFetchingNextPage, viewMode])

  const selectionCount = selected.size

  function submitSearch(e: React.FormEvent) {
    e.preventDefault()
    setFilters(f => ({ ...f, search: searchDraft }))
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="relative z-40 shrink-0 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm px-4 py-2 flex items-center gap-3 flex-wrap">
        {/* Library views */}
        <div className="flex rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5">
          {([
            { id: 'library', icon: LayoutGrid, label: 'Bibliothek' },
            { id: 'favorites', icon: Heart, label: 'Favoriten' },
            { id: 'archive', icon: Archive, label: 'Archiv' },
            { id: 'trash', icon: Trash2, label: 'Papierkorb' },
          ] as const).map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => { setLibrary(id); clearSelection(); if (id !== 'library') setViewMode('grid') }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                library === id
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
              title={label}
            >
              <Icon size={14} />
              <span className="hidden md:inline">{label}</span>
            </button>
          ))}
        </div>

        {/* View tabs — only meaningful in the main library */}
        {library === 'library' && (
          <div className="flex rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5">
            {([
              { id: 'grid', icon: LayoutGrid, label: 'Galerie' },
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
        )}

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

        {viewMode === 'grid' && (
          <>
            {/* Layout mode */}
            <div className="flex rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5" title="Layout">
              {([['rows', Rows3], ['masonry', Columns3]] as const).map(([id, Icon]) => (
                <button key={id} onClick={() => setLayout(id)}
                  className={`p-1.5 rounded-md transition-colors ${layout === id ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}`}>
                  <Icon size={14} />
                </button>
              ))}
            </div>
            {/* Group by date */}
            <div className="flex items-center gap-1.5" title="Nach Datum gruppieren">
              <Calendar size={14} className="text-gray-400" />
              <select value={groupBy} onChange={e => setGroupBy(e.target.value as any)}
                className="px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="day">Nach Tag</option>
                <option value="month">Nach Monat</option>
                <option value="none">Ohne Gruppen</option>
              </select>
            </div>
            {/* Zoom / density */}
            <div className="flex items-center gap-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-1" title="Bildgröße">
              <button onClick={() => setZoom(z => Math.max(110, z - 30))} className="p-1 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"><Minus size={13} /></button>
              <input type="range" min={110} max={360} step={10} value={zoom} onChange={e => setZoom(Number(e.target.value))} className="hidden sm:block w-20 accent-indigo-500" />
              <button onClick={() => setZoom(z => Math.min(360, z + 30))} className="p-1 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"><Plus size={13} /></button>
            </div>
            <select value={sort} onChange={e => setSort(e.target.value as any)}
              title="Sortierung"
              className="px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="newest">Neueste zuerst</option>
              <option value="oldest">Älteste zuerst</option>
              <option value="added">Zuletzt hinzugefügt</option>
              <option value="name">Dateiname</option>
            </select>
            <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
              title="Bilder pro Ladevorgang"
              className="hidden sm:block px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={250}>250</option>
            </select>
          </>
        )}

        {viewMode !== 'memories' && (
          <FilterPanel filters={filters} onChange={setFilters} />
        )}
      </div>

      {/* Gallery area */}
      <div ref={setScrollEl} className="relative flex-1 overflow-y-auto p-4">
        {viewMode === 'grid' && groupBy !== 'none' && sort !== 'name' && sort !== 'added' && <DateScrubber scrollEl={scrollEl} />}
        {viewMode === 'grid' && (
          <>
            {allGridPhotos.length === 0 && !infiniteQuery.isLoading && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <LayoutGrid size={48} className="text-gray-300 dark:text-gray-600 mb-4" />
                <p className="text-gray-500 dark:text-gray-400 text-sm">Keine Fotos gefunden.</p>
              </div>
            )}
            <Gallery
              photos={allGridPhotos}
              layout={layout}
              rowHeight={rowHeight}
              groupBy={(sort === 'name' || sort === 'added') ? 'none' : groupBy}
              onPhotoClick={i => setLightbox({ photos: allGridPhotos, index: i, live: true })}
              onFavoriteToggle={photo => favMutation.mutate(photo.id)}
              selectable
              selected={selected}
              onToggleSelect={toggleSelect}
              onSelectMany={selectMany}
            />
            {/* Infinite scroll sentinel */}
            <div ref={sentinelRef} className="h-12 flex items-center justify-center">
              {infiniteQuery.isFetchingNextPage && (
                <span className="text-xs text-gray-400 flex items-center gap-2">
                  <span className="w-3 h-3 border-2 border-gray-300 border-t-indigo-500 rounded-full animate-spin" /> Lade weitere…
                </span>
              )}
              {!infiniteQuery.hasNextPage && allGridPhotos.length > 0 && (
                <span className="text-xs text-gray-300 dark:text-gray-600">Alle {total.toLocaleString('de')} Fotos geladen</span>
              )}
            </div>
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
          {library === 'trash' ? (
            <button onClick={() => batchMutation.mutate('untrash')} disabled={batchMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-emerald-300 hover:bg-emerald-500/20 transition-colors disabled:opacity-50" title="Wiederherstellen">
              <Archive size={16} /> <span className="hidden sm:inline">Wiederherstellen</span>
            </button>
          ) : library === 'archive' ? (
            <button onClick={() => batchMutation.mutate('unarchive')} disabled={batchMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title="Aus Archiv">
              <Archive size={16} /> <span className="hidden sm:inline">Aus Archiv</span>
            </button>
          ) : (
            <>
              <button onClick={() => batchMutation.mutate('favorite')} disabled={batchMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title="Favorisieren">
                <Heart size={16} /> <span className="hidden sm:inline">Favorit</span>
              </button>
              <button onClick={() => batchMutation.mutate('archive')} disabled={batchMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title="Archivieren">
                <Archive size={16} /> <span className="hidden sm:inline">Archiv</span>
              </button>
            </>
          )}
          {library !== 'trash' && (
            <button onClick={() => setAlbumModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors" title="Zu Album hinzufügen">
              <FolderPlus size={16} /> <span className="hidden sm:inline">Album</span>
            </button>
          )}
          {library !== 'trash' && (
            <button onClick={() => batchMutation.mutate('trash')} disabled={batchMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-red-300 hover:bg-red-500/20 transition-colors disabled:opacity-50" title="In Papierkorb">
              <Trash2 size={16} /> <span className="hidden sm:inline">Papierkorb</span>
            </button>
          )}
          <button
            onClick={() => { if (window.confirm(`${selected.size} Medien endgültig löschen? Dateien werden entfernt – nicht umkehrbar.`)) batchMutation.mutate('delete') }}
            disabled={batchMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-red-400 hover:bg-red-500/25 transition-colors disabled:opacity-50" title="Endgültig löschen">
            <Trash2 size={16} /> <span className="hidden sm:inline">Löschen</span>
          </button>
        </div>
      )}

      {albumModal && (
        <AddToAlbumModal photoIds={[...selected]} onClose={() => setAlbumModal(false)}
          onDone={() => { setAlbumModal(false); clearSelection() }} />
      )}

      {/* Lightbox */}
      {lightbox && (
        <GalleryLightbox
          photos={lightbox.live ? allGridPhotos : lightbox.photos}
          index={lightbox.index}
          onClose={() => setLightbox(null)}
          onFavorite={p => favMutation.mutate(p.id)}
          hasMore={lightbox.live ? infiniteQuery.hasNextPage : false}
          onLoadMore={lightbox.live ? () => infiniteQuery.fetchNextPage() : undefined}
        />
      )}
    </div>
  )
}

function AddToAlbumModal({ photoIds, onClose, onDone }: { photoIds: number[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const { data: albums = [] } = useQuery<any[]>({ queryKey: ['albums'], queryFn: () => api.get('/albums').then(r => r.data) })
  const manual = albums.filter(a => a.album_type === 'manual')
  const done = () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast(`${photoIds.length} Foto(s) hinzugefügt`, 'success'); onDone() }
  const addTo = useMutation({ mutationFn: (id: number) => api.post(`/albums/${id}/photos`, { photo_ids: photoIds }), onSuccess: done })
  const create = useMutation({
    mutationFn: async () => { const a = await api.post('/albums', { name: newName.trim(), album_type: 'manual' }); await api.post(`/albums/${a.data.id}/photos`, { photo_ids: photoIds }) },
    onSuccess: done,
  })
  return (
    <Modal open onClose={onClose} title={`${photoIds.length} Foto(s) zu Album`}>
      <div className="flex gap-2 mb-4">
        <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Neues Album…"
          onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) create.mutate() }}
          className="flex-1 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        <button onClick={() => create.mutate()} disabled={!newName.trim() || create.isPending}
          className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">Erstellen</button>
      </div>
      <div className="max-h-72 overflow-y-auto space-y-1">
        {manual.length === 0 ? (
          <p className="text-sm text-zinc-500 text-center py-3">Noch keine manuellen Alben — oben eines anlegen.</p>
        ) : manual.map(a => (
          <button key={a.id} onClick={() => addTo.mutate(a.id)} disabled={addTo.isPending}
            className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-left disabled:opacity-50">
            <div className="w-10 h-10 rounded-lg overflow-hidden bg-zinc-200 dark:bg-zinc-800 shrink-0">
              {a.cover_photo_id && <img src={thumbUrl({ id: a.cover_photo_id }, 'small')} className="w-full h-full object-cover" />}
            </div>
            <span className="text-sm text-zinc-900 dark:text-white flex-1 truncate">{a.name}</span>
            <span className="text-xs text-zinc-500">{a.photo_count ?? ''}</span>
          </button>
        ))}
      </div>
    </Modal>
  )
}

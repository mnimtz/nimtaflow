import { useState, useEffect, useRef, useMemo } from 'react'
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { LayoutGrid, Sparkles, Search, X, Heart, Archive, Trash2, Calendar, CalendarRange, Minus, Plus, Rows3, Columns3, FolderPlus, Play } from 'lucide-react'
import { api, thumbUrl, type Photo, type PhotoStats } from '../lib/api'
import Gallery, { type LayoutMode } from '../components/gallery/Gallery'
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import DateScrubber from '../components/gallery/DateScrubber'
import FilterPanel, { DEFAULT_FILTERS, type Filters } from '../components/gallery/FilterPanel'
import { Modal, useToast } from '../components/ui/dialogs'
import { useT } from '../i18n'
import { useAssistant } from '../store/assistant'

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
const PAGE_SIZE = 150
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
  const { t } = useT()
  const { data } = useQuery<MemoryGroup[]>({
    queryKey: ['memories'],
    queryFn: () => api.get('/photos/memories').then(r => r.data),
    staleTime: 3600_000,
  })

  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <Sparkles size={48} className="text-gray-300 dark:text-gray-600 mb-4" />
        <p className="text-gray-500 dark:text-gray-400 text-sm">{t('gallery.memories.empty')}</p>
        <p className="text-gray-400 dark:text-gray-600 text-xs mt-1 max-w-xs">
          {t('gallery.memories.emptyHint')}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-12 pb-12">
      {data.map(group => (
        <section key={group.years_ago}>
          <div className="flex items-center gap-3 mb-4">
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-pink-500 text-white shrink-0 shadow-sm">
              <div className="text-center leading-none">
                <div className="text-xl font-bold">{group.years_ago}</div>
                <div className="text-[9px] uppercase tracking-wide opacity-90">{group.years_ago === 1 ? t('gallery.memories.yearSingular') : t('gallery.memories.yearPlural')}</div>
              </div>
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white truncate">
                {group.years_ago === 1 ? t('gallery.memories.todayOneYear') : t('gallery.memories.todayYears', { n: group.years_ago })}
              </h2>
              <p className="text-sm text-gray-500">
                {new Date(group.date).toLocaleDateString('de', { day: 'numeric', month: 'long', year: 'numeric' })}
                {' · '}{group.photos.length} {group.photos.length === 1 ? t('gallery.memories.photoSingular') : t('gallery.memories.photoPlural')}
              </p>
            </div>
          </div>
          <div
            className="grid gap-1.5"
            style={{
              gridTemplateColumns: `repeat(auto-fill, minmax(${Math.floor(ROW_HEIGHT * 1.33)}px, 1fr))`,
              gridAutoRows: `${ROW_HEIGHT}px`,
            }}
          >
            {group.photos.map((photo, i) => (
              <div
                key={photo.id}
                className="relative overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800 cursor-pointer group"
                onClick={() => onPhotoClick(group.photos, i)}
              >
                <img
                  src={thumbUrl(photo, 'medium')}
                  alt={photo.filename}
                  className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                  loading="lazy"
                />
                {photo.is_video && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="bg-black/45 rounded-full p-2 group-hover:bg-black/60 transition">
                      <Play size={16} className="text-white" fill="white" />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}

export default function GalleryPage() {
  const { t } = useT()
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
  const [jumpMonth, setJumpMonth] = useState<string | null>(null)
  const [zoom, setZoom] = useState<number>(() => Number(localStorage.getItem('gallery.zoom')) || (isMobile() ? 140 : 210))
  const [groupBy, setGroupBy] = useState<'none' | 'day' | 'month'>(() => (localStorage.getItem('gallery.groupBy') as any) || 'day')
  const [layout, setLayout] = useState<LayoutMode>(() => (localStorage.getItem('gallery.layout') as LayoutMode) || 'rows')
  const [showTimeline, setShowTimeline] = useState<boolean>(() => (localStorage.getItem('gallery.timeline') ?? 'true') === 'true')
  useEffect(() => { localStorage.setItem('gallery.timeline', String(showTimeline)) }, [showTimeline])
  useEffect(() => { localStorage.setItem('gallery.groupBy', groupBy) }, [groupBy])
  useEffect(() => { localStorage.setItem('gallery.layout', layout) }, [layout])
  // Zoom-Slider produziert bei jeder Bewegung viele Werte — kein Sinn jedesmal
  // synchronen storage-Write zu machen. 200ms Debounce hält den Slider flüssig.
  useEffect(() => {
    const h = setTimeout(() => localStorage.setItem('gallery.zoom', String(zoom)), 200)
    return () => clearTimeout(h)
  }, [zoom])
  const rowHeight = zoom
  const qc = useQueryClient()

  // Ambient-Assistent: aktives Ergebnis-Set filtert die Galerie auf genau diese Fotos.
  const asstIds = useAssistant(s => s.resultIds)
  const asstQuery = useAssistant(s => s.resultQuery)
  const asstClear = useAssistant(s => s.clearResult)
  const galleryFilter = useAssistant(s => s.galleryFilter)
  const setGalleryFilter = useAssistant(s => s.setGalleryFilter)
  const asstActive = !!(asstIds && asstIds.length)

  const filterParams = {
    ...buildFilterParams(filters), view: library, sort,
    ...(asstActive ? { ids: asstIds!.join(',') } : {}),
    ...(galleryFilter && !asstActive ? {
      ...(galleryFilter.personId != null ? { person_id: String(galleryFilter.personId) } : {}),
      ...(galleryFilter.dateFrom ? { date_from: galleryFilter.dateFrom } : {}),
      ...(galleryFilter.dateTo ? { date_to: galleryFilter.dateTo } : {}),
      ...(galleryFilter.mediaType ? { media_type: galleryFilter.mediaType } : {}),
    } : {}),
  }

  const infiniteQuery = useInfiniteQuery({
    queryKey: ['photos', 'grid', filterParams, pageSize],
    queryFn: ({ pageParam = 1, signal }) =>
      api.get('/photos', {
        params: { ...filterParams, page: pageParam, limit: pageSize },
        signal,   // React-Query cancelt alte Requests bei Filter-Wechsel/Unmount
      })
        .then(r => r.data as PhotoListResponse),
    // Nächste Seite laden, wenn die letzte VOLL war (total wird ab Seite 2 nicht mehr
    // gezählt → -1). Eine nicht-volle Seite ist das Ende.
    getNextPageParam: (last) =>
      last.items.length >= last.limit ? last.page + 1 : undefined,
    initialPageParam: 1,
    enabled: viewMode === 'grid',
  })


  const { data: stats } = useQuery<PhotoStats>({
    queryKey: ['photo-stats'],
    queryFn: () => api.get('/photos/stats').then(r => r.data),
    staleTime: 60_000,
  })

  // Timeline-Buckets (Monats-Zählungen) für den Datum-Scrubber — bewusst OHNE Datums-
  // filter, damit die Leiste immer die GESAMTE Historie der aktuellen Ansicht/Person
  // kennt und man überall hinspringen kann.
  const bucketParams = useMemo(() => {
    const p: Record<string, string> = { view: library }
    if (asstActive) p.ids = asstIds!.join(',')
    if (filters.search) p.search = filters.search
    if (filters.camera) p.camera = filters.camera
    if (filters.mediaType) p.media_type = filters.mediaType
    if (filters.favorites) p.favorites = 'true'
    if (filters.hasGps === true) p.has_gps = 'true'
    if (filters.personId != null) p.person_id = String(filters.personId)
    if (!asstActive && galleryFilter) {
      if (galleryFilter.personId != null) p.person_id = String(galleryFilter.personId)
      if (galleryFilter.mediaType) p.media_type = galleryFilter.mediaType
    }
    return p
  }, [library, asstActive, asstIds, filters.search, filters.camera, filters.mediaType, filters.favorites, filters.hasGps, filters.personId, galleryFilter])

  const showScrubber = viewMode === 'grid' && groupBy !== 'none' && sort !== 'name' && sort !== 'added'
  const { data: bucketData } = useQuery<{ buckets: { month: string; count: number }[]; total: number }>({
    queryKey: ['photo-buckets', bucketParams],
    queryFn: () => api.get('/photos/timeline/buckets', { params: bucketParams }).then(r => r.data),
    enabled: showScrubber,
    staleTime: 60_000,
  })

  function jumpToMonth(month: string) {
    const [y, m] = month.split('-').map(Number)
    const last = new Date(y, m, 0).getDate()   // letzter Tag des Monats
    setJumpMonth(month)
    setFilters(f => ({ ...f, dateTo: `${month}-${String(last).padStart(2, '0')}` }))
    scrollEl?.scrollTo({ top: 0 })
  }
  function clearJump() {
    setJumpMonth(null)
    setFilters(f => ({ ...f, dateTo: '' }))
  }

  // Optimistic Update statt kompletter Refetch: Favorit-Klick auf einem
  // Foto in Seite 12 einer 25-Seiten-Galerie hat vorher ALLE Seiten neu geladen
  // (dank Prefix-Match auf ['photos']). Jetzt: nur die einzelne Photo-Row in
  // allen Cache-Einträgen togglen — kein Netzwerk-Refetch.
  const favMutation = useMutation({
    mutationFn: (id: number) => api.patch(`/photos/${id}/favorite`),
    onMutate: async (id: number) => {
      const cache = qc.getQueriesData<{ pages: PhotoListResponse[] }>({ queryKey: ['photos'] })
      cache.forEach(([key, data]) => {
        if (!data?.pages) return
        qc.setQueryData(key, {
          ...data,
          pages: data.pages.map(pg => ({
            ...pg,
            items: pg.items.map(p =>
              p.id === id ? { ...p, is_favorite: !p.is_favorite } : p,
            ),
          })),
        })
      })
    },
  })

  const batchMutation = useMutation({
    mutationFn: (action: string) => api.post('/photos/batch', { ids: [...selected], action }),
    onSuccess: () => {
      // Batch-Ops (archive, trash, delete) verändern Sichtbarkeit → hier ist
      // ein Refetch unvermeidlich, aber wir invalidieren spezifischer: nur die
      // Grid-Query, nicht z.B. photo-stats/photo-buckets in einem Zug.
      qc.invalidateQueries({ queryKey: ['photos', 'grid'] })
      clearSelection()
    },
  })

  // Nur neu flachklopfen, wenn wirklich eine Seite dazukam (nicht bei jedem Render) —
  // spart O(n)-Arbeit beim Scrollen/Nachladen.
  const allGridPhotos = useMemo(
    () => infiniteQuery.data?.pages.flatMap(p => p.items) ?? [],
    [infiniteQuery.data?.pages],
  )
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
    }, { rootMargin: '3500px' })
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
      {/* Ambient-Assistent: aktives Ergebnis-Set */}
      {asstActive && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-indigo-600/10 border-b border-indigo-500/30 text-sm">
          <Sparkles size={15} className="text-indigo-500 shrink-0" />
          <span className="text-zinc-700 dark:text-zinc-200 truncate">{t('gallery.assistantResults')} <span className="font-medium">„{asstQuery}"</span></span>
          <button onClick={() => asstClear()} className="ml-auto flex items-center gap-1 text-indigo-600 dark:text-indigo-300 hover:underline shrink-0">
            <X size={14} /> {t('gallery.assistantClear')}
          </button>
        </div>
      )}
      {/* Assistent-Galerie-Filter (person/datum ohne ID-Set) */}
      {!asstActive && galleryFilter && (
        <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-indigo-600/10 border-b border-indigo-500/30 text-sm">
          <Sparkles size={15} className="text-indigo-500 shrink-0" />
          <span className="text-zinc-700 dark:text-zinc-200 truncate">
            {t('gallery.assistantResults')} <span className="font-medium">{galleryFilter.label}</span>
          </span>
          <button onClick={() => setGalleryFilter(null)} className="ml-auto flex items-center gap-1 text-indigo-600 dark:text-indigo-300 hover:underline shrink-0">
            <X size={14} /> {t('gallery.assistantClear')}
          </button>
        </div>
      )}
      {/* Toolbar */}
      <div className="relative z-40 shrink-0 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm px-4 py-2 flex items-center gap-3 flex-wrap">
        {/* Library views */}
        <div className="flex rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5">
          {([
            { id: 'library', icon: LayoutGrid, label: t('gallery.library') },
            { id: 'favorites', icon: Heart, label: t('gallery.favorites') },
            { id: 'archive', icon: Archive, label: t('gallery.archive') },
            { id: 'trash', icon: Trash2, label: t('gallery.trash') },
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
              { id: 'grid', icon: LayoutGrid, label: t('gallery.viewGallery') },
              { id: 'memories', icon: Sparkles, label: t('gallery.viewMemories') },
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
              placeholder={t('gallery.searchPlaceholder')}
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
            {t('gallery.photosCount', { n: total.toLocaleString('de') })}
          </span>
        )}

        {viewMode === 'grid' && (
          <>
            {/* Layout mode */}
            <div className="flex rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5" title={t('gallery.layoutTitle')}>
              {([['rows', Rows3, t('gallery.layoutJustified')], ['masonry', Columns3, t('gallery.layoutMasonry')]] as const).map(([id, Icon, tip]) => (
                <button key={id} onClick={() => setLayout(id)} title={tip}
                  className={`p-1.5 rounded-md transition-colors ${layout === id ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}`}>
                  <Icon size={14} />
                </button>
              ))}
            </div>
            {/* Group by date */}
            <div className="flex items-center gap-1.5" title={t('gallery.groupByDate')}>
              <Calendar size={14} className="text-gray-400" />
              <select value={groupBy} onChange={e => setGroupBy(e.target.value as any)}
                className="px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="day">{t('gallery.groupByDay')}</option>
                <option value="month">{t('gallery.groupByMonth')}</option>
                <option value="none">{t('gallery.groupByNone')}</option>
              </select>
            </div>
            {/* Zeitleiste an/aus (Jahres-Leiste rechts zum schnellen Springen) */}
            {showScrubber && (
              <button onClick={() => setShowTimeline(v => !v)} title="Zeitleiste (Jahres-Sprung) ein/aus"
                className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border transition-colors ${showTimeline
                  ? 'border-indigo-500 text-indigo-600 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/30'
                  : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}`}>
                <CalendarRange size={14} /> <span className="hidden lg:inline">Zeitleiste</span>
              </button>
            )}
            {/* Zoom / density */}
            <div className="flex items-center gap-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-1" title={t('gallery.imageSize')}>
              <button onClick={() => setZoom(z => Math.max(110, z - 30))} className="p-1 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"><Minus size={13} /></button>
              <input type="range" min={110} max={360} step={10} value={zoom} onChange={e => setZoom(Number(e.target.value))} className="hidden sm:block w-20 accent-indigo-500" />
              <button onClick={() => setZoom(z => Math.min(360, z + 30))} className="p-1 text-gray-500 hover:text-gray-800 dark:hover:text-gray-200"><Plus size={13} /></button>
            </div>
            <select value={sort} onChange={e => setSort(e.target.value as any)}
              title={t('gallery.sortTitle')}
              className="px-2 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="newest">{t('gallery.sortNewest')}</option>
              <option value="oldest">{t('gallery.sortOldest')}</option>
              <option value="added">{t('gallery.sortAdded')}</option>
              <option value="name">{t('gallery.sortName')}</option>
            </select>
            <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}
              title={t('gallery.perLoadTitle')}
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
      <div ref={setScrollEl} className={`relative flex-1 overflow-y-auto p-4 ${showScrubber && showTimeline ? 'md:pr-14' : ''}`}>
        {showScrubber && showTimeline && <DateScrubber scrollEl={scrollEl} buckets={bucketData?.buckets} onJump={jumpToMonth} />}
        {jumpMonth && filters.dateTo && (
          <div className="sticky top-0 z-40 flex justify-center pointer-events-none">
            <button onClick={clearJump}
              className="pointer-events-auto mt-1 flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-600 text-white text-xs font-medium shadow-lg hover:bg-indigo-500">
              <Calendar size={13} />
              ab {new Date(jumpMonth + '-01').toLocaleDateString('de', { month: 'long', year: 'numeric' })}
              <X size={13} className="opacity-80" /> zu heute
            </button>
          </div>
        )}
        {viewMode === 'grid' && (
          <>
            {allGridPhotos.length === 0 && !infiniteQuery.isLoading && (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <LayoutGrid size={48} className="text-gray-300 dark:text-gray-600 mb-4" />
                <p className="text-gray-500 dark:text-gray-400 text-sm">{t('gallery.empty')}</p>
              </div>
            )}
            <Gallery
              photos={allGridPhotos}
              layout={layout}
              rowHeight={rowHeight}
              groupBy={(sort === 'name' || sort === 'added') ? 'none' : groupBy}
              scrollRoot={scrollEl}
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
                  <span className="w-3 h-3 border-2 border-gray-300 border-t-indigo-500 rounded-full animate-spin" /> {t('gallery.loadingMore')}
                </span>
              )}
              {!infiniteQuery.hasNextPage && allGridPhotos.length > 0 && (
                <span className="text-xs text-gray-300 dark:text-gray-600">{t('gallery.allLoaded', { n: total.toLocaleString('de') })}</span>
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
          <button onClick={clearSelection} className="p-2 rounded-xl text-zinc-300 hover:bg-white/10 transition-colors" title={t('gallery.clearSelection')}>
            <X size={18} />
          </button>
          <span className="px-2 text-sm font-semibold text-white tabular-nums">{selectionCount}</span>
          <div className="w-px h-6 bg-white/15 mx-1" />
          {library === 'trash' ? (
            <button onClick={() => batchMutation.mutate('untrash')} disabled={batchMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-emerald-300 hover:bg-emerald-500/20 transition-colors disabled:opacity-50" title={t('gallery.restore')}>
              <Archive size={16} /> <span className="hidden sm:inline">{t('gallery.restore')}</span>
            </button>
          ) : library === 'archive' ? (
            <button onClick={() => batchMutation.mutate('unarchive')} disabled={batchMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title={t('gallery.fromArchive')}>
              <Archive size={16} /> <span className="hidden sm:inline">{t('gallery.fromArchive')}</span>
            </button>
          ) : (
            <>
              <button onClick={() => batchMutation.mutate('favorite')} disabled={batchMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title={t('gallery.favoriteTitle')}>
                <Heart size={16} /> <span className="hidden sm:inline">{t('gallery.favorite')}</span>
              </button>
              <button onClick={() => batchMutation.mutate('archive')} disabled={batchMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors disabled:opacity-50" title={t('gallery.archiveTitle')}>
                <Archive size={16} /> <span className="hidden sm:inline">{t('gallery.archiveAction')}</span>
              </button>
            </>
          )}
          {library !== 'trash' && (
            <button onClick={() => setAlbumModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-zinc-200 hover:bg-white/10 transition-colors" title={t('gallery.addToAlbum')}>
              <FolderPlus size={16} /> <span className="hidden sm:inline">{t('gallery.album')}</span>
            </button>
          )}
          {library !== 'trash' && (
            <button onClick={() => batchMutation.mutate('trash')} disabled={batchMutation.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-red-300 hover:bg-red-500/20 transition-colors disabled:opacity-50" title={t('gallery.toTrash')}>
              <Trash2 size={16} /> <span className="hidden sm:inline">{t('gallery.trash')}</span>
            </button>
          )}
          <button
            onClick={() => { if (window.confirm(t('gallery.deleteConfirm', { n: selected.size }))) batchMutation.mutate('delete') }}
            disabled={batchMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-red-400 hover:bg-red-500/25 transition-colors disabled:opacity-50" title={t('gallery.deletePermanently')}>
            <Trash2 size={16} /> <span className="hidden sm:inline">{t('gallery.delete')}</span>
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
  const { t } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [newName, setNewName] = useState('')
  const { data: albums = [] } = useQuery<any[]>({ queryKey: ['albums'], queryFn: () => api.get('/albums').then(r => r.data) })
  const manual = albums.filter(a => a.album_type === 'manual')
  const done = () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast(t('gallery.albumAdded', { n: photoIds.length }), 'success'); onDone() }
  const addTo = useMutation({ mutationFn: (id: number) => api.post(`/albums/${id}/photos`, { photo_ids: photoIds }), onSuccess: done })
  const create = useMutation({
    mutationFn: async () => { const a = await api.post('/albums', { name: newName.trim(), album_type: 'manual' }); await api.post(`/albums/${a.data.id}/photos`, { photo_ids: photoIds }) },
    onSuccess: done,
  })
  return (
    <Modal open onClose={onClose} title={t('gallery.albumModalTitle', { n: photoIds.length })}>
      <div className="flex gap-2 mb-4">
        <input value={newName} onChange={e => setNewName(e.target.value)} placeholder={t('gallery.newAlbumPlaceholder')}
          onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) create.mutate() }}
          className="flex-1 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        <button onClick={() => create.mutate()} disabled={!newName.trim() || create.isPending}
          className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">{t('gallery.create')}</button>
      </div>
      <div className="max-h-72 overflow-y-auto space-y-1">
        {manual.length === 0 ? (
          <p className="text-sm text-zinc-500 text-center py-3">{t('gallery.noManualAlbums')}</p>
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

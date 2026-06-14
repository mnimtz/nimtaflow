import { useState, useCallback } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { Search, SlidersHorizontal } from 'lucide-react'
import { api, Photo } from '../lib/api'
import PhotoGrid from '../components/gallery/PhotoGrid'
import PhotoLightbox from '../components/gallery/PhotoLightbox'

export default function GalleryPage() {
  const [search, setSearch] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const [selected, setSelected] = useState<Photo | null>(null)

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } = useInfiniteQuery({
    queryKey: ['photos', activeSearch],
    queryFn: ({ pageParam = 1 }) =>
      api.get('/photos', { params: { page: pageParam, limit: 50, search: activeSearch || undefined } })
        .then((r) => r.data),
    getNextPageParam: (last) => {
      const nextPage = last.page + 1
      return nextPage * last.limit < last.total ? nextPage : undefined
    },
    initialPageParam: 1,
  })

  const photos = data?.pages.flatMap((p) => p.items) ?? []
  const total = data?.pages[0]?.total ?? 0

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setActiveSearch(search)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center gap-3">
        <form onSubmit={handleSearch} className="flex-1 flex gap-2">
          <div className="relative flex-1 max-w-md">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Semantische Suche… z.B. „Lea am Strand""
              className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button type="submit" className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors">
            Suchen
          </button>
        </form>
        <span className="text-sm text-gray-500 dark:text-gray-400 shrink-0">
          {total.toLocaleString('de')} Fotos
        </span>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto p-4">
        {isLoading ? (
          <div className="flex items-center justify-center h-64 text-gray-400">Lade Fotos…</div>
        ) : photos.length === 0 ? (
          <EmptyState />
        ) : (
          <PhotoGrid
            photos={photos}
            onSelect={setSelected}
            onLoadMore={fetchNextPage}
            hasMore={hasNextPage}
            loadingMore={isFetchingNextPage}
          />
        )}
      </div>

      {/* Lightbox */}
      {selected && (
        <PhotoLightbox
          photo={selected}
          photos={photos}
          onClose={() => setSelected(null)}
          onNavigate={setSelected}
        />
      )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      <div className="text-5xl mb-4">📷</div>
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Noch keine Fotos</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
        Füge unter <strong>Einstellungen → Quellen</strong> einen Ordner hinzu, um loszulegen.
      </p>
    </div>
  )
}

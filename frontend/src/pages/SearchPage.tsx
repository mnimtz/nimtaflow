import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Sparkles, Loader2 } from 'lucide-react'
import { api, type Photo } from '../lib/api'
import JustifiedGrid from '../components/gallery/JustifiedGrid'
import PhotoLightbox from '../components/gallery/PhotoLightbox'
import { useT } from '../i18n'

export default function SearchPage() {
  const { t } = useT()
  const EXAMPLES = [
    t('search.example1'),
    t('search.example2'),
    t('search.example3'),
    t('search.example4'),
  ]
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [lightbox, setLightbox] = useState<{ photos: Photo[]; index: number } | null>(null)

  const { data, isFetching, error } = useQuery({
    queryKey: ['semantic-search', query],
    queryFn: () => api.get('/photos/search/semantic', { params: { q: query, limit: 80 } }).then(r => r.data.items as Photo[]),
    enabled: query.trim().length > 0,
  })

  const photos = data ?? []

  return (
    <div className="flex flex-col h-full">
      <div className="shrink-0 border-b border-gray-200 dark:border-gray-800 px-4 py-3">
        <form onSubmit={e => { e.preventDefault(); setQuery(draft) }} className="flex items-center gap-2 max-w-2xl mx-auto">
          <div className="relative flex-1">
            <Sparkles size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-indigo-400" />
            <input
              value={draft}
              onChange={e => setDraft(e.target.value)}
              placeholder={t('search.placeholder')}
              className="w-full pl-9 pr-3 py-2.5 text-sm rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <button type="submit" className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium transition-colors">
            <Search size={15} /> {t('search.submit')}
          </button>
        </form>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {!query && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Sparkles size={40} className="text-indigo-300 dark:text-indigo-700 mb-3" />
            <p className="text-gray-600 dark:text-gray-300 text-sm font-medium">{t('search.emptyTitle')}</p>
            <p className="text-gray-400 text-xs mt-1 max-w-md">
              {t('search.emptyDesc')}
            </p>
            <div className="flex flex-wrap gap-2 justify-center mt-4 max-w-lg">
              {EXAMPLES.map(ex => (
                <button key={ex} onClick={() => { setDraft(ex); setQuery(ex) }}
                  className="px-3 py-1.5 rounded-full text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {isFetching && (
          <div className="flex justify-center py-16 text-gray-400 text-sm items-center gap-2">
            <Loader2 size={16} className="animate-spin" /> {t('search.running')}
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-sm text-amber-500">{(error as any)?.response?.data?.detail || t('search.failed')}</p>
            <p className="text-xs text-gray-400 mt-1">{t('search.failedHint')}</p>
          </div>
        )}

        {query && !isFetching && !error && (
          photos.length === 0 ? (
            <p className="text-center text-gray-400 text-sm py-16">{t('search.noResults')}</p>
          ) : (
            <>
              <p className="text-xs text-gray-400 mb-3">{t('search.hits', { n: photos.length, q: query })}</p>
              <JustifiedGrid
                photos={photos}
                rowHeight={200}
                gap={4}
                onPhotoClick={(_, i) => setLightbox({ photos, index: i })}
              />
            </>
          )
        )}
      </div>

      {lightbox && (
        <PhotoLightbox photos={lightbox.photos} initialIndex={lightbox.index} onClose={() => setLightbox(null)} />
      )}
    </div>
  )
}

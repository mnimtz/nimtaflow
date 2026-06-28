import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PawPrint, Loader2 } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../lib/api'
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import { useT } from '../i18n'

/** Pets — surfaces photos the AI tagged as showing a dog/cat/etc. No extra model:
 *  it reuses the descriptions/tags already computed for the whole library. */
export default function PetsPage() {
  const { t } = useT()
  const [lbIdx, setLbIdx] = useState<number | null>(null)
  const { data, isPending } = useQuery<{ items: Photo[]; total: number }>({
    queryKey: ['pets'],
    queryFn: () => api.get('/photos/pets', { params: { limit: 300 } }).then(r => r.data),
    staleTime: 60_000,
  })
  const photos = data?.items || []

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <PawPrint className="text-indigo-500" size={22} />
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white">{t('nav.pets')}</h1>
      </div>
      <p className="text-sm text-zinc-500 mb-4">{t('pets.subtitle')}</p>

      {isPending ? (
        <div className="flex items-center justify-center py-20 text-zinc-400 text-sm">
          <Loader2 className="animate-spin mr-2" size={16} /> {t('pets.loading')}
        </div>
      ) : photos.length === 0 ? (
        <div className="text-center py-20 text-zinc-400">
          <PawPrint size={40} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">{t('pets.empty')}</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-zinc-400 mb-2">{t('pets.count', { n: data?.total ?? photos.length })}</p>
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8 gap-1.5">
            {photos.map((photo, i) => (
              <div key={photo.id} className="relative aspect-square rounded-lg overflow-hidden bg-zinc-800">
                <img src={thumbUrl(photo as any, 'small')} className="w-full h-full object-cover cursor-pointer"
                  loading="lazy" onClick={() => setLbIdx(i)} />
              </div>
            ))}
          </div>
        </>
      )}
      {lbIdx !== null && <GalleryLightbox photos={photos} index={lbIdx} onClose={() => setLbIdx(null)} />}
    </div>
  )
}

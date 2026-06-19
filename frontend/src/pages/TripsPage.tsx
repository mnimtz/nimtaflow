import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plane, MapPin, Images } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../lib/api'
import GalleryLightbox from '../components/gallery/GalleryLightbox'

type Ev = {
  count: number; date_from: string; date_to: string; days: number
  city: string | null; is_trip: boolean; cover_photo_id: number
}

function fmtRange(a: string, b: string) {
  const da = new Date(a), db = new Date(b)
  if (a === b) return da.toLocaleDateString('de', { day: 'numeric', month: 'long', year: 'numeric' })
  const opt: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
  const sameYear = da.getFullYear() === db.getFullYear()
  return `${da.toLocaleDateString('de', sameYear ? opt : { ...opt, year: 'numeric' })} – ${db.toLocaleDateString('de', { ...opt, year: 'numeric' })}`
}

export default function TripsPage() {
  const [tab, setTab] = useState<'trips' | 'all'>('trips')
  const { data, isLoading } = useQuery<{ home_city: string | null; events: Ev[] }>({
    queryKey: ['trips'],
    queryFn: () => api.get('/photos/trips').then(r => r.data),
  })
  const [lb, setLb] = useState<{ photos: Photo[]; index: number } | null>(null)

  const open = async (e: Ev) => {
    try {
      const r = await api.get('/photos', { params: { date_from: e.date_from, date_to: e.date_to, limit: 500, sort: 'oldest' } })
      setLb({ photos: r.data.items || [], index: 0 })
    } catch { /* ignore */ }
  }

  const events = (data?.events || []).filter(e => tab === 'trips' ? e.is_trip : true)

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white flex items-center gap-2">
          <Plane size={20} /> Reisen & Events
        </h1>
        <div className="flex rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-700 text-sm">
          {([['trips', 'Reisen'], ['all', 'Alle Events']] as const).map(([v, l]) => (
            <button key={v} onClick={() => setTab(v)}
              className={`px-3 py-1.5 ${tab === v ? 'bg-indigo-600 text-white' : 'text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}>{l}</button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <p className="text-zinc-500">Lade …</p>
      ) : events.length === 0 ? (
        <p className="text-zinc-500 text-sm">Noch keine {tab === 'trips' ? 'Reisen' : 'Events'} erkannt. (Automatisch aus Zeit + Ort — sobald Fotos Datum/GPS haben.)</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {events.map(e => (
            <button key={`${e.date_from}-${e.cover_photo_id}`} onClick={() => open(e)}
              className="group text-left rounded-2xl overflow-hidden bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 hover:ring-2 hover:ring-indigo-500 transition">
              <div className="aspect-[16/10] overflow-hidden bg-zinc-200 dark:bg-zinc-800">
                <img src={thumbUrl({ id: e.cover_photo_id } as any, 'medium')} loading="lazy"
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  onError={ev => { (ev.target as HTMLImageElement).style.opacity = '0.2' }} />
              </div>
              <div className="p-3">
                <div className="font-semibold text-zinc-900 dark:text-white truncate flex items-center gap-1.5">
                  {e.city ? <><MapPin size={13} className="text-indigo-400 shrink-0" /> {e.city}</> : 'Event'}
                </div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">{fmtRange(e.date_from, e.date_to)}</div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-1 flex items-center gap-3">
                  <span className="flex items-center gap-1"><Images size={12} /> {e.count}</span>
                  {e.days > 1 && <span>{e.days} Tage</span>}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {lb && <GalleryLightbox photos={lb.photos} index={lb.index} onClose={() => setLb(null)} />}
    </div>
  )
}

import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapContainer, TileLayer, Polyline, Marker, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { Plane, MapPin, Images, Sparkles, ArrowLeft, X, Loader2, Trash2 } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../lib/api'
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import { useToast, useConfirm } from '../components/ui/dialogs'

type Waypoint = { place: string; country?: string; date?: string; lat: number; lng: number; note?: string }
type Album = { id: number; name: string; cover_photo_id?: number | null; photo_count: number; smart_criteria?: any }
type Ev = { count: number; date_from: string; date_to: string; days: number; city: string | null; is_trip: boolean; cover_photo_id: number }

function fmtRange(a?: string, b?: string) {
  if (!a) return ''
  const da = new Date(a), db = b ? new Date(b) : da
  const o: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short' }
  if (!b || a === b) return da.toLocaleDateString('de', { day: 'numeric', month: 'long', year: 'numeric' })
  const sy = da.getFullYear() === db.getFullYear()
  return `${da.toLocaleDateString('de', sy ? o : { ...o, year: 'numeric' })} – ${db.toLocaleDateString('de', { ...o, year: 'numeric' })}`
}

function FitAll({ pts }: { pts: [number, number][] }) {
  const map = useMap()
  useMemo(() => { if (pts.length) setTimeout(() => map.fitBounds(pts as any, { padding: [40, 40], maxZoom: 12 }), 0) }, [pts.length])
  return null
}

// ── Trip detail: map route (photo GPS line + named waypoints) + removable photos ──
function TripDetail({ album, onBack }: { album: Album; onBack: () => void }) {
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const [lbIdx, setLbIdx] = useState<number | null>(null)
  const { data } = useQuery<{ items: Photo[]; total: number }>({
    queryKey: ['album-photos', album.id],
    queryFn: () => api.get(`/albums/${album.id}/photos`, { params: { limit: 1000 } }).then(r => r.data),
  })
  const photos = data?.items || []
  const route: Waypoint[] = album.smart_criteria?.route || []
  // actual travelled path = photos with GPS, in chronological order
  const gpsLine = useMemo(() => photos
    .filter(p => p.latitude != null && p.longitude != null)
    .sort((a, b) => (a.taken_at || '').localeCompare(b.taken_at || ''))
    .map(p => [p.latitude!, p.longitude!] as [number, number]), [photos])
  const allPts = useMemo(() => [...gpsLine, ...route.map(w => [w.lat, w.lng] as [number, number])], [gpsLine, route])

  const remove = useMutation({
    mutationFn: (pid: number) => api.delete(`/albums/${album.id}/photos/${pid}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['album-photos', album.id] }); toast('Foto aus Reise entfernt', 'success') },
  })
  const delTrip = useMutation({
    mutationFn: () => api.delete(`/albums/${album.id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast('Reise gelöscht', 'success'); onBack() },
  })

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <button onClick={onBack} className="flex items-center gap-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-white text-sm mb-4"><ArrowLeft size={16} /> Zurück</button>
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white mb-1">{album.name}</h1>
        <button onClick={async () => { if (await confirm({ title: `Reise „${album.name}" löschen?`, message: 'Das Album wird gelöscht. Die Fotos bleiben in deiner Galerie.', danger: true, confirmLabel: 'Löschen' })) delTrip.mutate() }}
          className="flex items-center gap-1.5 text-sm text-red-500 hover:text-red-400 shrink-0"><Trash2 size={15} /> Reise löschen</button>
      </div>
      <p className="text-sm text-zinc-500 mb-4">{photos.length} Fotos{route.length ? ` · ${route.length} Stationen` : ''}</p>

      {allPts.length > 0 && (
        <div className="rounded-2xl overflow-hidden border border-zinc-200 dark:border-zinc-700 h-72 mb-6">
          <MapContainer center={allPts[0]} zoom={6} className="h-full w-full" scrollWheelZoom>
            <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
            <FitAll pts={allPts} />
            {gpsLine.length > 1 && <Polyline positions={gpsLine} pathOptions={{ color: '#818cf8', weight: 3, opacity: 0.7 }} />}
            {route.length > 1 && <Polyline positions={route.map(w => [w.lat, w.lng] as [number, number])} pathOptions={{ color: '#f59e0b', weight: 2, dashArray: '6 6', opacity: 0.8 }} />}
            {route.map((w, i) => (
              <Marker key={i} position={[w.lat, w.lng]}
                icon={L.divIcon({ className: '', html: `<div style="background:#f59e0b;color:#000;font-size:11px;font-weight:700;border-radius:9999px;width:20px;height:20px;display:flex;align-items:center;justify-content:center;border:2px solid #fff">${i + 1}</div>`, iconSize: [20, 20], iconAnchor: [10, 10] })}>
                <Tooltip>{w.place}{w.date ? ` · ${new Date(w.date).toLocaleDateString('de')}` : ''}</Tooltip>
              </Marker>
            ))}
          </MapContainer>
        </div>
      )}

      <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8 gap-1.5">
        {photos.map((photo, i) => (
          <div key={photo.id} className="group relative aspect-square rounded-lg overflow-hidden bg-zinc-800">
            <img src={thumbUrl(photo as any, 'small')} className="w-full h-full object-cover cursor-pointer" loading="lazy" onClick={() => setLbIdx(i)} />
            <button onClick={async () => { if (await confirm({ title: 'Aus der Reise entfernen?', message: 'Das Foto bleibt in deiner Galerie, nur nicht in dieser Reise.', confirmLabel: 'Entfernen' })) remove.mutate(photo.id) }}
              title="Aus Reise entfernen"
              className="absolute top-1 right-1 bg-black/60 hover:bg-red-600 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition"><X size={12} /></button>
          </div>
        ))}
      </div>
      {lbIdx !== null && <GalleryLightbox photos={photos} index={lbIdx} onClose={() => setLbIdx(null)} />}
    </div>
  )
}

// ── Create-trip wizard ──────────────────────────────────────────────────────────
function Wizard({ onClose, onCreated }: { onClose: () => void; onCreated: (id: number) => void }) {
  const toast = useToast()
  const [desc, setDesc] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [plan, setPlan] = useState<{ name: string; date_from?: string; date_to?: string; summary?: string; waypoints: Waypoint[] } | null>(null)
  const inp = 'w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500'

  const planM = useMutation({
    mutationFn: () => api.post('/photos/plan-trip', { description: desc, date_from: from || null, date_to: to || null }).then(r => r.data),
    onSuccess: (d) => { if (d.error) toast(d.error, 'error'); else { setPlan(d); if (d.date_from && !from) setFrom(d.date_from); if (d.date_to && !to) setTo(d.date_to) } },
    onError: () => toast('Planung fehlgeschlagen', 'error'),
  })
  const saveM = useMutation({
    mutationFn: () => api.post('/photos/create-trip', { name: plan!.name, date_from: from || plan!.date_from, date_to: to || plan!.date_to, waypoints: plan!.waypoints, description: plan!.summary }).then(r => r.data),
    onSuccess: (d) => { toast(`Reise „${d.name}" angelegt (${d.added} Fotos)`, 'success'); onCreated(d.album_id) },
    onError: () => toast('Konnte Reise nicht speichern', 'error'),
  })

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
          <h2 className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-white"><Sparkles size={16} className="text-indigo-400" /> Reise anlegen</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Beschreibe die Reise (Gemini baut die Route)</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} className={`${inp} resize-none`}
              placeholder="z. B. AIDA Mittelmeer-Kreuzfahrt ab Mallorca über Barcelona, Marseille, Genua und Rom" />
          </div>
          <div className="flex gap-2">
            <div className="flex-1"><label className="block text-xs text-zinc-500 mb-1">von</label><input type="date" value={from} onChange={e => setFrom(e.target.value)} className={inp} /></div>
            <div className="flex-1"><label className="block text-xs text-zinc-500 mb-1">bis</label><input type="date" value={to} onChange={e => setTo(e.target.value)} className={inp} /></div>
          </div>
          <button onClick={() => planM.mutate()} disabled={!desc.trim() || planM.isPending}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-zinc-200 dark:bg-zinc-700 text-sm font-medium text-zinc-800 dark:text-white hover:bg-zinc-300 dark:hover:bg-zinc-600 disabled:opacity-50">
            {planM.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} Route planen
          </button>

          {plan && (
            <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-3 space-y-2">
              <div className="font-semibold text-zinc-900 dark:text-white">{plan.name}</div>
              {plan.summary && <p className="text-xs text-zinc-500">{plan.summary}</p>}
              <ol className="space-y-1">
                {plan.waypoints.map((w, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                    <span className="w-5 h-5 shrink-0 rounded-full bg-amber-500 text-black text-[11px] font-bold flex items-center justify-center">{i + 1}</span>
                    <span className="font-medium">{w.place}</span>
                    {w.date && <span className="text-xs text-zinc-500">{new Date(w.date).toLocaleDateString('de')}</span>}
                  </li>
                ))}
              </ol>
              <button onClick={() => saveM.mutate()} disabled={saveM.isPending}
                className="w-full mt-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
                {saveM.isPending ? <Loader2 size={15} className="animate-spin" /> : <Plane size={15} />} Reise speichern + Fotos zuordnen
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function TripsPage() {
  const qc = useQueryClient()
  const [wizard, setWizard] = useState(false)
  const [openTrip, setOpenTrip] = useState<Album | null>(null)
  const [lb, setLb] = useState<{ photos: Photo[]; index: number } | null>(null)

  const { data: albums = [] } = useQuery<Album[]>({ queryKey: ['albums'], queryFn: () => api.get('/albums').then(r => r.data) })
  const trips = albums.filter(a => a.smart_criteria?.trip)
  const { data: evData } = useQuery<{ events: Ev[] }>({ queryKey: ['trips'], queryFn: () => api.get('/photos/trips').then(r => r.data) })
  const suggestions = (evData?.events || []).filter(e => e.is_trip)

  const openEvent = async (e: Ev) => {
    try {
      const r = await api.get('/photos', { params: { date_from: e.date_from, date_to: e.date_to, limit: 500, sort: 'oldest' } })
      setLb({ photos: r.data.items || [], index: 0 })
    } catch { /* ignore */ }
  }

  if (openTrip) return <TripDetail album={openTrip} onBack={() => setOpenTrip(null)} />

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <div className="flex items-center justify-between gap-3 mb-5 flex-wrap">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white flex items-center gap-2"><Plane size={20} /> Reisen</h1>
        <button onClick={() => setWizard(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
          <Sparkles size={15} /> Reise anlegen
        </button>
      </div>

      {trips.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
          {trips.map(a => (
            <button key={a.id} onClick={() => setOpenTrip(a)}
              className="group text-left rounded-2xl overflow-hidden bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 hover:ring-2 hover:ring-indigo-500 transition">
              <div className="aspect-[16/10] overflow-hidden bg-zinc-200 dark:bg-zinc-800">
                {a.cover_photo_id && <img src={thumbUrl({ id: a.cover_photo_id } as any, 'medium')} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />}
              </div>
              <div className="p-3">
                <div className="font-semibold text-zinc-900 dark:text-white truncate">{a.name}</div>
                <div className="text-xs text-zinc-500 mt-1 flex items-center gap-3">
                  <span className="flex items-center gap-1"><Images size={12} /> {a.photo_count}</span>
                  {a.smart_criteria?.route?.length ? <span className="flex items-center gap-1"><MapPin size={12} /> {a.smart_criteria.route.length}</span> : null}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {suggestions.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-3">Automatisch erkannt</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {suggestions.map(e => (
              <button key={`${e.date_from}-${e.cover_photo_id}`} onClick={() => openEvent(e)}
                className="group text-left rounded-2xl overflow-hidden bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 hover:ring-2 hover:ring-indigo-500 transition">
                <div className="aspect-[16/10] overflow-hidden bg-zinc-200 dark:bg-zinc-800">
                  <img src={thumbUrl({ id: e.cover_photo_id } as any, 'medium')} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                </div>
                <div className="p-3">
                  <div className="font-semibold text-zinc-900 dark:text-white truncate flex items-center gap-1.5">{e.city ? <><MapPin size={13} className="text-indigo-400 shrink-0" /> {e.city}</> : 'Event'}</div>
                  <div className="text-xs text-zinc-500 mt-0.5">{fmtRange(e.date_from, e.date_to)}</div>
                  <div className="text-xs text-zinc-500 mt-1 flex items-center gap-3"><span className="flex items-center gap-1"><Images size={12} /> {e.count}</span>{e.days > 1 && <span>{e.days} Tage</span>}</div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      {trips.length === 0 && suggestions.length === 0 && (
        <p className="text-zinc-500 text-sm">Noch keine Reisen. Lege über „Reise anlegen" eine an — Gemini baut die Route und ordnet die Fotos automatisch zu.</p>
      )}

      {wizard && <Wizard onClose={() => setWizard(false)} onCreated={(id) => { setWizard(false); qc.invalidateQueries({ queryKey: ['albums'] }); const a = albums.find(x => x.id === id); if (a) setOpenTrip(a) }} />}
      {lb && <GalleryLightbox photos={lb.photos} index={lb.index} onClose={() => setLb(null)} />}
    </div>
  )
}

import { useState, useMemo, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapContainer, TileLayer, Polyline, Marker, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { Plane, MapPin, Images, Sparkles, ArrowLeft, X, Loader2, Trash2, Share2, Pencil, Plus, Check, Play, Pause } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../lib/api'
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import ShareDialog from '../components/ShareDialog'
import { Modal, useToast, useConfirm } from '../components/ui/dialogs'
import { useT } from '../i18n'

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

// Pan the map to follow the moving marker while a route plays.
function RouteFollow({ at }: { at: [number, number] | null }) {
  const map = useMap()
  useEffect(() => { if (at) map.panTo(at, { animate: true, duration: 0.7 }) }, [at?.[0], at?.[1]])
  return null
}

// ── Add-photos picker: search + date filter (prefilled to the trip span) ──────────
function AddPhotosModal({ albumId, existing, defaultFrom, defaultTo, onClose, onAdded }: {
  albumId: number; existing: Set<number>; defaultFrom?: string; defaultTo?: string
  onClose: () => void; onAdded: () => void
}) {
  const { t } = useT()
  const toast = useToast()
  const [q, setQ] = useState('')
  const [from, setFrom] = useState(defaultFrom || '')
  const [to, setTo] = useState(defaultTo || '')
  const [sel, setSel] = useState<Set<number>>(new Set())

  const { data, isFetching } = useQuery<{ items: Photo[]; total: number }>({
    queryKey: ['trip-add-photos', albumId, q, from, to],
    queryFn: () => api.get('/photos', { params: {
      search: q.trim() || undefined, date_from: from || undefined, date_to: to || undefined,
      limit: 120, sort: 'oldest',
    } }).then(r => r.data),
  })
  const items = data?.items || []

  const add = useMutation({
    mutationFn: () => api.post(`/albums/${albumId}/photos`, { photo_ids: [...sel] }).then(r => r.data),
    onSuccess: (d: { added: number }) => { toast(t('trips.toastAdded', { n: d.added }), 'success'); onAdded() },
  })
  const toggle = (id: number) => setSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const inp = 'px-2.5 py-1.5 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <Modal open onClose={onClose} title={t('trips.addPhotosTitle')} maxWidth="max-w-4xl">
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('trips.searchPlaceholder')} className={`${inp} flex-1 min-w-[10rem]`} />
        <label className="text-xs text-zinc-500">{t('trips.from')} <input type="date" value={from} onChange={e => setFrom(e.target.value)} className={inp} /></label>
        <label className="text-xs text-zinc-500">{t('trips.to')} <input type="date" value={to} onChange={e => setTo(e.target.value)} className={inp} /></label>
      </div>
      <div className="h-[55vh] overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-800 p-1.5">
        {isFetching && items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-400 text-sm"><Loader2 className="animate-spin mr-2" size={16} /> {t('trips.loading')}</div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-400 text-sm">{t('trips.noPhotosForFilter')}</div>
        ) : (
          <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-1.5">
            {items.map(p => {
              const already = existing.has(p.id)
              const picked = sel.has(p.id)
              return (
                <button key={p.id} disabled={already} onClick={() => toggle(p.id)}
                  className={`relative aspect-square rounded-lg overflow-hidden bg-zinc-800 ${already ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'} ${picked ? 'ring-2 ring-indigo-500' : ''}`}>
                  <img src={thumbUrl(p as any, 'small')} className="w-full h-full object-cover" loading="lazy" />
                  {already && <span className="absolute inset-x-0 bottom-0 text-[10px] bg-black/60 text-white text-center py-0.5">{t('trips.inTrip')}</span>}
                  {picked && <span className="absolute top-1 right-1 bg-indigo-500 rounded-full p-0.5"><Check size={11} className="text-white" /></span>}
                </button>
              )
            })}
          </div>
        )}
      </div>
      <div className="flex items-center justify-end gap-2 mt-3">
        <button onClick={onClose} className="px-3 py-1.5 text-sm rounded-lg text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('trips.cancel')}</button>
        <button onClick={() => add.mutate()} disabled={sel.size === 0 || add.isPending}
          className="px-3.5 py-1.5 text-sm rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-500 disabled:opacity-50">
          {add.isPending ? t('trips.adding') : t('trips.addN', { n: sel.size })}
        </button>
      </div>
    </Modal>
  )
}

// ── Trip detail: map route (photo GPS line + named waypoints) + add/removable photos ──
function TripDetail({ album, onBack }: { album: Album; onBack: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const [lbIdx, setLbIdx] = useState<number | null>(null)
  const [showShare, setShowShare] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const { data } = useQuery<{ items: Photo[]; total: number }>({
    queryKey: ['album-photos', album.id],
    queryFn: () => api.get(`/albums/${album.id}/photos`, { params: { limit: 1000 } }).then(r => r.data),
  })
  const photos = data?.items || []
  // Trip date span (from existing photos) → prefill the add-photos date filter.
  const dates = useMemo(() => photos.map(p => p.taken_at).filter(Boolean).sort() as string[], [photos])
  const tripFrom = dates[0]?.slice(0, 10)
  const tripTo = dates[dates.length - 1]?.slice(0, 10)
  const existingIds = useMemo(() => new Set(photos.map(p => p.id)), [photos])
  const route: Waypoint[] = album.smart_criteria?.route || []
  // actual travelled path = photos with GPS, in chronological order
  const gpsPhotos = useMemo(() => photos
    .filter(p => p.latitude != null && p.longitude != null)
    .sort((a, b) => (a.taken_at || '').localeCompare(b.taken_at || '')), [photos])
  const gpsLine = useMemo(() => gpsPhotos.map(p => [p.latitude!, p.longitude!] as [number, number]), [gpsPhotos])
  const allPts = useMemo(() => [...gpsLine, ...route.map(w => [w.lat, w.lng] as [number, number])], [gpsLine, route])

  // ── Animated route playback ──────────────────────────────────────────────
  const [playing, setPlaying] = useState(false)
  const [playIdx, setPlayIdx] = useState(0)
  useEffect(() => {
    if (!playing) return
    if (playIdx >= gpsLine.length - 1) { setPlaying(false); return }
    const id = setTimeout(() => setPlayIdx(i => Math.min(i + 1, gpsLine.length - 1)), 900)
    return () => clearTimeout(id)
  }, [playing, playIdx, gpsLine.length])
  const togglePlay = () => {
    if (playing) { setPlaying(false); return }
    if (playIdx >= gpsLine.length - 1) setPlayIdx(0)   // restart from the beginning
    setPlaying(true)
  }
  const curPhoto = playing || playIdx > 0 ? gpsPhotos[playIdx] : null

  const remove = useMutation({
    mutationFn: (pid: number) => api.delete(`/albums/${album.id}/photos/${pid}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['album-photos', album.id] }); toast(t('trips.photoRemoved'), 'success') },
  })
  const delTrip = useMutation({
    mutationFn: () => api.delete(`/albums/${album.id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast(t('trips.tripDeleted'), 'success'); onBack() },
  })
  const renameTrip = useMutation({
    mutationFn: (name: string) => api.patch(`/albums/${album.id}`, { name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast(t('trips.tripRenamed'), 'success') },
  })

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <button onClick={onBack} className="flex items-center gap-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-white text-sm mb-4"><ArrowLeft size={16} /> {t('trips.back')}</button>
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white mb-1">{album.name}</h1>
        <div className="flex items-center gap-3 shrink-0">
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-1.5 text-sm text-indigo-500 hover:text-indigo-400"><Plus size={15} /> {t('trips.addPhotos')}</button>
          <button onClick={() => { const n = window.prompt(t('trips.renamePrompt'), album.name); if (n && n.trim() && n !== album.name) renameTrip.mutate(n.trim()) }}
            className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white"><Pencil size={15} /> {t('trips.rename')}</button>
          <button onClick={() => setShowShare(true)}
            className="flex items-center gap-1.5 text-sm text-indigo-500 hover:text-indigo-400"><Share2 size={15} /> {t('trips.share')}</button>
          <button onClick={async () => { if (await confirm({ title: t('trips.confirmDeleteTitle', { name: album.name }), message: t('trips.confirmDeleteMsg'), danger: true, confirmLabel: t('trips.confirmDeleteLabel') })) delTrip.mutate() }}
            className="flex items-center gap-1.5 text-sm text-red-500 hover:text-red-400"><Trash2 size={15} /> {t('trips.deleteTrip')}</button>
        </div>
      </div>
      {showShare && <ShareDialog target={{ kind: 'album', albumId: album.id, title: album.name }} onClose={() => setShowShare(false)} />}
      {showAdd && (
        <AddPhotosModal albumId={album.id} existing={existingIds} defaultFrom={tripFrom} defaultTo={tripTo}
          onClose={() => setShowAdd(false)}
          onAdded={() => { qc.invalidateQueries({ queryKey: ['album-photos', album.id] }); qc.invalidateQueries({ queryKey: ['albums'] }); setShowAdd(false) }} />
      )}
      <p className="text-sm text-zinc-500 mb-4">{route.length ? t('trips.photosStations', { photos: photos.length, stations: route.length }) : t('trips.photosOnly', { photos: photos.length })}</p>

      {allPts.length > 0 && (
        <div className="relative rounded-2xl overflow-hidden border border-zinc-200 dark:border-zinc-700 h-72 mb-6">
          <MapContainer center={allPts[0]} zoom={6} className="h-full w-full" scrollWheelZoom>
            <TileLayer url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png" attribution="&copy; CARTO &copy; OpenStreetMap contributors" />
            {!playing && playIdx === 0 && <FitAll pts={allPts} />}
            {/* Full route, dimmed while a playback is in progress */}
            {gpsLine.length > 1 && <Polyline positions={gpsLine} pathOptions={{ color: '#818cf8', weight: 3, opacity: curPhoto ? 0.25 : 0.7 }} />}
            {/* Travelled-so-far highlight + moving marker during playback */}
            {curPhoto && playIdx > 0 && <Polyline positions={gpsLine.slice(0, playIdx + 1)} pathOptions={{ color: '#f6d488', weight: 4, opacity: 0.95 }} />}
            {curPhoto && (
              <>
                <Marker position={gpsLine[playIdx]}
                  icon={L.divIcon({ className: '', html: `<div style="background:#e8b54a;border:3px solid #fff;border-radius:9999px;width:18px;height:18px;box-shadow:0 0 0 6px rgba(232,181,74,.35)"></div>`, iconSize: [18, 18], iconAnchor: [9, 9] })} />
                <RouteFollow at={gpsLine[playIdx]} />
              </>
            )}
            {route.length > 1 && <Polyline positions={route.map(w => [w.lat, w.lng] as [number, number])} pathOptions={{ color: '#f59e0b', weight: 2, dashArray: '6 6', opacity: 0.8 }} />}
            {route.map((w, i) => (
              <Marker key={i} position={[w.lat, w.lng]}
                icon={L.divIcon({ className: '', html: `<div style="background:#f59e0b;color:#000;font-size:11px;font-weight:700;border-radius:9999px;width:20px;height:20px;display:flex;align-items:center;justify-content:center;border:2px solid #fff">${i + 1}</div>`, iconSize: [20, 20], iconAnchor: [10, 10] })}>
                <Tooltip>{w.place}{w.date ? ` · ${new Date(w.date).toLocaleDateString('de')}` : ''}</Tooltip>
              </Marker>
            ))}
          </MapContainer>

          {gpsLine.length > 1 && (
            <button onClick={togglePlay}
              className="absolute top-2 left-2 z-[500] flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-black/70 hover:bg-black/85 text-white text-sm font-medium backdrop-blur">
              {playing ? <Pause size={15} /> : <Play size={15} />}
              {playing ? t('trips.routePause') : t('trips.routePlay')}
            </button>
          )}
          {curPhoto && (
            <div className="absolute bottom-2 left-2 right-2 z-[500] flex items-center gap-3 px-3 py-2 rounded-xl bg-black/70 text-white backdrop-blur">
              <img src={thumbUrl(curPhoto as any, 'small')} className="w-14 h-14 rounded-lg object-cover shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">{[(curPhoto as any).city, (curPhoto as any).country].filter(Boolean).join(', ') || t('trips.routeStop')}</div>
                <div className="text-xs text-white/70">{curPhoto.taken_at ? new Date(curPhoto.taken_at).toLocaleDateString('de', { day: 'numeric', month: 'long', year: 'numeric' }) : ''}</div>
              </div>
              <div className="text-xs text-white/70 shrink-0">{playIdx + 1}/{gpsLine.length}</div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8 gap-1.5">
        {photos.map((photo, i) => (
          <div key={photo.id} className="group relative aspect-square rounded-lg overflow-hidden bg-zinc-800">
            <img src={thumbUrl(photo as any, 'small')} className="w-full h-full object-cover cursor-pointer" loading="lazy" onClick={() => setLbIdx(i)} />
            <button onClick={async () => { if (await confirm({ title: t('trips.removeFromTripTitle'), message: t('trips.removeFromTripMsg'), confirmLabel: t('trips.removeLabel') })) remove.mutate(photo.id) }}
              title={t('trips.removeFromTripTooltip')}
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
  const { t } = useT()
  const toast = useToast()
  const [desc, setDesc] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [plan, setPlan] = useState<{ name: string; date_from?: string; date_to?: string; summary?: string; waypoints: Waypoint[] } | null>(null)
  const inp = 'w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500'

  const planM = useMutation({
    mutationFn: () => api.post('/photos/plan-trip', { description: desc, date_from: from || null, date_to: to || null }).then(r => r.data),
    onSuccess: (d) => { if (d.error) toast(d.error, 'error'); else { setPlan(d); if (d.date_from && !from) setFrom(d.date_from); if (d.date_to && !to) setTo(d.date_to) } },
    onError: () => toast(t('trips.planFailed'), 'error'),
  })
  const saveM = useMutation({
    mutationFn: () => api.post('/photos/create-trip', { name: plan!.name, date_from: from || plan!.date_from, date_to: to || plan!.date_to, waypoints: plan!.waypoints, description: plan!.summary }).then(r => r.data),
    onSuccess: (d) => { toast(t('trips.tripCreated', { name: d.name, added: d.added }), 'success'); onCreated(d.album_id) },
    onError: () => toast(t('trips.saveFailed'), 'error'),
  })

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
          <h2 className="text-base font-semibold flex items-center gap-2 text-zinc-900 dark:text-white"><Sparkles size={16} className="text-indigo-400" /> {t('trips.createTitle')}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">{t('trips.describe')}</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3} className={`${inp} resize-none`}
              placeholder={t('trips.describePlaceholder')} />
          </div>
          <div className="flex gap-2">
            <div className="flex-1"><label className="block text-xs text-zinc-500 mb-1">{t('trips.from')}</label><input type="date" value={from} onChange={e => setFrom(e.target.value)} className={inp} /></div>
            <div className="flex-1"><label className="block text-xs text-zinc-500 mb-1">{t('trips.to')}</label><input type="date" value={to} onChange={e => setTo(e.target.value)} className={inp} /></div>
          </div>
          <button onClick={() => planM.mutate()} disabled={!desc.trim() || planM.isPending}
            className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-zinc-200 dark:bg-zinc-700 text-sm font-medium text-zinc-800 dark:text-white hover:bg-zinc-300 dark:hover:bg-zinc-600 disabled:opacity-50">
            {planM.isPending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} {t('trips.planRoute')}
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
                {saveM.isPending ? <Loader2 size={15} className="animate-spin" /> : <Plane size={15} />} {t('trips.saveTrip')}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function TripsPage() {
  const { t } = useT()
  const qc = useQueryClient()
  const [wizard, setWizard] = useState(false)
  const [openTrip, setOpenTrip] = useState<Album | null>(null)
  const [lb, setLb] = useState<{ photos: Photo[]; index: number } | null>(null)

  const { data: albums = [] } = useQuery<Album[]>({ queryKey: ['albums'], queryFn: () => api.get('/albums').then(r => r.data) })
  const trips = albums.filter(a => a.smart_criteria?.trip)

  // Deep-Link vom Assistenten: /trips?trip=<id> öffnet direkt diese Reise.
  const [searchParams, setSearchParams] = useSearchParams()
  useEffect(() => {
    const tid = searchParams.get('trip')
    if (tid && /^\d+$/.test(tid) && albums.length) {
      const a = albums.find(x => x.id === Number(tid))
      if (a) { setOpenTrip(a); setSearchParams({}, { replace: true }) }
    }
  }, [searchParams, albums])
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
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white flex items-center gap-2"><Plane size={20} /> {t('trips.heading')}</h1>
        <button onClick={() => setWizard(true)} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
          <Sparkles size={15} /> {t('trips.createTitle')}
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
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-3">{t('trips.autoDetected')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {suggestions.map(e => (
              <button key={`${e.date_from}-${e.cover_photo_id}`} onClick={() => openEvent(e)}
                className="group text-left rounded-2xl overflow-hidden bg-zinc-100 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 hover:ring-2 hover:ring-indigo-500 transition">
                <div className="aspect-[16/10] overflow-hidden bg-zinc-200 dark:bg-zinc-800">
                  <img src={thumbUrl({ id: e.cover_photo_id } as any, 'medium')} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                </div>
                <div className="p-3">
                  <div className="font-semibold text-zinc-900 dark:text-white truncate flex items-center gap-1.5">{e.city ? <><MapPin size={13} className="text-indigo-400 shrink-0" /> {e.city}</> : t('trips.event')}</div>
                  <div className="text-xs text-zinc-500 mt-0.5">{fmtRange(e.date_from, e.date_to)}</div>
                  <div className="text-xs text-zinc-500 mt-1 flex items-center gap-3"><span className="flex items-center gap-1"><Images size={12} /> {e.count}</span>{e.days > 1 && <span>{t('trips.days', { n: e.days })}</span>}</div>
                </div>
              </button>
            ))}
          </div>
        </>
      )}

      {trips.length === 0 && suggestions.length === 0 && (
        <p className="text-zinc-500 text-sm">{t('trips.emptyState')}</p>
      )}

      {wizard && <Wizard onClose={() => setWizard(false)} onCreated={(id) => { setWizard(false); qc.invalidateQueries({ queryKey: ['albums'] }); const a = albums.find(x => x.id === id); if (a) setOpenTrip(a) }} />}
      {lb && <GalleryLightbox photos={lb.photos} index={lb.index} onClose={() => setLb(null)} />}
    </div>
  )
}

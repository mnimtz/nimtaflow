import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import Lightbox from 'yet-another-react-lightbox'
import 'yet-another-react-lightbox/styles.css'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import Fullscreen from 'yet-another-react-lightbox/plugins/fullscreen'
import Slideshow from 'yet-another-react-lightbox/plugins/slideshow'
import Thumbnails from 'yet-another-react-lightbox/plugins/thumbnails'
import 'yet-another-react-lightbox/plugins/thumbnails.css'
import Counter from 'yet-another-react-lightbox/plugins/counter'
import 'yet-another-react-lightbox/plugins/counter.css'
import Captions from 'yet-another-react-lightbox/plugins/captions'
import 'yet-another-react-lightbox/plugins/captions.css'
import Video from 'yet-another-react-lightbox/plugins/video'
import Download from 'yet-another-react-lightbox/plugins/download'
import { MapContainer, TileLayer, CircleMarker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Info, Heart, Camera, MapPin, Calendar, Aperture, Users as UsersIcon, Tag as TagIcon } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../../lib/api'

function fmtBytes(b?: number) { if (!b) return null; const u = ['B', 'KB', 'MB', 'GB']; let i = 0, n = b; while (n >= 1024 && i < 3) { n /= 1024; i++ } return `${n.toFixed(1)} ${u[i]}` }

function fmtDur(s?: number) { if (!s) return null; const m = Math.floor(s / 60), sec = Math.round(s % 60); return `${m}:${String(sec).padStart(2, '0')} min` }
function fmtDate(v?: string) { return v ? new Date(v).toLocaleString('de', { dateStyle: 'medium', timeStyle: 'short' }) : null }

function InfoPanel({ photoId, onClose }: { photoId: number; onClose: () => void }) {
  const { data: p } = useQuery<any>({ queryKey: ['photo-detail', photoId], queryFn: () => api.get(`/photos/${photoId}`).then(r => r.data) })
  if (!p) return null
  const Row = ({ icon: Icon, label, children }: any) => (
    <div className="flex items-start gap-2 text-sm text-zinc-200">
      {Icon ? <Icon size={15} className="mt-0.5 text-zinc-400 shrink-0" /> : <span className="w-[15px] shrink-0" />}
      <div className="min-w-0">{label && <div className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</div>}{children}</div>
    </div>
  )
  const taken = p.taken_at ? new Date(p.taken_at).toLocaleString('de', { dateStyle: 'full', timeStyle: 'short' }) : null
  const mp = p.width && p.height ? (p.width * p.height / 1e6).toFixed(1) : null
  // tags come back as an array (p.tags); fall back to a keywords string
  const tags: string[] = Array.isArray(p.tags) ? p.tags
    : (p.keywords ? String(p.keywords).split(',').map((k: string) => k.trim()).filter(Boolean) : [])
  const people: any[] = Array.isArray(p.people) ? p.people : []
  const namedPeople = people.filter(pp => pp.name)
  const exposure = [
    p.focal_length && `${Math.round(p.focal_length)} mm`,
    p.focal_length_35mm && `(KB ${p.focal_length_35mm} mm)`,
    p.aperture && `ƒ/${p.aperture}`,
    p.shutter_speed && `${p.shutter_speed}s`,
    p.iso && `ISO ${p.iso}`,
    p.exposure_compensation != null && p.exposure_compensation !== 0 && `${p.exposure_compensation > 0 ? '+' : ''}${p.exposure_compensation} EV`,
  ].filter(Boolean)
  return (
    <div className="fixed z-[100000] bg-zinc-900/95 backdrop-blur border-zinc-700 text-white overflow-y-auto
      inset-x-0 bottom-0 max-h-[60vh] border-t rounded-t-2xl
      md:inset-y-0 md:right-0 md:left-auto md:w-[360px] md:max-h-none md:border-l md:border-t-0 md:rounded-none">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 sticky top-0 bg-zinc-900/95">
        <h3 className="font-semibold">Informationen</h3>
        <button onClick={onClose} className="text-zinc-400 hover:text-white text-sm">Schließen</button>
      </div>
      <div className="p-4 space-y-4">
        <p className="text-sm font-medium text-zinc-100 break-all">{p.filename}</p>

        {p.description && (
          <div>
            <p className="text-sm text-zinc-300 italic">{p.description}</p>
            {p.description_model && <p className="text-[11px] text-zinc-500 mt-1">KI: {p.description_model}</p>}
          </div>
        )}

        {taken && <Row icon={Calendar} label="Aufgenommen">{taken}</Row>}

        {(p.camera_make || p.camera_model) && (
          <Row icon={Camera} label="Kamera">
            {[p.camera_make, p.camera_model].filter(Boolean).join(' ')}
            {p.lens_model && <div className="text-xs text-zinc-400">{p.lens_model}</div>}
          </Row>
        )}

        {exposure.length > 0 && (
          <Row icon={Aperture} label="Belichtung">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-zinc-300">{exposure.map((e, i) => <span key={i}>{e}</span>)}</div>
          </Row>
        )}

        {(p.width && p.height) && (
          <Row icon={Info} label={p.is_video ? 'Video' : 'Bild'}>
            {p.width} × {p.height}{mp ? ` · ${mp} MP` : ''}
            <div className="text-xs text-zinc-400 flex flex-wrap gap-x-3">
              {fmtBytes(p.file_size) && <span>{fmtBytes(p.file_size)}</span>}
              {p.mime_type && <span>{p.mime_type}</span>}
              {p.is_video && fmtDur(p.duration_seconds) && <span>{fmtDur(p.duration_seconds)}</span>}
              {p.is_video && p.video_codec && <span>{p.video_codec}</span>}
              {p.is_video && p.video_fps && <span>{Math.round(p.video_fps)} fps</span>}
              {p.is_video && p.video_bitrate && <span>{(p.video_bitrate / 1e6).toFixed(1)} Mbit/s</span>}
            </div>
          </Row>
        )}

        {namedPeople.length > 0 && (
          <Row icon={UsersIcon} label="Personen">
            <div className="flex flex-wrap gap-1.5">
              {namedPeople.map(pp => <span key={pp.face_id} className="px-2 py-0.5 rounded-full bg-indigo-600/30 text-indigo-200 text-xs">{pp.name}</span>)}
            </div>
          </Row>
        )}

        {(p.city || p.country || p.location_name) && <Row icon={MapPin} label="Ort">{[p.location_name, p.city, p.country].filter(Boolean).join(', ')}</Row>}

        {p.latitude != null && p.longitude != null && (
          <div className="space-y-1.5">
            <div className="rounded-xl overflow-hidden border border-zinc-800 h-40">
              <MapContainer center={[p.latitude, p.longitude]} zoom={13} className="h-full w-full" zoomControl={false} attributionControl={false} dragging={false} scrollWheelZoom={false}>
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
                <CircleMarker center={[p.latitude, p.longitude]} radius={7} pathOptions={{ color: '#6366f1', fillColor: '#818cf8', fillOpacity: 0.9 }} />
              </MapContainer>
            </div>
            <p className="text-[11px] text-zinc-500">{p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}{p.altitude != null ? ` · ${Math.round(p.altitude)} m` : ''}</p>
          </div>
        )}

        {tags.length > 0 && (
          <Row icon={TagIcon} label="Tags">
            <div className="flex flex-wrap gap-1.5">
              {tags.slice(0, 30).map((k) => <span key={k} className="px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 text-xs">{k}</span>)}
            </div>
          </Row>
        )}

        {(p.user_rating || p.is_favorite) && (
          <Row icon={Heart} label="Bewertung">
            {p.user_rating ? '★'.repeat(p.user_rating) + '☆'.repeat(5 - p.user_rating) : ''}{p.is_favorite ? '  ❤️ Favorit' : ''}
          </Row>
        )}

        <div className="pt-2 border-t border-zinc-800 space-y-1 text-[11px] text-zinc-500">
          <div className="break-all">{p.path}</div>
          {fmtDate(p.indexed_at) && <div>Indexiert: {fmtDate(p.indexed_at)}</div>}
          {fmtDate(p.processed_at) && <div>Verarbeitet: {fmtDate(p.processed_at)}</div>}
          {p.ai_error && <div className="text-amber-400">KI-Fehler bei der Verarbeitung</div>}
        </div>
      </div>
    </div>
  )
}

export default function GalleryLightbox({ photos, index, onClose, onFavorite, hasMore, onLoadMore }: {
  photos: Photo[]; index: number; onClose: () => void; onFavorite?: (photo: Photo) => void
  hasMore?: boolean; onLoadMore?: () => void
}) {
  const [cur, setCur] = useState(index)
  const [info, setInfo] = useState(false)
  // Track favorite state locally so the heart updates immediately (the `photos`
  // array is a snapshot frozen when the lightbox opened).
  const [favs, setFavs] = useState<Set<number>>(() => new Set(photos.filter(p => p.is_favorite).map(p => p.id)))
  const toggleFav = (p: Photo) => {
    onFavorite?.(p)
    setFavs(s => { const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n })
  }
  const isFav = (p?: Photo) => !!p && favs.has(p.id)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'i') { setInfo(v => !v) }
      if (e.key === 'f' && photos[cur]) toggleFav(photos[cur])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cur, photos, onFavorite])

  const slides = photos.map(p => p.is_video
    ? { type: 'video' as const, poster: thumbUrl(p, 'large'), width: p.width || 1280, height: p.height || 720, sources: [{ src: `/api/photos/${p.id}/video/stream`, type: 'video/mp4' }], description: p.filename }
    : { src: thumbUrl(p, 'large'), width: p.width || undefined, height: p.height || undefined, description: p.filename, download: { url: `/api/photos/${p.id}/original`, filename: p.filename } })

  const infoBtn = (
    <button key="info" type="button" className="yarl__button" onClick={() => setInfo(v => !v)} title="Informationen (i)">
      <Info className="yarl__icon" />
    </button>
  )
  const favBtn = onFavorite ? (
    <button key="fav" type="button" className="yarl__button" onClick={() => photos[cur] && toggleFav(photos[cur])} title="Favorit (f)">
      <Heart className="yarl__icon" fill={isFav(photos[cur]) ? 'currentColor' : 'none'} color={isFav(photos[cur]) ? '#f87171' : undefined} />
    </button>
  ) : null

  return (
    <>
      <Lightbox
        open index={index} close={onClose} slides={slides as any}
        on={{ view: ({ index: i }) => {
          setCur(i)
          // Pull the next page as the user nears the end of what's loaded, so
          // browsing covers the whole library instead of looping a few photos.
          if (onLoadMore && hasMore && i >= photos.length - 3) onLoadMore()
        } }}
        plugins={[Zoom, Fullscreen, Slideshow, Thumbnails, Counter, Captions, Video, Download]}
        toolbar={{ buttons: [favBtn, infoBtn, 'download', 'slideshow', 'fullscreen', 'close'].filter(Boolean) as any }}
        zoom={{ maxZoomPixelRatio: 4, scrollToZoom: true }}
        thumbnails={{ position: 'bottom', width: 96, height: 64, border: 0, gap: 6 }}
        counter={{ container: { style: { top: 'unset', bottom: 0 } } }}
        captions={{ descriptionTextAlign: 'center' }}
        carousel={{ finite: true, preload: 2 }}
        styles={{ container: { backgroundColor: 'rgba(0,0,0,0.94)' } }}
        animation={{ fade: 250, swipe: 300 }}
      />
      {info && photos[cur] && <InfoPanel photoId={photos[cur].id} onClose={() => setInfo(false)} />}
    </>
  )
}

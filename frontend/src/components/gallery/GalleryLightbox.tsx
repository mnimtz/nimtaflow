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
import { Info, Heart, Camera, MapPin, Calendar, Aperture } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../../lib/api'

function fmtBytes(b?: number) { if (!b) return null; const u = ['B', 'KB', 'MB', 'GB']; let i = 0, n = b; while (n >= 1024 && i < 3) { n /= 1024; i++ } return `${n.toFixed(1)} ${u[i]}` }

function InfoPanel({ photoId, onClose }: { photoId: number; onClose: () => void }) {
  const { data: p } = useQuery<any>({ queryKey: ['photo-detail', photoId], queryFn: () => api.get(`/photos/${photoId}`).then(r => r.data) })
  if (!p) return null
  const Row = ({ icon: Icon, children }: any) => <div className="flex items-start gap-2 text-sm text-zinc-200"><Icon size={15} className="mt-0.5 text-zinc-400 shrink-0" /><div>{children}</div></div>
  const date = p.taken_at ? new Date(p.taken_at).toLocaleString('de', { dateStyle: 'full', timeStyle: 'short' }) : null
  return (
    <div className="fixed z-[100000] bg-zinc-900/95 backdrop-blur border-zinc-700 text-white overflow-y-auto
      inset-x-0 bottom-0 max-h-[55vh] border-t rounded-t-2xl
      md:inset-y-0 md:right-0 md:left-auto md:w-[340px] md:max-h-none md:border-l md:border-t-0 md:rounded-none">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 sticky top-0 bg-zinc-900/95">
        <h3 className="font-semibold">Informationen</h3>
        <button onClick={onClose} className="text-zinc-400 hover:text-white text-sm">Schließen</button>
      </div>
      <div className="p-4 space-y-4">
        <p className="text-sm text-zinc-300 break-all">{p.filename}</p>
        {p.description && <p className="text-sm text-zinc-300 italic">{p.description}</p>}
        {date && <Row icon={Calendar}>{date}</Row>}
        {(p.camera_make || p.camera_model) && <Row icon={Camera}>{[p.camera_make, p.camera_model].filter(Boolean).join(' ')}{p.lens_model && <div className="text-xs text-zinc-400">{p.lens_model}</div>}</Row>}
        {(p.aperture || p.shutter_speed || p.iso || p.focal_length) && (
          <Row icon={Aperture}>
            <div className="flex flex-wrap gap-x-3 text-zinc-300">
              {p.focal_length && <span>{Math.round(p.focal_length)} mm</span>}
              {p.aperture && <span>ƒ/{p.aperture}</span>}
              {p.shutter_speed && <span>{p.shutter_speed}s</span>}
              {p.iso && <span>ISO {p.iso}</span>}
            </div>
          </Row>
        )}
        {(p.width && p.height) && <Row icon={Info}>{p.width} × {p.height}{fmtBytes(p.file_size) ? ` · ${fmtBytes(p.file_size)}` : ''}</Row>}
        {(p.city || p.country || p.location_name) && <Row icon={MapPin}>{[p.location_name, p.city, p.country].filter(Boolean).join(', ')}</Row>}
        {p.latitude != null && p.longitude != null && (
          <div className="rounded-xl overflow-hidden border border-zinc-800 h-40">
            <MapContainer center={[p.latitude, p.longitude]} zoom={13} className="h-full w-full" zoomControl={false} attributionControl={false} dragging={false} scrollWheelZoom={false}>
              <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" />
              <CircleMarker center={[p.latitude, p.longitude]} radius={7} pathOptions={{ color: '#6366f1', fillColor: '#818cf8', fillOpacity: 0.9 }} />
            </MapContainer>
          </div>
        )}
        {p.keywords && (
          <div className="flex flex-wrap gap-1.5">
            {String(p.keywords).split(',').map((k: string) => k.trim()).filter(Boolean).slice(0, 20).map((k: string) => (
              <span key={k} className="px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 text-xs">{k}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function GalleryLightbox({ photos, index, onClose, onFavorite }: {
  photos: Photo[]; index: number; onClose: () => void; onFavorite?: (photo: Photo) => void
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
        on={{ view: ({ index: i }) => setCur(i) }}
        plugins={[Zoom, Fullscreen, Slideshow, Thumbnails, Counter, Captions, Video, Download]}
        toolbar={{ buttons: [favBtn, infoBtn, 'download', 'slideshow', 'fullscreen', 'close'].filter(Boolean) as any }}
        zoom={{ maxZoomPixelRatio: 4, scrollToZoom: true }}
        thumbnails={{ position: 'bottom', width: 96, height: 64, border: 0, gap: 6 }}
        counter={{ container: { style: { top: 'unset', bottom: 0 } } }}
        captions={{ descriptionTextAlign: 'center' }}
        carousel={{ finite: false, preload: 2 }}
        styles={{ container: { backgroundColor: 'rgba(0,0,0,0.94)' } }}
        animation={{ fade: 250, swipe: 300 }}
      />
      {info && photos[cur] && <InfoPanel photoId={photos[cur].id} onClose={() => setInfo(false)} />}
    </>
  )
}

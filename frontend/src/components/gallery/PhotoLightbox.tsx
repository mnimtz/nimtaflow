import { useEffect, useState, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  X, ChevronLeft, ChevronRight, Heart, Download, Info,
  MapPin, Camera, Aperture, Trash2, Calendar, Star, Pencil, Save, Loader2,
} from 'lucide-react'
import { api, type Photo } from '../../lib/api'
import VideoPlayer from './VideoPlayer'

type PhotoDetail = Photo & {
  description?: string
  camera_make?: string
  camera_model?: string
  lens_model?: string
  focal_length?: number
  aperture?: number
  shutter_speed?: string
  iso?: number
  altitude?: number
  city?: string
  country?: string
  location_name?: string
  file_size?: number
  mime_type?: string
  title?: string
  caption?: string
  keywords?: string
  user_description?: string
  tags?: string[]
  people?: { face_id: number; person_id: number | null; name: string | null; confidence?: number }[]
  exposure_time?: number
  white_balance?: number
  flash?: number
  orientation?: number
  color_space?: string
  software?: string
  focal_length_35mm?: number
  description_model?: string
}

type Props = {
  photos: Photo[]
  initialIndex: number
  onClose: () => void
}

function ExifRow({ label, value }: { label: string; value?: string | number | null }) {
  if (!value) return null
  return (
    <div className="flex justify-between gap-2 text-sm">
      <span className="text-gray-400 shrink-0">{label}</span>
      <span className="text-gray-200 text-right break-all">{String(value)}</span>
    </div>
  )
}

export default function PhotoLightbox({ photos, initialIndex, onClose }: Props) {
  const [index, setIndex] = useState(initialIndex)
  const [showInfo, setShowInfo] = useState(false)
  const [rating, setRating] = useState(0)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ title: '', user_description: '', keywords: '', writeFile: false, writeXmp: false })
  const touch = useRef<{ x: number; y: number } | null>(null)
  const qc = useQueryClient()

  const photo = photos[index]

  const { data: detail } = useQuery<PhotoDetail>({
    queryKey: ['photo-detail', photo?.id],
    queryFn: () => api.get(`/photos/${photo.id}`).then(r => r.data),
    enabled: !!photo,
  })

  useEffect(() => {
    setRating(detail?.user_rating ?? 0)
    setEditing(false)
    setForm({
      title: detail?.title ?? '',
      user_description: detail?.user_description ?? detail?.description ?? '',
      keywords: detail?.keywords ?? '',
      writeFile: false,
      writeXmp: false,
    })
  }, [detail])

  const saveMeta = useMutation({
    mutationFn: () => api.patch(`/photos/${photo.id}/meta`, {
      title: form.title || null,
      user_description: form.user_description || null,
      keywords: form.keywords || null,
      write_to_file: form.writeFile,
      write_xmp_sidecar: form.writeXmp,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['photo-detail', photo.id] })
      qc.invalidateQueries({ queryKey: ['photos'] })
      setEditing(false)
    },
  })

  function onTouchStart(e: React.TouchEvent) {
    touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }
  }
  function onTouchEnd(e: React.TouchEvent) {
    if (!touch.current) return
    const dx = e.changedTouches[0].clientX - touch.current.x
    const dy = e.changedTouches[0].clientY - touch.current.y
    if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) {
      go(dx < 0 ? 1 : -1)
    } else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) {
      onClose()
    }
    touch.current = null
  }

  const favMutation = useMutation({
    mutationFn: (id: number) => api.patch(`/photos/${id}/favorite`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['photos'] }),
  })

  const trashMutation = useMutation({
    mutationFn: (id: number) => api.patch(`/photos/${id}/trash`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['photos'] }); onClose() },
  })

  const go = useCallback((dir: -1 | 1) => {
    setIndex(i => Math.max(0, Math.min(photos.length - 1, i + dir)))
  }, [photos.length])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') go(-1)
      if (e.key === 'ArrowRight') go(1)
      if (e.key === 'i') setShowInfo(s => !s)
      if (e.key === 'f') photo && favMutation.mutate(photo.id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, go, photo?.id])

  if (!photo) return null

  const isFav = detail?.is_favorite ?? photo.is_favorite

  return (
    <div className="fixed inset-0 z-50 bg-black flex">
      {/* Main area */}
      <div className="relative flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-4 py-3 bg-gradient-to-b from-black/70 to-transparent">
          <button onClick={onClose} className="text-white/80 hover:text-white p-1 rounded transition-colors">
            <X size={22} />
          </button>
          <span className="text-white/60 text-sm">{index + 1} / {photos.length}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => favMutation.mutate(photo.id)}
              className={`p-2 rounded-full transition-colors ${isFav ? 'text-red-500' : 'text-white/70 hover:text-white'}`}
            >
              <Heart size={18} fill={isFav ? 'currentColor' : 'none'} />
            </button>
            <div className="flex gap-0.5 px-1">
              {[1, 2, 3, 4, 5].map(s => (
                <button
                  key={s}
                  onClick={() => { setRating(s); api.patch(`/photos/${photo.id}/rating`, { rating: s }) }}
                  className={`transition-colors ${s <= rating ? 'text-yellow-400' : 'text-white/30 hover:text-white/60'}`}
                >
                  <Star size={14} fill={s <= rating ? 'currentColor' : 'none'} />
                </button>
              ))}
            </div>
            <a
              href={`/api/photos/${photo.id}/original`}
              download={photo.filename}
              className="p-2 rounded-full text-white/70 hover:text-white transition-colors"
              onClick={e => e.stopPropagation()}
            >
              <Download size={18} />
            </a>
            <button
              onClick={() => setShowInfo(s => !s)}
              className={`p-2 rounded-full transition-colors ${showInfo ? 'text-indigo-400' : 'text-white/70 hover:text-white'}`}
            >
              <Info size={18} />
            </button>
            <button
              onClick={() => trashMutation.mutate(photo.id)}
              className="p-2 rounded-full text-white/40 hover:text-red-400 transition-colors"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        {/* Media */}
        <div
          className="flex-1 flex items-center justify-center overflow-hidden"
          onTouchStart={onTouchStart}
          onTouchEnd={onTouchEnd}
        >
          {photo.is_video ? (
            <VideoPlayer photoId={photo.id} className="w-full h-full" autoPlay />
          ) : (
            <img
              key={photo.id}
              src={`/api/photos/${photo.id}/original`}
              alt={photo.filename}
              className="max-h-full max-w-full object-contain select-none"
              draggable={false}
            />
          )}
        </div>

        {/* Nav */}
        {index > 0 && (
          <button
            onClick={() => go(-1)}
            className="absolute left-3 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-2 transition-colors"
          >
            <ChevronLeft size={24} />
          </button>
        )}
        {index < photos.length - 1 && (
          <button
            onClick={() => go(1)}
            className="absolute right-3 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/70 text-white rounded-full p-2 transition-colors"
          >
            <ChevronRight size={24} />
          </button>
        )}

        {/* Bottom */}
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-4 py-3 pointer-events-none">
          <p className="text-white/60 text-xs font-mono truncate">{photo.filename}</p>
          {detail?.description && (
            <p className="text-white/80 text-sm mt-0.5 line-clamp-2">{detail.description}</p>
          )}
        </div>
      </div>

      {/* Info panel — side panel on desktop, bottom sheet on mobile */}
      {showInfo && (
        <div className="
          bg-gray-950 border-white/10 overflow-y-auto
          md:w-80 md:shrink-0 md:border-l md:static
          fixed inset-x-0 bottom-0 max-h-[70vh] border-t rounded-t-2xl md:rounded-none z-20
        ">
          <div className="p-4 space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-white font-semibold text-sm">Details</h3>
              <div className="flex items-center gap-1">
                {!editing ? (
                  <button onClick={() => setEditing(true)} className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 px-2 py-1 rounded-lg hover:bg-white/5 transition-colors">
                    <Pencil size={13} /> Bearbeiten
                  </button>
                ) : (
                  <button onClick={() => setEditing(false)} className="text-xs text-gray-400 hover:text-white px-2 py-1">Abbrechen</button>
                )}
                <button onClick={() => setShowInfo(false)} className="md:hidden text-gray-400 hover:text-white p-1"><X size={16} /></button>
              </div>
            </div>

            {/* Editable metadata */}
            {editing ? (
              <div className="space-y-3">
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Titel</label>
                  <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                    className="w-full px-2.5 py-1.5 text-sm rounded-lg bg-gray-800 border border-white/10 text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Beschreibung</label>
                  <textarea value={form.user_description} onChange={e => setForm(f => ({ ...f, user_description: e.target.value }))} rows={3}
                    className="w-full px-2.5 py-1.5 text-sm rounded-lg bg-gray-800 border border-white/10 text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-400 mb-1">Schlagwörter (Komma-getrennt)</label>
                  <input value={form.keywords} onChange={e => setForm(f => ({ ...f, keywords: e.target.value }))} placeholder="urlaub, strand, 2024"
                    className="w-full px-2.5 py-1.5 text-sm rounded-lg bg-gray-800 border border-white/10 text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div className="space-y-1.5 pt-1">
                  <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
                    <input type="checkbox" checked={form.writeFile} onChange={e => setForm(f => ({ ...f, writeFile: e.target.checked }))} className="accent-indigo-500" />
                    In Originaldatei schreiben (EXIF/IPTC)
                  </label>
                  <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
                    <input type="checkbox" checked={form.writeXmp} onChange={e => setForm(f => ({ ...f, writeXmp: e.target.checked }))} className="accent-indigo-500" />
                    XMP-Sidecar (.xmp) schreiben
                  </label>
                </div>
                <button onClick={() => saveMeta.mutate()} disabled={saveMeta.isPending}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors">
                  {saveMeta.isPending ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                  Speichern
                </button>
              </div>
            ) : (detail?.title || detail?.user_description || detail?.description || detail?.keywords) ? (
              <div className="space-y-2">
                {detail?.title && <p className="text-gray-100 text-sm font-medium">{detail.title}</p>}
                {(detail?.user_description || detail?.description) && (
                  <p className="text-gray-300 text-sm">{detail.user_description || detail.description}</p>
                )}
                {detail?.keywords && (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {detail.keywords.split(',').map(k => k.trim()).filter(Boolean).map(k => (
                      <span key={k} className="px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 text-[11px]">{k}</span>
                    ))}
                  </div>
                )}
                {detail?.description_model && (
                  <p className="text-[10px] text-gray-500">KI-Beschreibung via {detail.description_model}</p>
                )}
              </div>
            ) : null}

            {/* Recognized people */}
            {detail?.people && detail.people.length > 0 && (
              <div className="border-t border-white/10 pt-4">
                <p className="text-xs text-gray-400 mb-1.5">Personen ({detail.people.length})</p>
                <div className="flex flex-wrap gap-1.5">
                  {detail.people.map(p => (
                    <span key={p.face_id} className={`px-2 py-0.5 rounded-full text-[11px] ${p.name ? 'bg-emerald-500/15 text-emerald-300' : 'bg-white/10 text-gray-400'}`}>
                      {p.name || 'Unbenannt'}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* AI tags */}
            {detail?.tags && detail.tags.length > 0 && (
              <div className="border-t border-white/10 pt-4">
                <p className="text-xs text-gray-400 mb-1.5">KI-Tags</p>
                <div className="flex flex-wrap gap-1.5">
                  {detail.tags.map(t => (
                    <span key={t} className="px-2 py-0.5 rounded-full bg-white/8 text-gray-300 text-[11px]">{t}</span>
                  ))}
                </div>
              </div>
            )}

            {photo.taken_at && (
              <div className="flex items-start gap-3">
                <Calendar size={16} className="text-gray-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-gray-200 text-sm">
                    {new Date(photo.taken_at).toLocaleDateString('de', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                  </p>
                  <p className="text-gray-400 text-xs">
                    {new Date(photo.taken_at).toLocaleTimeString('de')}
                  </p>
                </div>
              </div>
            )}

            {(detail?.city || detail?.country || photo.latitude) && (
              <div className="flex items-start gap-3">
                <MapPin size={16} className="text-green-400 mt-0.5 shrink-0" />
                <div>
                  {detail?.city && (
                    <p className="text-gray-200 text-sm">
                      {detail.city}{detail.country ? `, ${detail.country}` : ''}
                    </p>
                  )}
                  {detail?.location_name && <p className="text-gray-400 text-xs">{detail.location_name}</p>}
                  {photo.latitude && (
                    <p className="text-gray-500 text-xs font-mono mt-0.5">
                      {photo.latitude.toFixed(5)}, {photo.longitude?.toFixed(5)}
                    </p>
                  )}
                </div>
              </div>
            )}

            {detail?.camera_model && (
              <div className="flex items-start gap-3">
                <Camera size={16} className="text-gray-400 mt-0.5 shrink-0" />
                <div>
                  <p className="text-gray-200 text-sm">{detail.camera_model}</p>
                  {detail.lens_model && <p className="text-gray-400 text-xs">{detail.lens_model}</p>}
                </div>
              </div>
            )}

            {(detail?.aperture || detail?.shutter_speed || detail?.iso || detail?.focal_length) && (
              <div className="flex items-start gap-3">
                <Aperture size={16} className="text-gray-400 mt-0.5 shrink-0" />
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {detail?.focal_length && <span className="text-gray-300 text-sm">{detail.focal_length}mm</span>}
                  {detail?.aperture && <span className="text-gray-300 text-sm">f/{detail.aperture}</span>}
                  {detail?.shutter_speed && <span className="text-gray-300 text-sm">{detail.shutter_speed}s</span>}
                  {detail?.iso && <span className="text-gray-300 text-sm">ISO {detail.iso}</span>}
                </div>
              </div>
            )}

            {photo.width && (
              <div className="border-t border-white/10 pt-4 space-y-2">
                <ExifRow label="Auflösung" value={`${photo.width} × ${photo.height}`} />
                <ExifRow
                  label="Dateigröße"
                  value={detail?.file_size ? `${(detail.file_size / 1024 / 1024).toFixed(1)} MB` : null}
                />
                <ExifRow label="Format" value={detail?.mime_type} />
                <ExifRow label="Belichtungszeit" value={detail?.exposure_time ? `${detail.exposure_time}s` : null} />
                <ExifRow label="KB-Brennweite" value={detail?.focal_length_35mm ? `${detail.focal_length_35mm}mm` : null} />
                <ExifRow label="Blitz" value={detail?.flash != null ? (detail.flash ? 'Ja' : 'Nein') : null} />
                <ExifRow label="Weißabgleich" value={detail?.white_balance != null ? (detail.white_balance ? 'Manuell' : 'Auto') : null} />
                <ExifRow label="Farbraum" value={detail?.color_space} />
                <ExifRow label="Software" value={detail?.software} />
                <ExifRow label="Künstler" value={(detail as any)?.artist} />
                {detail?.is_video && <ExifRow label="Dauer" value={photo.duration_seconds ? `${Math.round(photo.duration_seconds)}s` : null} />}
              </div>
            )}

            {photo.latitude && photo.longitude && (
              <div className="border-t border-white/10 pt-4">
                <a
                  href={`https://www.openstreetmap.org/?mlat=${photo.latitude}&mlon=${photo.longitude}&zoom=14`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  <MapPin size={12} />
                  In OpenStreetMap öffnen
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

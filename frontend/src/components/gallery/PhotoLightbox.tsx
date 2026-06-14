import { useEffect, useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  X, ChevronLeft, ChevronRight, Heart, Download, Info,
  MapPin, Camera, Aperture, Trash2, Calendar, Star,
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
  const qc = useQueryClient()

  const photo = photos[index]

  const { data: detail } = useQuery<PhotoDetail>({
    queryKey: ['photo-detail', photo?.id],
    queryFn: () => api.get(`/photos/${photo.id}`).then(r => r.data),
    enabled: !!photo,
  })

  useEffect(() => {
    setRating(detail?.user_rating ?? 0)
  }, [detail])

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
        <div className="flex-1 flex items-center justify-center overflow-hidden">
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

      {/* Info panel */}
      {showInfo && (
        <div className="w-72 shrink-0 bg-gray-950 border-l border-white/10 overflow-y-auto">
          <div className="p-4 space-y-5">
            <h3 className="text-white font-semibold text-sm">Details</h3>

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

import { useEffect, useCallback } from 'react'
import { X, ChevronLeft, ChevronRight, Download, MapPin, Camera } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api, Photo } from '../../lib/api'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'

type Props = {
  photo: Photo
  photos: Photo[]
  onClose: () => void
  onNavigate: (p: Photo) => void
}

export default function PhotoLightbox({ photo, photos, onClose, onNavigate }: Props) {
  const idx = photos.findIndex((p) => p.id === photo.id)

  const { data: detail } = useQuery({
    queryKey: ['photo', photo.id],
    queryFn: () => api.get(`/photos/${photo.id}`).then((r) => r.data),
  })

  const prev = useCallback(() => { if (idx > 0) onNavigate(photos[idx - 1]) }, [idx, photos, onNavigate])
  const next = useCallback(() => { if (idx < photos.length - 1) onNavigate(photos[idx + 1]) }, [idx, photos, onNavigate])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowLeft') prev()
      if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, prev, next])

  return (
    <div className="fixed inset-0 z-50 flex bg-black/95" onClick={onClose}>
      {/* Close */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 z-10 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
      >
        <X size={20} />
      </button>

      {/* Prev */}
      {idx > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); prev() }}
          className="absolute left-4 top-1/2 -translate-y-1/2 z-10 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
        >
          <ChevronLeft size={24} />
        </button>
      )}

      {/* Image */}
      <div className="flex-1 flex items-center justify-center p-4" onClick={(e) => e.stopPropagation()}>
        <img
          src={`/api/photos/${photo.id}/thumbnail?size=large`}
          alt={photo.filename}
          className="max-w-full max-h-full object-contain rounded"
        />
      </div>

      {/* Next */}
      {idx < photos.length - 1 && (
        <button
          onClick={(e) => { e.stopPropagation(); next() }}
          className="absolute right-4 top-1/2 -translate-y-1/2 z-10 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white transition-colors"
        >
          <ChevronRight size={24} />
        </button>
      )}

      {/* Info sidebar */}
      <div
        className="w-72 shrink-0 bg-gray-900 border-l border-gray-800 overflow-y-auto p-4 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          <p className="text-sm font-medium text-white truncate">{photo.filename}</p>
          {photo.taken_at && (
            <p className="text-xs text-gray-400 mt-1">
              {format(new Date(photo.taken_at), 'PPPp', { locale: de })}
            </p>
          )}
        </div>

        {detail?.description && (
          <div>
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Beschreibung</p>
            <p className="text-sm text-gray-200">{detail.description}</p>
          </div>
        )}

        {(photo.latitude && photo.longitude) && (
          <div className="flex items-center gap-2 text-sm text-gray-300">
            <MapPin size={14} className="text-gray-500" />
            <span>{detail?.city || `${photo.latitude.toFixed(4)}, ${photo.longitude.toFixed(4)}`}</span>
          </div>
        )}

        {detail?.camera_model && (
          <div className="flex items-center gap-2 text-sm text-gray-300">
            <Camera size={14} className="text-gray-500" />
            <span>{detail.camera_model}</span>
          </div>
        )}

        {detail && (
          <div className="grid grid-cols-2 gap-2">
            {detail.aperture && <Chip label="Blende" value={`f/${detail.aperture}`} />}
            {detail.shutter_speed && <Chip label="Verschluss" value={detail.shutter_speed} />}
            {detail.iso && <Chip label="ISO" value={String(detail.iso)} />}
            {detail.focal_length && <Chip label="Brennweite" value={`${detail.focal_length}mm`} />}
          </div>
        )}

        <a
          href={`/api/photos/${photo.id}/original`}
          download={photo.filename}
          className="flex items-center gap-2 text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          <Download size={14} />
          Original herunterladen
        </a>
      </div>
    </div>
  )
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-800 rounded px-2 py-1">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm text-gray-200 font-medium">{value}</p>
    </div>
  )
}

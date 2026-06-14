import { useRef, useEffect } from 'react'
import { Heart, Play } from 'lucide-react'
import type { Photo, TimelineGroup } from '../../lib/api'

type Props = {
  groups: TimelineGroup[]
  rowHeight?: number
  onPhotoClick: (photo: Photo, allPhotos: Photo[], index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
}

function formatDateHeader(dateStr: string): { primary: string; secondary: string } {
  if (dateStr === 'unknown') return { primary: 'Unbekanntes Datum', secondary: '' }
  const d = new Date(dateStr)
  return {
    primary: d.toLocaleDateString('de', { weekday: 'long', day: 'numeric', month: 'long' }),
    secondary: d.getFullYear().toString(),
  }
}

function PhotoThumb({ photo, onClick, onFavorite }: {
  photo: Photo
  onClick: () => void
  onFavorite?: () => void
}) {
  return (
    <div
      className="relative group overflow-hidden rounded bg-gray-100 dark:bg-gray-800 cursor-pointer"
      style={{ aspectRatio: (photo.width && photo.height) ? `${photo.width}/${photo.height}` : '4/3' }}
      onClick={onClick}
    >
      <img
        src={`/api/photos/${photo.id}/thumbnail?size=medium`}
        alt={photo.filename}
        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
        loading="lazy"
      />
      {photo.is_video && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="bg-black/50 rounded-full p-2">
            <Play size={16} fill="white" className="text-white" />
          </div>
        </div>
      )}
      <button
        className={`absolute top-1 right-1 p-1 rounded-full transition-all ${
          photo.is_favorite
            ? 'bg-red-500 text-white opacity-100'
            : 'bg-black/40 text-white opacity-0 group-hover:opacity-100'
        }`}
        onClick={(e) => { e.stopPropagation(); onFavorite?.() }}
      >
        <Heart size={10} fill={photo.is_favorite ? 'white' : 'none'} />
      </button>
    </div>
  )
}

export default function TimelineView({ groups, rowHeight = 180, onPhotoClick, onFavoriteToggle }: Props) {
  const allPhotos = groups.flatMap(g => g.photos)

  return (
    <div className="w-full space-y-6">
      {groups.map((group) => {
        const { primary, secondary } = formatDateHeader(group.date)
        return (
          <div key={group.date}>
            {/* Sticky date header */}
            <div className="sticky top-0 z-10 bg-white/90 dark:bg-gray-950/90 backdrop-blur-sm py-2 mb-2 flex items-baseline gap-3">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{primary}</h3>
              <span className="text-xs text-gray-400">{secondary}</span>
              {group.count > group.photos.length && (
                <span className="ml-auto text-xs text-gray-400">{group.count} Fotos</span>
              )}
            </div>

            {/* Photos — CSS grid with auto columns */}
            <div
              className="grid gap-1"
              style={{
                gridTemplateColumns: `repeat(auto-fill, minmax(${Math.floor(rowHeight * 1.33)}px, 1fr))`,
                gridAutoRows: `${rowHeight}px`,
              }}
            >
              {group.photos.map((photo) => {
                const globalIndex = allPhotos.findIndex(p => p.id === photo.id)
                return (
                  <PhotoThumb
                    key={photo.id}
                    photo={photo}
                    onClick={() => onPhotoClick(photo, allPhotos, globalIndex)}
                    onFavorite={() => onFavoriteToggle?.(photo)}
                  />
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

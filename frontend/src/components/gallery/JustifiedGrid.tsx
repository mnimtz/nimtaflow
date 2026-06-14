import { useEffect, useRef, useState } from 'react'
import { Heart, Play, Star } from 'lucide-react'
import type { Photo } from '../../lib/api'

type Props = {
  photos: Photo[]
  rowHeight?: number
  gap?: number
  onPhotoClick: (photo: Photo, index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
}

type RowItem = { photo: Photo; index: number; width: number }

function buildRows(photos: Photo[], containerWidth: number, targetHeight: number, gap: number): RowItem[][] {
  if (!containerWidth) return []
  const rows: RowItem[][] = []
  let row: RowItem[] = []
  let rowWidth = 0

  photos.forEach((photo, index) => {
    const aspect = (photo.width && photo.height) ? photo.width / photo.height : 4 / 3
    const itemWidth = targetHeight * aspect
    const withGap = rowWidth + itemWidth + (row.length > 0 ? gap : 0)

    if (withGap > containerWidth && row.length > 0) {
      rows.push(row)
      row = [{ photo, index, width: itemWidth }]
      rowWidth = itemWidth
    } else {
      row.push({ photo, index, width: itemWidth })
      rowWidth = rowWidth + itemWidth + (row.length > 1 ? gap : 0)
    }
  })
  if (row.length > 0) rows.push(row)
  return rows
}

function JustifiedRow({ items, containerWidth, targetHeight, gap, onPhotoClick, onFavoriteToggle }: {
  items: RowItem[]
  containerWidth: number
  targetHeight: number
  gap: number
  onPhotoClick: (photo: Photo, index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
}) {
  const totalNatural = items.reduce((sum, it) => sum + it.width, 0)
  const totalGaps = gap * (items.length - 1)
  const scale = (containerWidth - totalGaps) / totalNatural
  return (
    <div className="flex" style={{ gap, height: targetHeight }}>
      {items.map(({ photo, index, width }) => {
        const w = Math.floor(width * scale)
        return (
          <div
            key={photo.id}
            className="relative group overflow-hidden bg-gray-100 dark:bg-gray-800 rounded cursor-pointer shrink-0"
            style={{ width: w, height: targetHeight }}
            onClick={() => onPhotoClick(photo, index)}
          >
            <img
              src={`/api/photos/${photo.id}/thumbnail?size=medium`}
              alt={photo.filename}
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
              loading="lazy"
            />

            {/* Video badge */}
            {photo.is_video && (
              <div className="absolute bottom-1.5 left-1.5 bg-black/60 rounded px-1.5 py-0.5 flex items-center gap-1">
                <Play size={10} fill="white" className="text-white" />
                {photo.duration_seconds && (
                  <span className="text-white text-[10px] font-medium">
                    {Math.floor(photo.duration_seconds / 60)}:{String(Math.floor(photo.duration_seconds % 60)).padStart(2, '0')}
                  </span>
                )}
              </div>
            )}

            {/* Favorite */}
            <button
              className={`absolute top-1.5 right-1.5 p-1 rounded-full transition-all ${
                photo.is_favorite
                  ? 'bg-red-500 text-white opacity-100'
                  : 'bg-black/40 text-white opacity-0 group-hover:opacity-100'
              }`}
              onClick={(e) => { e.stopPropagation(); onFavoriteToggle?.(photo) }}
            >
              <Heart size={12} fill={photo.is_favorite ? 'white' : 'none'} />
            </button>

            {/* Rating stars */}
            {photo.user_rating && photo.user_rating > 0 && (
              <div className="absolute bottom-1.5 right-1.5 flex gap-0.5">
                {Array.from({ length: photo.user_rating }).map((_, i) => (
                  <Star key={i} size={8} fill="gold" className="text-yellow-400" />
                ))}
              </div>
            )}

            {/* Hover overlay */}
            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
          </div>
        )
      })}
    </div>
  )
}

export default function JustifiedGrid({ photos, rowHeight = 200, gap = 4, onPhotoClick, onFavoriteToggle }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    const ro = new ResizeObserver(([entry]) => setContainerWidth(entry.contentRect.width))
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const rows = buildRows(photos, containerWidth, rowHeight, gap)

  return (
    <div ref={containerRef} className="w-full">
      <div className="flex flex-col" style={{ gap }}>
        {rows.map((row, ri) => (
          <JustifiedRow
            key={ri}
            items={row}
            containerWidth={containerWidth}
            targetHeight={rowHeight}
            gap={gap}
            onPhotoClick={onPhotoClick}
            onFavoriteToggle={onFavoriteToggle}
          />
        ))}
      </div>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { Heart, Play, Star, Check } from 'lucide-react'
import type { Photo } from '../../lib/api'

/** Tile image with a skeleton shimmer until it loads + video hover preview. */
function TileImage({ photo, isSelected }: { photo: Photo; isSelected: boolean }) {
  const [loaded, setLoaded] = useState(false)
  const [hover, setHover] = useState(false)
  return (
    <div
      className="absolute inset-0"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {!loaded && <div className="absolute inset-0 animate-pulse bg-gray-200 dark:bg-gray-700/60" />}
      <img
        src={`/api/photos/${photo.id}/thumbnail?size=medium`}
        alt={photo.filename}
        onLoad={() => setLoaded(true)}
        className={`w-full h-full object-cover transition-all duration-300 ${loaded ? 'opacity-100' : 'opacity-0'} ${
          isSelected ? 'scale-[0.92]' : 'group-hover:scale-105'
        }`}
        loading="lazy"
        draggable={false}
      />
      {/* animated preview on hover for videos */}
      {photo.is_video && hover && (
        <img
          src={`/api/photos/${photo.id}/preview`}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          draggable={false}
        />
      )}
    </div>
  )
}

type Props = {
  photos: Photo[]
  rowHeight?: number
  gap?: number
  onPhotoClick: (photo: Photo, index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
  selectable?: boolean
  selected?: Set<number>
  onToggleSelect?: (photo: Photo, index: number, shift: boolean) => void
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

function JustifiedRow({ items, containerWidth, targetHeight, gap, onPhotoClick, onFavoriteToggle, selectable, selected, onToggleSelect, anySelected, isLast }: {
  items: RowItem[]
  containerWidth: number
  targetHeight: number
  gap: number
  onPhotoClick: (photo: Photo, index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
  selectable?: boolean
  selected?: Set<number>
  onToggleSelect?: (photo: Photo, index: number, shift: boolean) => void
  anySelected: boolean
  isLast?: boolean
}) {
  const totalNatural = items.reduce((sum, it) => sum + it.width, 0)
  const totalGaps = gap * (items.length - 1)
  let scale = (containerWidth - totalGaps) / totalNatural
  // Don't blow up a sparse last row (e.g. a single item) to full width.
  if (isLast && scale > 1.15) scale = 1
  return (
    <div className="flex" style={{ gap, height: targetHeight, justifyContent: 'flex-start' }}>
      {items.map(({ photo, index, width }) => {
        const w = Math.floor(width * scale)
        const isSelected = selected?.has(photo.id) ?? false
        return (
          <div
            key={photo.id}
            className={`relative group overflow-hidden bg-gray-100 dark:bg-gray-800 rounded-lg cursor-pointer shrink-0 transition-all ${
              isSelected ? 'ring-[3px] ring-indigo-500 ring-offset-1 ring-offset-white dark:ring-offset-gray-950' : ''
            }`}
            style={{ width: w, height: targetHeight }}
            onClick={(e) => {
              if (selectable && anySelected) { onToggleSelect?.(photo, index, e.shiftKey); return }
              onPhotoClick(photo, index)
            }}
          >
            <TileImage photo={photo} isSelected={isSelected} />

            {/* top gradient for control legibility */}
            <div className="absolute inset-x-0 top-0 h-12 bg-gradient-to-b from-black/45 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none"
                 style={{ opacity: isSelected ? 1 : undefined }} />

            {/* Select checkbox */}
            {selectable && (
              <button
                className={`absolute top-1.5 left-1.5 w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                  isSelected
                    ? 'bg-indigo-500 text-white scale-100'
                    : 'bg-black/30 text-white/90 opacity-0 group-hover:opacity-100 hover:bg-black/50'
                }`}
                onClick={(e) => { e.stopPropagation(); onToggleSelect?.(photo, index, e.shiftKey) }}
                title="Auswählen"
              >
                <Check size={15} strokeWidth={3} className={isSelected ? 'opacity-100' : 'opacity-70'} />
              </button>
            )}

            {/* Video badge */}
            {photo.is_video && (
              <div className="absolute bottom-1.5 left-1.5 bg-black/60 rounded px-1.5 py-0.5 flex items-center gap-1 pointer-events-none">
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
              <div className="absolute bottom-1.5 right-1.5 flex gap-0.5 pointer-events-none">
                {Array.from({ length: photo.user_rating }).map((_, i) => (
                  <Star key={i} size={8} fill="gold" className="text-yellow-400" />
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function JustifiedGrid({ photos, rowHeight = 200, gap = 4, onPhotoClick, onFavoriteToggle, selectable, selected, onToggleSelect }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerWidth, setContainerWidth] = useState(0)

  useEffect(() => {
    const ro = new ResizeObserver(([entry]) => setContainerWidth(entry.contentRect.width))
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const rows = buildRows(photos, containerWidth, rowHeight, gap)
  const anySelected = (selected?.size ?? 0) > 0

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
            selectable={selectable}
            selected={selected}
            onToggleSelect={onToggleSelect}
            anySelected={anySelected}
            isLast={ri === rows.length - 1}
          />
        ))}
      </div>
    </div>
  )
}

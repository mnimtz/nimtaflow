import { useState } from 'react'
import { Heart, Play, Star, Check } from 'lucide-react'
import { thumbUrl, type Photo } from '../../lib/api'

export type Indexed = { photo: Photo; index: number }
type RowItem = { photo: Photo; index: number; width: number }

/** Build justified rows: each row is scaled to fill the container width while
 * keeping a uniform height — so aspect ratios are preserved (no distortion) and
 * tiles never overlap. */
export function buildRows(items: Indexed[], containerWidth: number, targetHeight: number, gap: number): RowItem[][] {
  if (!containerWidth) return []
  const rows: RowItem[][] = []
  let row: RowItem[] = []
  let rowWidth = 0
  for (const { photo, index } of items) {
    const aspect = photo.width && photo.height ? photo.width / photo.height : 4 / 3
    const w = targetHeight * Math.max(0.4, Math.min(3, aspect))
    const withGap = rowWidth + w + (row.length ? gap : 0)
    if (withGap > containerWidth && row.length) {
      rows.push(row); row = [{ photo, index, width: w }]; rowWidth = w
    } else {
      row.push({ photo, index, width: w }); rowWidth += w + (row.length > 1 ? gap : 0)
    }
  }
  if (row.length) rows.push(row)
  return rows
}

function TileImage({ photo, isSelected }: { photo: Photo; isSelected: boolean }) {
  const [loaded, setLoaded] = useState(false)
  const [hover, setHover] = useState(false)
  return (
    <div className="absolute inset-0" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      {!loaded && <div className="absolute inset-0 animate-pulse bg-gray-200 dark:bg-gray-800" />}
      <img
        src={thumbUrl(photo, 'medium')} alt={photo.filename} onLoad={() => setLoaded(true)} loading="lazy" draggable={false}
        className={`w-full h-full object-cover transition-all duration-500 ${loaded ? 'opacity-100' : 'opacity-0'} ${isSelected ? 'scale-[0.92]' : 'group-hover:scale-[1.04]'}`}
      />
      {photo.is_video && hover && (
        <img src={`/api/photos/${photo.id}/preview`} alt="" draggable={false}
          className="absolute inset-0 w-full h-full object-cover"
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
      )}
    </div>
  )
}

export interface RowCallbacks {
  onPhotoClick: (index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
  selectable?: boolean
  selected?: Set<number>
  onToggleSelect?: (photo: Photo, index: number, shift: boolean) => void
}

/** Render a set of photos as justified rows. `items` carry global indices. */
export function JustifiedRows({ items, containerWidth, rowHeight, gap, isLastGroup, ...cb }: {
  items: Indexed[]; containerWidth: number; rowHeight: number; gap: number; isLastGroup?: boolean
} & RowCallbacks) {
  const rows = buildRows(items, containerWidth, rowHeight, gap)
  const anySelected = (cb.selected?.size ?? 0) > 0
  return (
    <div className="flex flex-col" style={{ gap }}>
      {rows.map((row, ri) => {
        const totalNatural = row.reduce((s, it) => s + it.width, 0)
        const totalGaps = gap * (row.length - 1)
        let scale = (containerWidth - totalGaps) / totalNatural
        // Last row of a group is usually under-full — never enlarge it (that would
        // crop/zoom a lone photo to full width). Scaling height WITH width keeps
        // every photo's true aspect ratio, so object-cover never distorts.
        const lastRow = ri === rows.length - 1
        if (lastRow) scale = Math.min(scale, 1)
        const rowH = Math.round(rowHeight * scale)
        return (
          <div key={ri} className="flex" style={{ gap, height: rowH }}>
            {row.map(({ photo, index, width }) => {
              const w = Math.floor(width * scale)
              const isSel = cb.selected?.has(photo.id) ?? false
              return (
                <div key={photo.id}
                  className={`relative group overflow-hidden bg-gray-100 dark:bg-gray-800/80 rounded-xl cursor-pointer shrink-0 transition-shadow hover:shadow-lg hover:shadow-black/20 ${isSel ? 'ring-[3px] ring-indigo-500 ring-offset-2 ring-offset-white dark:ring-offset-zinc-950' : ''}`}
                  style={{ width: w, height: rowH }}
                  onClick={e => { if (cb.selectable && anySelected) { cb.onToggleSelect?.(photo, index, (e as any).shiftKey); return } cb.onPhotoClick(index) }}>
                  <TileImage photo={photo} isSelected={isSel} />
                  <div className="absolute inset-x-0 top-0 h-14 bg-gradient-to-b from-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" style={{ opacity: isSel ? 1 : undefined }} />
                  {cb.selectable && (
                    <button onClick={e => { e.stopPropagation(); cb.onToggleSelect?.(photo, index, e.shiftKey) }} title="Auswählen"
                      className={`absolute top-2 left-2 w-6 h-6 rounded-full flex items-center justify-center transition-all ${isSel ? 'bg-indigo-500 text-white' : 'bg-black/35 text-white/90 opacity-0 group-hover:opacity-100 hover:bg-black/55'}`}>
                      <Check size={15} strokeWidth={3} />
                    </button>
                  )}
                  {photo.is_video && (
                    <div className="absolute bottom-2 left-2 bg-black/60 rounded px-1.5 py-0.5 flex items-center gap-1 pointer-events-none">
                      <Play size={10} fill="white" className="text-white" />
                      {photo.duration_seconds != null && (
                        <span className="text-white text-[10px] font-medium">
                          {Math.floor(photo.duration_seconds / 60)}:{String(Math.floor(photo.duration_seconds % 60)).padStart(2, '0')}
                        </span>
                      )}
                    </div>
                  )}
                  <button onClick={e => { e.stopPropagation(); cb.onFavoriteToggle?.(photo) }}
                    className={`absolute top-2 right-2 p-1 rounded-full transition-all ${photo.is_favorite ? 'bg-red-500 text-white opacity-100' : 'bg-black/40 text-white opacity-0 group-hover:opacity-100'}`}>
                    <Heart size={12} fill={photo.is_favorite ? 'white' : 'none'} />
                  </button>
                  {!!photo.user_rating && photo.user_rating > 0 && (
                    <div className="absolute bottom-2 right-2 flex gap-0.5 pointer-events-none">
                      {Array.from({ length: photo.user_rating }).map((_, i) => <Star key={i} size={8} fill="gold" className="text-yellow-400" />)}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </div>
  )
}

/** Group photos (carrying their global index) by day or month. */
export function groupByDate(photos: Photo[], by: 'day' | 'month'): { key: string; label: string; items: Indexed[] }[] {
  const groups: { key: string; label: string; items: Indexed[] }[] = []
  const map = new Map<string, { label: string; items: Indexed[] }>()
  photos.forEach((photo, index) => {
    const ts = photo.taken_at
    let key = 'unknown', label = 'Unbekanntes Datum'
    if (ts) {
      const d = new Date(ts)
      if (by === 'day') {
        key = ts.slice(0, 10)
        label = d.toLocaleDateString('de', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
      } else {
        key = ts.slice(0, 7)
        label = d.toLocaleDateString('de', { month: 'long', year: 'numeric' })
      }
    }
    if (!map.has(key)) { const g = { label, items: [] as Indexed[] }; map.set(key, g); groups.push({ key, ...g } as any) }
    map.get(key)!.items.push({ photo, index })
  })
  // groups array entries reference the same arrays via map
  return groups.map(g => ({ key: g.key, label: map.get(g.key)!.label, items: map.get(g.key)!.items }))
}

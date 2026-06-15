import { useEffect, useRef, useState } from 'react'
import { type Photo } from '../../lib/api'
import { JustifiedRows, groupByDate, type Indexed } from './justified'

type Props = {
  photos: Photo[]
  rowHeight?: number
  gap?: number
  groupBy?: 'none' | 'day' | 'month'
  onPhotoClick: (photo: Photo, index: number) => void
  onFavoriteToggle?: (photo: Photo) => void
  selectable?: boolean
  selected?: Set<number>
  onToggleSelect?: (photo: Photo, index: number, shift: boolean) => void
}

function GroupHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="sticky top-0 z-10 -mx-1 px-1 py-2 mb-2 bg-gradient-to-b from-white via-white/95 to-white/0 dark:from-zinc-950 dark:via-zinc-950/95 dark:to-transparent backdrop-blur-sm flex items-baseline gap-2">
      <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 capitalize">{label}</h3>
      <span className="text-xs text-zinc-400">{count}</span>
    </div>
  )
}

export default function JustifiedGrid({
  photos, rowHeight = 200, gap = 5, groupBy = 'none',
  onPhotoClick, onFavoriteToggle, selectable, selected, onToggleSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  const cb = {
    onPhotoClick: (i: number) => onPhotoClick(photos[i], i),
    onFavoriteToggle, selectable, selected, onToggleSelect,
  }

  const allItems: Indexed[] = photos.map((photo, index) => ({ photo, index }))

  return (
    <div ref={containerRef} className="w-full">
      {groupBy === 'none' ? (
        <JustifiedRows items={allItems} containerWidth={w} rowHeight={rowHeight} gap={gap} isLastGroup {...cb} />
      ) : (
        <div className="space-y-6">
          {groupByDate(photos, groupBy).map((g, gi, arr) => (
            <section key={g.key}>
              <GroupHeader label={g.label} count={g.items.length} />
              <JustifiedRows items={g.items} containerWidth={w} rowHeight={rowHeight} gap={gap} isLastGroup={gi === arr.length - 1} {...cb} />
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

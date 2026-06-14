import { useRef, useEffect, useState, useCallback } from 'react'
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

function scrubberLabel(dateStr: string): string {
  if (dateStr === 'unknown') return '—'
  const d = new Date(dateStr)
  return d.toLocaleDateString('de', { month: 'short', year: 'numeric' })
}

function PhotoThumb({ photo, onClick, onFavorite }: {
  photo: Photo
  onClick: () => void
  onFavorite?: () => void
}) {
  return (
    <div
      className="relative group overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800 cursor-pointer"
      style={{ aspectRatio: (photo.width && photo.height) ? `${photo.width}/${photo.height}` : '4/3' }}
      onClick={onClick}
    >
      <img
        src={`/api/photos/${photo.id}/thumbnail?size=medium`}
        alt={photo.filename}
        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
        loading="lazy"
        draggable={false}
      />
      {photo.is_video && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
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

/** Google-Photos-style draggable date scrubber on the right edge of the scroll area. */
function DateScrubber({ scrollEl, label }: { scrollEl: HTMLElement | null; label: string }) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [frac, setFrac] = useState(0)
  const [active, setActive] = useState(false)

  // follow scroll position
  useEffect(() => {
    if (!scrollEl) return
    const onScroll = () => {
      const max = scrollEl.scrollHeight - scrollEl.clientHeight
      setFrac(max > 0 ? scrollEl.scrollTop / max : 0)
    }
    onScroll()
    scrollEl.addEventListener('scroll', onScroll, { passive: true })
    return () => scrollEl.removeEventListener('scroll', onScroll)
  }, [scrollEl])

  const seek = useCallback((clientY: number) => {
    if (!scrollEl || !trackRef.current) return
    const rect = trackRef.current.getBoundingClientRect()
    const f = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height))
    scrollEl.scrollTop = f * (scrollEl.scrollHeight - scrollEl.clientHeight)
  }, [scrollEl])

  useEffect(() => {
    if (!active) return
    const move = (e: PointerEvent) => { e.preventDefault(); seek(e.clientY) }
    const up = () => setActive(false)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [active, seek])

  return (
    <div
      ref={trackRef}
      className="hidden md:block fixed right-1 top-28 bottom-6 w-8 z-30 group/scrub"
      onPointerDown={(e) => { setActive(true); seek(e.clientY) }}
    >
      <div
        className={`absolute right-1 -translate-y-1/2 flex items-center gap-2 transition-opacity ${
          active ? 'opacity-100' : 'opacity-0 group-hover/scrub:opacity-100'
        }`}
        style={{ top: `${frac * 100}%` }}
      >
        {(active) && (
          <span className="px-2.5 py-1 rounded-lg bg-zinc-900 text-white text-xs font-medium shadow-lg whitespace-nowrap">
            {label}
          </span>
        )}
        <div className="w-3 h-3 rounded-full bg-indigo-500 ring-2 ring-white dark:ring-zinc-900 shadow cursor-grab active:cursor-grabbing" />
      </div>
    </div>
  )
}

export default function TimelineView({ groups, rowHeight = 180, onPhotoClick, onFavoriteToggle }: Props) {
  const allPhotos = groups.flatMap(g => g.photos)
  const rootRef = useRef<HTMLDivElement>(null)
  const headerRefs = useRef<Map<string, HTMLElement>>(new Map())
  const [scrollEl, setScrollEl] = useState<HTMLElement | null>(null)
  const [currentLabel, setCurrentLabel] = useState('')

  // locate the scrollable ancestor
  useEffect(() => {
    let el = rootRef.current?.parentElement
    while (el) {
      const oy = getComputedStyle(el).overflowY
      if (oy === 'auto' || oy === 'scroll') break
      el = el.parentElement
    }
    setScrollEl(el ?? null)
  }, [])

  // track which group is at the top of the viewport
  useEffect(() => {
    if (!scrollEl) return
    const update = () => {
      const top = scrollEl.scrollTop
      let label = groups[0] ? scrubberLabel(groups[0].date) : ''
      for (const g of groups) {
        const h = headerRefs.current.get(g.date)
        if (h && h.offsetTop - scrollEl.offsetTop <= top + 8) label = scrubberLabel(g.date)
        else break
      }
      setCurrentLabel(label)
    }
    update()
    scrollEl.addEventListener('scroll', update, { passive: true })
    return () => scrollEl.removeEventListener('scroll', update)
  }, [scrollEl, groups])

  return (
    <div ref={rootRef} className="w-full space-y-6">
      {groups.map((group) => {
        const { primary, secondary } = formatDateHeader(group.date)
        return (
          <div key={group.date}>
            {/* Sticky date header */}
            <div
              ref={(el) => { if (el) headerRefs.current.set(group.date, el) }}
              className="sticky top-0 z-10 bg-white/90 dark:bg-gray-950/90 backdrop-blur-sm py-2 mb-2 flex items-baseline gap-3"
            >
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

      <DateScrubber scrollEl={scrollEl} label={currentLabel} />
    </div>
  )
}

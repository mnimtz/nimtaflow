import { useRef, useEffect, useState, useCallback } from 'react'
import { type Photo, type TimelineGroup } from '../../lib/api'
import { JustifiedRows, type Indexed } from './justified'

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
  return new Date(dateStr).toLocaleDateString('de', { month: 'short', year: 'numeric' })
}

function DateScrubber({ scrollEl, label }: { scrollEl: HTMLElement | null; label: string }) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [frac, setFrac] = useState(0)
  const [active, setActive] = useState(false)
  useEffect(() => {
    if (!scrollEl) return
    const onScroll = () => {
      const max = scrollEl.scrollHeight - scrollEl.clientHeight
      setFrac(max > 0 ? scrollEl.scrollTop / max : 0)
    }
    onScroll(); scrollEl.addEventListener('scroll', onScroll, { passive: true })
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
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [active, seek])
  return (
    <div ref={trackRef} className="hidden md:block fixed right-1 top-28 bottom-6 w-8 z-30 group/scrub" onPointerDown={e => { setActive(true); seek(e.clientY) }}>
      <div className={`absolute right-1 -translate-y-1/2 flex items-center gap-2 transition-opacity ${active ? 'opacity-100' : 'opacity-0 group-hover/scrub:opacity-100'}`} style={{ top: `${frac * 100}%` }}>
        {active && <span className="px-2.5 py-1 rounded-lg bg-zinc-900 text-white text-xs font-medium shadow-lg whitespace-nowrap">{label}</span>}
        <div className="w-3 h-3 rounded-full bg-indigo-500 ring-2 ring-white dark:ring-zinc-900 shadow cursor-grab active:cursor-grabbing" />
      </div>
    </div>
  )
}

export default function TimelineView({ groups, rowHeight = 180, onPhotoClick, onFavoriteToggle }: Props) {
  const allPhotos = groups.flatMap(g => g.photos)
  const indexOf = new Map(allPhotos.map((p, i) => [p.id, i]))
  const rootRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const headerRefs = useRef<Map<string, HTMLElement>>(new Map())
  const [scrollEl, setScrollEl] = useState<HTMLElement | null>(null)
  const [w, setW] = useState(0)
  const [currentLabel, setCurrentLabel] = useState('')

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    if (containerRef.current) ro.observe(containerRef.current)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    let el = rootRef.current?.parentElement
    while (el) { const oy = getComputedStyle(el).overflowY; if (oy === 'auto' || oy === 'scroll') break; el = el.parentElement }
    setScrollEl(el ?? null)
  }, [])

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
    update(); scrollEl.addEventListener('scroll', update, { passive: true })
    return () => scrollEl.removeEventListener('scroll', update)
  }, [scrollEl, groups])

  return (
    <div ref={rootRef} className="w-full">
      <div ref={containerRef} className="space-y-6">
        {groups.map((group) => {
          const { primary, secondary } = formatDateHeader(group.date)
          const items: Indexed[] = group.photos.map(p => ({ photo: p, index: indexOf.get(p.id)! }))
          return (
            <section key={group.date}>
              <div ref={el => { if (el) headerRefs.current.set(group.date, el) }}
                className="sticky top-0 z-10 py-2 mb-2 bg-gradient-to-b from-white via-white/95 to-white/0 dark:from-zinc-950 dark:via-zinc-950/95 dark:to-transparent backdrop-blur-sm flex items-baseline gap-3">
                <h3 className="text-sm font-semibold text-zinc-900 dark:text-white capitalize">{primary}</h3>
                <span className="text-xs text-zinc-400">{secondary}</span>
                {group.count > group.photos.length && <span className="ml-auto text-xs text-zinc-400">{group.count} Fotos</span>}
              </div>
              <JustifiedRows items={items} containerWidth={w} rowHeight={rowHeight} gap={5} isLastGroup
                onPhotoClick={i => onPhotoClick(allPhotos[i], allPhotos, i)}
                onFavoriteToggle={onFavoriteToggle} />
            </section>
          )
        })}
      </div>
      <DateScrubber scrollEl={scrollEl} label={currentLabel} />
    </div>
  )
}

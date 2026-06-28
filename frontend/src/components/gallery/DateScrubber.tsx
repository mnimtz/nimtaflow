import { useRef, useEffect, useState, useCallback } from 'react'

function monthLabel(gkey?: string | null): string {
  if (!gkey || gkey === 'unknown') return ''
  const d = new Date(gkey.length === 7 ? gkey + '-01' : gkey)
  if (isNaN(+d)) return ''
  return d.toLocaleDateString('de', { month: 'short', year: 'numeric' })
}

/** Google-Photos-style draggable date scrubber on the right edge of the gallery
 * scroll area. Reads the date-group <section> markers rendered by Gallery. */
export default function DateScrubber({ scrollEl }: { scrollEl: HTMLElement | null }) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [frac, setFrac] = useState(0)
  const [active, setActive] = useState(false)
  const [label, setLabel] = useState('')

  useEffect(() => {
    if (!scrollEl) return
    const update = () => {
      const max = scrollEl.scrollHeight - scrollEl.clientHeight
      setFrac(max > 0 ? scrollEl.scrollTop / max : 0)
      const top = scrollEl.getBoundingClientRect().top
      let lbl = ''
      scrollEl.querySelectorAll<HTMLElement>('section[data-gkey]').forEach(sec => {
        if (sec.getBoundingClientRect().top <= top + 72) lbl = sec.dataset.gkey || ''
      })
      setLabel(monthLabel(lbl))
    }
    update()
    scrollEl.addEventListener('scroll', update, { passive: true })
    const ro = new ResizeObserver(update); ro.observe(scrollEl)
    return () => { scrollEl.removeEventListener('scroll', update); ro.disconnect() }
  }, [scrollEl])

  const seek = useCallback((clientY: number) => {
    if (!scrollEl || !trackRef.current) return
    const r = trackRef.current.getBoundingClientRect()
    const f = Math.max(0, Math.min(1, (clientY - r.top) / r.height))
    scrollEl.scrollTop = f * (scrollEl.scrollHeight - scrollEl.clientHeight)
  }, [scrollEl])

  useEffect(() => {
    if (!active) return
    const move = (e: PointerEvent) => { e.preventDefault(); seek(e.clientY) }
    const up = () => setActive(false)
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [active, seek])

  if (!scrollEl) return null
  return (
    <div ref={trackRef} className="hidden md:block absolute right-0.5 top-2 bottom-2 w-9 z-30 group/scrub"
      onPointerDown={e => { setActive(true); seek(e.clientY) }}>
      <div className={`absolute right-1.5 -translate-y-1/2 flex items-center gap-2 transition-opacity ${active ? 'opacity-100' : 'opacity-0 group-hover/scrub:opacity-100'}`}
        style={{ top: `${frac * 100}%` }}>
        {active && label && (
          <span className="px-2.5 py-1 rounded-lg bg-zinc-900 text-white text-xs font-medium shadow-lg whitespace-nowrap">{label}</span>
        )}
        <div className="w-3.5 h-3.5 rounded-full bg-indigo-500 ring-2 ring-white dark:ring-zinc-900 shadow cursor-grab active:cursor-grabbing" />
      </div>
    </div>
  )
}

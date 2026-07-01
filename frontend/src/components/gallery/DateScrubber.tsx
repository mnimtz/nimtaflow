import { useRef, useEffect, useState, useCallback, useMemo } from 'react'

export type Bucket = { month: string; count: number }

function monthLabel(m?: string | null): string {
  if (!m || m === 'unknown') return ''
  const d = new Date(m.length === 7 ? m + '-01' : m)
  if (isNaN(+d)) return ''
  return d.toLocaleDateString('de', { month: 'short', year: 'numeric' })
}

/** Google-Photos-/Immich-style date scrubber on the right edge of the gallery.
 *  Mit `buckets` (Monats-Zählungen vom Server) kennt er die GESAMTE Zeitspanne sofort:
 *  Jahres-Marken sitzen an der richtigen Position, und beim Loslassen springt er zum
 *  Datum — ist der Monat schon geladen, wird hin-gescrollt, sonst via `onJump` nachgeladen.
 *  Ohne buckets: klassisches proportionales Scrollen über den geladenen Inhalt. */
export default function DateScrubber({ scrollEl, buckets, onJump }: {
  scrollEl: HTMLElement | null
  buckets?: Bucket[]
  onJump?: (month: string) => void
}) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [frac, setFrac] = useState(0)
  const [active, setActive] = useState(false)
  const [label, setLabel] = useState('')

  const total = useMemo(() => buckets?.reduce((s, b) => s + b.count, 0) ?? 0, [buckets])
  // Kumulative Startfraktion je Monat (0 = neuestes … 1 = ältestes).
  const startFrac = useMemo(() => {
    const m = new Map<string, number>()
    if (buckets && total) { let acc = 0; for (const b of buckets) { m.set(b.month, acc / total); acc += b.count } }
    return m
  }, [buckets, total])
  // Jahres-Marken an ihrer Startposition.
  const ticks = useMemo(() => {
    const out: { y: string; f: number }[] = []
    if (buckets && total) { let acc = 0; const seen = new Set<string>()
      for (const b of buckets) { const y = b.month.slice(0, 4); if (!seen.has(y)) { seen.add(y); out.push({ y, f: acc / total }) } acc += b.count } }
    return out
  }, [buckets, total])
  const monthAtFrac = useCallback((f: number): string | null => {
    if (!buckets || !total) return null
    const target = f * total; let acc = 0
    for (const b of buckets) { acc += b.count; if (acc >= target) return b.month }
    return buckets[buckets.length - 1]?.month ?? null
  }, [buckets, total])

  // Thumb-Position + Label aus der obersten sichtbaren Sektion ableiten.
  useEffect(() => {
    if (!scrollEl) return
    const update = () => {
      const top = scrollEl.getBoundingClientRect().top
      let gkey = ''
      scrollEl.querySelectorAll<HTMLElement>('section[data-gkey]').forEach(sec => {
        if (sec.getBoundingClientRect().top <= top + 72) gkey = sec.dataset.gkey || ''
      })
      if (buckets && total) {
        const f = startFrac.get(gkey?.slice(0, 7)) // day-key → Monat
        if (f != null) setFrac(f)
        else { const max = scrollEl.scrollHeight - scrollEl.clientHeight; setFrac(max > 0 ? scrollEl.scrollTop / max : 0) }
      } else {
        const max = scrollEl.scrollHeight - scrollEl.clientHeight
        setFrac(max > 0 ? scrollEl.scrollTop / max : 0)
      }
      if (!active) setLabel(monthLabel(gkey))
    }
    update()
    scrollEl.addEventListener('scroll', update, { passive: true })
    const ro = new ResizeObserver(update); ro.observe(scrollEl)
    return () => { scrollEl.removeEventListener('scroll', update); ro.disconnect() }
  }, [scrollEl, buckets, total, startFrac, active])

  const fracAt = useCallback((clientY: number) => {
    const r = trackRef.current!.getBoundingClientRect()
    return Math.max(0, Math.min(1, (clientY - r.top) / r.height))
  }, [])

  // Ziehen: Timeline-Modus zeigt nur die Vorschau (Label), springt erst beim Loslassen.
  // Ohne buckets: live proportional scrollen (altes Verhalten).
  const onDrag = useCallback((clientY: number) => {
    if (!scrollEl || !trackRef.current) return
    const f = fracAt(clientY)
    setFrac(f)
    if (buckets && total) {
      setLabel(monthLabel(monthAtFrac(f)))
    } else {
      scrollEl.scrollTop = f * (scrollEl.scrollHeight - scrollEl.clientHeight)
    }
  }, [scrollEl, buckets, total, monthAtFrac, fracAt])

  const commit = useCallback((clientY: number) => {
    if (!scrollEl || !(buckets && total)) return
    const month = monthAtFrac(fracAt(clientY))
    if (!month) return
    // Schon geladen? → hin-scrollen. Sonst via Datum-Anker nachladen.
    const sec = scrollEl.querySelector<HTMLElement>(`section[data-gkey^="${month}"]`)
    if (sec) sec.scrollIntoView({ block: 'start' })
    else onJump?.(month)
  }, [scrollEl, buckets, total, monthAtFrac, fracAt, onJump])

  useEffect(() => {
    if (!active) return
    const move = (e: PointerEvent) => { e.preventDefault(); onDrag(e.clientY) }
    const up = (e: PointerEvent) => { commit(e.clientY); setActive(false) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [active, onDrag, commit])

  if (!scrollEl) return null
  return (
    <div ref={trackRef} className="hidden md:block absolute right-0.5 top-2 bottom-2 w-9 z-30 group/scrub"
      onPointerDown={e => { setActive(true); onDrag(e.clientY) }}>
      {/* Jahres-Marken (nur mit buckets) */}
      {ticks.map(t => (
        <div key={t.y} className="absolute right-5 -translate-y-1/2 text-[10px] tabular-nums text-zinc-400/70 dark:text-zinc-500
          opacity-0 group-hover/scrub:opacity-100 transition-opacity pointer-events-none" style={{ top: `${t.f * 100}%` }}>
          {t.y}
        </div>
      ))}
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

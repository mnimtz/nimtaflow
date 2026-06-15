import { useEffect, useRef, useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, X, Network, Image as ImageIcon } from 'lucide-react'
import { api } from '../lib/api'
import GalleryLightbox from '../components/gallery/GalleryLightbox'

interface GNode { id: number; name: string; named: boolean; face_count: number }
interface GEdge { id: number; from: number; to: number; type: string; category: string; directed: boolean }
interface Pos { x: number; y: number; vx: number; vy: number }

const CAT_COLOR: Record<string, string> = { family: '#10b981', social: '#0ea5e9', other: '#a1a1aa' }
const TYPE_LABEL: Record<string, string> = {
  parent: 'Elternteil', grandparent: 'Großelternteil', partner: 'Partner', sibling: 'Geschwister',
  relative: 'Verwandt', friend: 'Freund', colleague: 'Kollege', other: 'Sonstige',
}
const W = 1000, H = 680

export default function RelationshipsPage() {
  const qc = useQueryClient()
  const { data } = useQuery<{ nodes: GNode[]; edges: GEdge[] }>({
    queryKey: ['rel-graph'], queryFn: () => api.get('/relationships/graph').then(r => r.data),
  })
  const nodes = data?.nodes ?? []
  const edges = data?.edges ?? []

  const posRef = useRef<Map<number, Pos>>(new Map())
  const [, setTick] = useState(0)
  const dragRef = useRef<number | null>(null)
  const [sel, setSel] = useState<number | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [lb, setLb] = useState<any[] | null>(null)
  const openPhotos = async (url: string) => {
    const d = await api.get(url).then(r => r.data)
    const items = d.items || d
    if (items && items.length) setLb(items); else setLb([])
  }

  // (re)seed positions when the node set changes
  useEffect(() => {
    const m = posRef.current
    const ids = new Set(nodes.map(n => n.id))
    for (const id of [...m.keys()]) if (!ids.has(id)) m.delete(id)
    nodes.forEach((n, i) => {
      if (!m.has(n.id)) {
        const a = (i / Math.max(1, nodes.length)) * Math.PI * 2
        m.set(n.id, { x: W / 2 + Math.cos(a) * 220, y: H / 2 + Math.sin(a) * 220, vx: 0, vy: 0 })
      }
    })
  }, [nodes])

  // force simulation loop
  useEffect(() => {
    if (!nodes.length) return
    let raf = 0, frames = 0
    const step = () => {
      const m = posRef.current
      const arr = nodes.map(n => ({ n, p: m.get(n.id)! })).filter(x => x.p)
      // repulsion
      for (let i = 0; i < arr.length; i++) for (let j = i + 1; j < arr.length; j++) {
        const a = arr[i].p, b = arr[j].p
        let dx = a.x - b.x, dy = a.y - b.y
        let d2 = dx * dx + dy * dy || 1
        const f = 9000 / d2
        const d = Math.sqrt(d2)
        const ux = dx / d, uy = dy / d
        a.vx += ux * f; a.vy += uy * f; b.vx -= ux * f; b.vy -= uy * f
      }
      // springs on edges
      for (const e of edges) {
        const a = m.get(e.from), b = m.get(e.to)
        if (!a || !b) continue
        const dx = b.x - a.x, dy = b.y - a.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = (d - 150) * 0.02
        const ux = dx / d, uy = dy / d
        a.vx += ux * f; a.vy += uy * f; b.vx -= ux * f; b.vy -= uy * f
      }
      // integrate + center pull + damping
      for (const { p } of arr) {
        p.vx += (W / 2 - p.x) * 0.002; p.vy += (H / 2 - p.y) * 0.002
        p.vx *= 0.85; p.vy *= 0.85
        p.x += Math.max(-30, Math.min(30, p.vx)); p.y += Math.max(-30, Math.min(30, p.vy))
        p.x = Math.max(40, Math.min(W - 40, p.x)); p.y = Math.max(40, Math.min(H - 40, p.y))
      }
      const dragged = dragRef.current
      if (dragged != null) { const p = m.get(dragged); if (p) { p.vx = 0; p.vy = 0 } }
      setTick(t => t + 1)
      frames++
      if (frames < 600) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [nodes, edges])

  const svgRef = useRef<SVGSVGElement>(null)
  const toLocal = (e: React.PointerEvent) => {
    const r = svgRef.current!.getBoundingClientRect()
    return { x: ((e.clientX - r.left) / r.width) * W, y: ((e.clientY - r.top) / r.height) * H }
  }

  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/relationships/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rel-graph'] }),
  })
  const derive = useMutation({
    mutationFn: () => api.post('/relationships/derive').then(r => r.data),
    onSuccess: (data: { created?: number }) => {
      qc.invalidateQueries({ queryKey: ['rel-graph'] })
      const n = data?.created ?? 0
      if (n > 0) alert(`${n} neue Verbindung(en) abgeleitet (Geschwister/Großeltern).`)
      else alert('Keine neuen Verbindungen ableitbar.\n\nAbgeleitet werden Geschwister (gemeinsame Eltern) und Großeltern (Eltern eines Elternteils). Lege dafür zuerst „Elternteil"-Verbindungen an.')
    },
    onError: () => alert('Ableiten fehlgeschlagen.'),
  })

  const byId = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const selNode = sel != null ? byId.get(sel) : null
  const selEdges = edges.filter(e => e.from === sel || e.to === sel)

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white flex items-center gap-2"><Network size={22} /> Beziehungen</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Familien- & Freundes-Netzwerk · {nodes.length} Personen, {edges.length} Verbindungen</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => derive.mutate()} disabled={derive.isPending}
            className="px-3.5 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
            title="Geschwister & Großeltern automatisch aus Eltern-Verbindungen ableiten">
            {derive.isPending ? 'Leite ab…' : 'Verwandtschaft ableiten'}
          </button>
          <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
            <Plus size={15} /> Verbindung
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        {Object.entries({ family: 'Familie', social: 'Sozial', other: 'Sonstige' }).map(([k, lbl]) => (
          <span key={k} className="flex items-center gap-1.5"><span className="w-3 h-0.5 rounded" style={{ background: CAT_COLOR[k] }} /> {lbl}</span>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900/40 overflow-hidden">
          <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-[680px] touch-none"
            onPointerMove={e => { const id = dragRef.current; if (id != null) { const p = posRef.current.get(id); const l = toLocal(e); if (p) { p.x = l.x; p.y = l.y } } }}
            onPointerUp={() => { dragRef.current = null }} onPointerLeave={() => { dragRef.current = null }}>
            <defs>
              <clipPath id="rel-clip" clipPathUnits="objectBoundingBox"><circle cx="0.5" cy="0.5" r="0.5" /></clipPath>
              <marker id="rel-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="#10b981" />
              </marker>
            </defs>
            {edges.map(e => {
              const a = posRef.current.get(e.from), b = posRef.current.get(e.to)
              if (!a || !b) return null
              const hi = sel == null || e.from === sel || e.to === sel
              return (
                <line key={e.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke={CAT_COLOR[e.category]} strokeWidth={hi ? 2.5 : 1} strokeOpacity={hi ? 0.9 : 0.25}
                  markerEnd={e.directed ? 'url(#rel-arrow)' : undefined}>
                  <title>{TYPE_LABEL[e.type] || e.type}</title>
                </line>
              )
            })}
            {nodes.map(n => {
              const p = posRef.current.get(n.id); if (!p) return null
              const R = 26, active = sel === n.id
              return (
                <g key={n.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: 'grab' }}
                  onPointerDown={e => { (e.target as Element).setPointerCapture?.(e.pointerId); dragRef.current = n.id; setSel(n.id) }}>
                  <circle r={R + 2} fill={active ? '#6366f1' : '#27272a'} />
                  <circle r={R} fill="#3f3f46" />
                  <image x={-R} y={-R} width={R * 2} height={R * 2} href={`/api/people/${n.id}/avatar`} clipPath="url(#rel-clip)" preserveAspectRatio="xMidYMid slice" />
                  <text y={R + 14} textAnchor="middle" fontSize="12" fontWeight="600"
                    fill={active ? '#818cf8' : 'currentColor'} className="text-zinc-700 dark:text-zinc-200 select-none pointer-events-none">
                    {n.name.length > 16 ? n.name.slice(0, 15) + '…' : n.name}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>

        {/* Side panel: selected person's relationships */}
        <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 p-4">
          {selNode ? (
            <>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-9 h-9 rounded-full overflow-hidden bg-zinc-200 dark:bg-zinc-800 relative">
                  <img src={`/api/people/${selNode.id}/avatar`} className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                </div>
                <p className="font-semibold text-zinc-900 dark:text-white truncate flex-1">{selNode.name}</p>
              </div>
              <button onClick={() => openPhotos(`/people/${sel}/photos?limit=200`)}
                className="w-full mb-3 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
                <ImageIcon size={15} /> Fotos ansehen ({selNode.face_count})
              </button>
              {selEdges.length === 0 ? (
                <p className="text-sm text-zinc-500">Noch keine Verbindungen. Lege oben eine an.</p>
              ) : (
                <ul className="space-y-1.5">
                  {selEdges.map(e => {
                    const other = byId.get(e.from === sel ? e.to : e.from)
                    const label = e.directed ? (e.from === sel ? TYPE_LABEL[e.type] + ' von' : 'Kind von') : TYPE_LABEL[e.type]
                    return (
                      <li key={e.id} className="flex items-center gap-2 text-sm group">
                        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: CAT_COLOR[e.category] }} />
                        <span className="text-zinc-500 text-xs">{label}</span>
                        <span className="text-zinc-800 dark:text-zinc-200 truncate flex-1">{other?.name}</span>
                        {other && (
                          <button onClick={() => openPhotos(`/relationships/together/${sel}/${other.id}`)}
                            title="Gemeinsame Fotos" className="text-zinc-400 hover:text-indigo-500"><ImageIcon size={14} /></button>
                        )}
                        <button onClick={() => del.mutate(e.id)} className="opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-red-500"><Trash2 size={13} /></button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </>
          ) : (
            <p className="text-sm text-zinc-500">Klicke eine Person im Graphen an, um ihre Verbindungen zu sehen. Knoten lassen sich ziehen.</p>
          )}
        </div>
      </div>

      {showAdd && <AddRelationModal nodes={nodes} preselect={sel} onClose={() => setShowAdd(false)}
        onSaved={() => { qc.invalidateQueries({ queryKey: ['rel-graph'] }); setShowAdd(false) }} />}
      {lb && lb.length > 0 && <GalleryLightbox photos={lb as any} index={0} onClose={() => setLb(null)} />}
      {lb && lb.length === 0 && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60" onClick={() => setLb(null)}>
          <div className="px-4 py-3 rounded-xl bg-zinc-900 text-zinc-200 text-sm">Keine gemeinsamen Fotos gefunden.</div>
        </div>
      )}
    </div>
  )
}

function AddRelationModal({ nodes, preselect, onClose, onSaved }: {
  nodes: GNode[]; preselect: number | null; onClose: () => void; onSaved: () => void
}) {
  const [from, setFrom] = useState<number | ''>(preselect ?? '')
  const [to, setTo] = useState<number | ''>('')
  const [type, setType] = useState('parent')
  const sorted = [...nodes].sort((a, b) => a.name.localeCompare(b.name))
  const sel = 'w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'
  const save = useMutation({
    mutationFn: () => api.post('/relationships', { from_person_id: from, to_person_id: to, rel_type: type }),
    onSuccess: onSaved,
  })
  const directedHint = type === 'parent' ? '„A ist Elternteil von B"' : type === 'grandparent' ? '„A ist Großelternteil von B"' : 'Reihenfolge egal'

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-200 dark:border-zinc-800">
          <h2 className="text-base font-semibold text-zinc-900 dark:text-white">Verbindung hinzufügen</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Person A</label>
            <select value={from} onChange={e => setFrom(Number(e.target.value))} className={sel}>
              <option value="">— wählen —</option>
              {sorted.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Beziehung</label>
            <select value={type} onChange={e => setType(e.target.value)} className={sel}>
              {Object.entries(TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <p className="text-xs text-zinc-500 mt-1">{directedHint}</p>
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Person B</label>
            <select value={to} onChange={e => setTo(Number(e.target.value))} className={sel}>
              <option value="">— wählen —</option>
              {sorted.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
            </select>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={onClose} className="px-3.5 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Abbrechen</button>
            <button onClick={() => save.mutate()} disabled={!from || !to || from === to || save.isPending}
              className="px-3.5 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">Speichern</button>
          </div>
        </div>
      </div>
    </div>
  )
}

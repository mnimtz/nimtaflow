import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import { Sparkles, X, ArrowUp, Loader2, MapPin } from 'lucide-react'
import { api } from '../lib/api'
import { useAssistant } from '../store/assistant'

type Msg = { role: 'user' | 'assistant'; content: string; photoCount?: number; ids?: number[]; suggestions?: string[]; query?: string }

const VIEW_LABEL: Record<string, string> = {
  '/': 'Start', '/gallery': 'Galerie', '/map': 'Karte', '/people': 'Personen',
  '/albums': 'Alben', '/trips': 'Reisen', '/highlights': 'Highlights',
}

/** Ambient-KI-Assistent (Phase 1): schwebt überall, filtert die Galerie auf die Antwort. */
export default function FloatingAssistant() {
  const nav = useNavigate()
  const loc = useLocation()
  const { open, setOpen, toggle, setResult } = useAssistant()
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Steuerung aus den Einstellungen (Kategorie „Chat-Assistent").
  const { data: cfg } = useQuery<Record<string, string>>({
    queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 30_000,
  })
  const assistantOn = (cfg?.['features.assistant'] ?? 'true') !== 'false'
  const steerGallery = (cfg?.['assistant.steer.gallery'] ?? 'true') !== 'false'
  const steerMap = (cfg?.['assistant.steer.map'] ?? 'true') !== 'false'

  useEffect(() => { scrollRef.current?.scrollTo({ top: 1e9 }) }, [messages, busy])

  if (!assistantOn) return null

  const context = VIEW_LABEL[loc.pathname] || null

  async function send(preset?: string) {
    const text = (preset ?? input).trim()
    if (!text || busy) return
    if (preset === undefined) setInput('')
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: text }])
    setBusy(true)
    try {
      const r = await api.post('/chat', { message: text, history })
      // result_ids = volles Such-Set (alle Treffer) → Galerie-Filter; Fallback: zitierte photo_ids.
      const ids: number[] = (r.data.result_ids && r.data.result_ids.length ? r.data.result_ids : r.data.photo_ids) || []
      const suggestions: string[] = Array.isArray(r.data.suggestions) ? r.data.suggestions : []
      setMessages(m => [...m, { role: 'assistant', content: r.data.answer || '…', photoCount: ids.length, ids, suggestions, query: text }])
      if (ids.length) {
        setResult(ids, text)
        // Auf der Karte bleiben (sie filtert sich selbst); sonst — wenn erlaubt — zur Galerie.
        if (loc.pathname === '/map') { /* bleibt auf der Karte */ }
        else if (steerGallery && loc.pathname !== '/gallery') nav('/gallery')
      }
    } catch {
      setMessages(m => [...m, { role: 'assistant', content: 'Gerade nicht erreichbar — bitte gleich nochmal.' }])
    } finally {
      setBusy(false)
    }
  }

  // Ergebnis dieser Nachricht auf der Karte zeigen (nutzt das geteilte Ergebnis-Set).
  function showOnMap(msg: Msg) {
    if (msg.ids && msg.ids.length) setResult(msg.ids, msg.query || '')
    nav('/map')
  }

  return (
    <>
      {open && (
        <div className="fixed z-[90] bottom-24 right-4 md:bottom-24 md:right-6 w-[92vw] max-w-[340px]
          rounded-2xl border border-zinc-700/70 bg-zinc-900/90 backdrop-blur-xl text-white shadow-2xl overflow-hidden flex flex-col"
          style={{ maxHeight: 'min(70vh, 560px)' }}>
          <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-white/10">
            <span className="flex items-center gap-2 font-medium text-sm">
              <Sparkles size={16} className="text-indigo-400" /> Assistent
            </span>
            <span className="flex items-center gap-2">
              {context && <span className="text-[11px] text-zinc-400 border border-white/10 rounded-full px-2 py-0.5">in {context}</span>}
              <button onClick={() => setOpen(false)} className="text-zinc-400 hover:text-white"><X size={16} /></button>
            </span>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
            {messages.length === 0 && (
              <div className="text-[13px] text-zinc-400 leading-relaxed">
                Frag mich etwas zu deinen Fotos — z. B. <span className="text-zinc-200">„Zeig mir Fotos vom Meer"</span>, <span className="text-zinc-200">„Fotos aus dem letzten Sommer"</span> oder <span className="text-zinc-200">„Wie viele Fotos habe ich?"</span>. Die Treffer erscheinen direkt in der Galerie.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex flex-col items-start'}>
                <div className={`max-w-[85%] text-[13px] leading-relaxed rounded-xl px-2.5 py-1.5 ${
                  m.role === 'user' ? 'self-end bg-indigo-600 text-white' : 'bg-white/10 text-zinc-100'}`}>
                  {m.content}
                  {m.role === 'assistant' && !!m.photoCount && (steerGallery || steerMap) && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
                      {steerGallery && (
                        <button onClick={() => nav('/gallery')} className="flex items-center gap-1 text-[11px] text-indigo-300 hover:text-indigo-200">
                          <Sparkles size={11} /> {m.photoCount} in der Galerie
                        </button>
                      )}
                      {steerMap && (
                        <button onClick={() => showOnMap(m)} className="flex items-center gap-1 text-[11px] text-indigo-300 hover:text-indigo-200">
                          <MapPin size={11} /> Auf der Karte
                        </button>
                      )}
                    </div>
                  )}
                </div>
                {/* Proaktive Folge-Vorschläge als antippbare Chips */}
                {m.role === 'assistant' && m.suggestions && m.suggestions.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {m.suggestions.map((s, k) => (
                      <button key={k} onClick={() => send(s)} disabled={busy}
                        className="px-2.5 py-1 rounded-full bg-white/5 border border-white/15 text-[11px] text-zinc-200 hover:bg-white/10 hover:border-indigo-400/50 disabled:opacity-40 transition-colors">
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="flex items-center gap-2 text-[12px] text-zinc-400"><Loader2 size={13} className="animate-spin" /> denkt nach…</div>}
          </div>

          <div className="flex items-center gap-2 px-3 py-2.5 border-t border-white/10">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') send() }}
              placeholder="Frag den Assistenten…"
              className="flex-1 h-9 px-3 text-sm rounded-lg bg-white/5 border border-white/10 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={() => send()} disabled={busy || !input.trim()}
              className="w-9 h-9 shrink-0 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center disabled:opacity-40">
              <ArrowUp size={16} />
            </button>
          </div>
        </div>
      )}

      <button onClick={toggle} aria-label="KI-Assistent"
        className="fixed z-[91] bottom-20 right-4 md:bottom-6 md:right-6 w-13 h-13 rounded-full
          bg-indigo-600 hover:bg-indigo-500 text-white shadow-xl flex items-center justify-center transition-transform active:scale-95"
        style={{ width: 52, height: 52 }}>
        {open ? <X size={22} /> : <Sparkles size={22} />}
      </button>
    </>
  )
}

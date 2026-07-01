import { useState, useRef, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Sparkles, X, ArrowUp, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAssistant } from '../store/assistant'

type Msg = { role: 'user' | 'assistant'; content: string; photoCount?: number }

const VIEW_LABEL: Record<string, string> = {
  '/': 'Start', '/gallery': 'Galerie', '/map': 'Karte', '/people': 'Personen',
  '/albums': 'Alben', '/trips': 'Reisen', '/highlights': 'Highlights',
}

/** Ambient-KI-Assistent (Phase 1): schwebt überall, filtert die Galerie auf die Antwort. */
export default function FloatingAssistant() {
  const nav = useNavigate()
  const loc = useLocation()
  const { enabled, open, setOpen, toggle, setResult } = useAssistant()
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => { scrollRef.current?.scrollTo({ top: 1e9 }) }, [messages, busy])

  if (!enabled) return null

  const context = VIEW_LABEL[loc.pathname] || null

  async function send() {
    const text = input.trim()
    if (!text || busy) return
    setInput('')
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: text }])
    setBusy(true)
    try {
      const r = await api.post('/chat', { message: text, history })
      const ids: number[] = r.data.photo_ids || []
      setMessages(m => [...m, { role: 'assistant', content: r.data.answer || '…', photoCount: ids.length }])
      if (ids.length) {
        setResult(ids, text)
        if (loc.pathname !== '/gallery') nav('/gallery')
      }
    } catch {
      setMessages(m => [...m, { role: 'assistant', content: 'Gerade nicht erreichbar — bitte gleich nochmal.' }])
    } finally {
      setBusy(false)
    }
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
                Frag mich etwas zu deinen Fotos — z. B. <span className="text-zinc-200">„Zeig Strandfotos von Lea 2022"</span> oder <span className="text-zinc-200">„Wann lernte Lea laufen?"</span>. Die Treffer erscheinen direkt in der Galerie.
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                <div className={`max-w-[85%] text-[13px] leading-relaxed rounded-xl px-2.5 py-1.5 ${
                  m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-white/10 text-zinc-100'}`}>
                  {m.content}
                  {m.role === 'assistant' && !!m.photoCount && (
                    <button onClick={() => nav('/gallery')} className="mt-1.5 flex items-center gap-1 text-[11px] text-indigo-300 hover:text-indigo-200">
                      <Sparkles size={11} /> {m.photoCount} Treffer in der Galerie ansehen
                    </button>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="flex items-center gap-2 text-[12px] text-zinc-400"><Loader2 size={13} className="animate-spin" /> denkt nach…</div>}
          </div>

          <div className="flex items-center gap-2 px-3 py-2.5 border-t border-white/10">
            <input value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') send() }}
              placeholder="Frag den Assistenten…"
              className="flex-1 h-9 px-3 text-sm rounded-lg bg-white/5 border border-white/10 text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={send} disabled={busy || !input.trim()}
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

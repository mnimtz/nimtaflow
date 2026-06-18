import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Send, Sparkles, Loader2, Cpu, Cloud } from 'lucide-react'
import { api, thumbUrl, type Photo } from '../lib/api'
import GalleryLightbox from '../components/gallery/GalleryLightbox'

type Msg = { role: 'user' | 'assistant'; content: string; photo_ids?: number[] }

const EXAMPLES = [
  'Zeig mir Fotos von Lea am Strand',
  'Wann waren wir das letzte Mal im Zoo?',
  'Welche Bilder gibt es von Weihnachten mit der ganzen Familie?',
  'Auf welchen Fotos ist ein Hund zu sehen?',
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [provider, setProvider] = useState('')   // '' = Server-Standard
  const [lightbox, setLightbox] = useState<{ photos: Photo[]; index: number } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const { data: status } = useQuery<{ provider: string; gemini_ready: boolean }>({
    queryKey: ['chat-status'], queryFn: () => api.get('/chat/status').then(r => r.data),
  })
  const eff = provider || status?.provider || 'gemini'

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, sending])

  const send = async (text: string) => {
    text = text.trim()
    if (!text || sending) return
    const history = messages.map(m => ({ role: m.role, content: m.content }))
    setMessages(m => [...m, { role: 'user', content: text }])
    setInput('')
    setSending(true)
    try {
      const r = await api.post('/chat', { message: text, history, provider: provider || undefined })
      setMessages(m => [...m, { role: 'assistant', content: r.data.answer || '(keine Antwort)', photo_ids: r.data.photo_ids || [] }])
    } catch (e: any) {
      setMessages(m => [...m, { role: 'assistant', content: 'Fehler: ' + (e?.response?.data?.detail || e?.message || 'unbekannt') }])
    } finally { setSending(false) }
  }

  // Open chat results IN-APP (lightbox), not in a new browser tab. Fetches the
  // full Photo objects for the message's ids so videos play + dimensions are right.
  const openLightbox = async (ids: number[], idx: number) => {
    try {
      const photos = await Promise.all(ids.map(id => api.get(`/photos/${id}`).then(r => r.data as Photo)))
      setLightbox({ photos, index: idx })
    } catch { /* ignore */ }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] md:h-screen max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles size={18} className="text-indigo-500 shrink-0" />
          <div className="min-w-0">
            <h1 className="text-base font-bold text-zinc-900 dark:text-white leading-tight">Foto-Chat</h1>
            <p className="text-[11px] text-zinc-500 truncate">Stell Fragen zu deiner Sammlung — beantwortet nur anhand gefundener Fotos.</p>
          </div>
        </div>
        {/* Provider-Umschalter */}
        <div className="flex items-center gap-1 text-xs shrink-0">
          {([
            { id: 'gemini', label: 'Gemini', icon: Cloud, note: 'Cloud · Kosten' },
            { id: 'local', label: 'Lokal', icon: Cpu, note: 'Qwen · gratis' },
          ] as const).map(p => (
            <button key={p.id} onClick={() => setProvider(p.id === (status?.provider || 'gemini') ? '' : p.id)}
              title={p.note}
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg border transition ${
                eff === p.id
                  ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-300'
                  : 'border-zinc-300 dark:border-zinc-700 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}>
              <p.icon size={13} /> {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5">
        {messages.length === 0 && (
          <div className="text-center mt-10 space-y-5">
            <p className="text-sm text-zinc-500">Frag mich etwas über deine Fotos:</p>
            <div className="flex flex-col items-center gap-2">
              {EXAMPLES.map(ex => (
                <button key={ex} onClick={() => send(ex)}
                  className="px-3.5 py-2 rounded-xl border border-zinc-200 dark:border-zinc-700 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition">
                  „{ex}"
                </button>
              ))}
            </div>
            {eff === 'gemini' && !status?.gemini_ready && (
              <p className="text-xs text-amber-500">Kein Gemini-API-Key hinterlegt — wähle „Lokal" oder trag den Key unter Einstellungen → Bilder-AI ein.</p>
            )}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
            <div className={`max-w-[85%] ${m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-100'} rounded-2xl px-4 py-2.5`}>
              <p className="text-sm whitespace-pre-wrap leading-relaxed">{m.content}</p>
              {m.photo_ids && m.photo_ids.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  {m.photo_ids.slice(0, 12).map((id, idx) => (
                    <button key={id} onClick={() => openLightbox(m.photo_ids!.slice(0, 12), idx)}
                      className="block w-16 h-16 rounded-lg overflow-hidden border border-black/10 hover:ring-2 hover:ring-indigo-400 transition">
                      <img src={thumbUrl({ id }, 'small')} className="w-full h-full object-cover" loading="lazy" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-zinc-100 dark:bg-zinc-800 rounded-2xl px-4 py-3 flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 size={15} className="animate-spin" /> sucht in den Fotos…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-zinc-200 dark:border-zinc-800 p-3">
        <div className="flex items-end gap-2">
          <textarea ref={taRef} value={input} onChange={e => setInput(e.target.value)} rows={1}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            placeholder="Frage zu deinen Fotos… (Enter zum Senden)"
            className="flex-1 resize-none max-h-32 px-3.5 py-2.5 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-900 dark:text-white placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <button onClick={() => send(input)} disabled={sending || !input.trim()}
            className="p-2.5 rounded-xl bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 transition shrink-0">
            <Send size={18} />
          </button>
        </div>
      </div>

      {lightbox && (
        <GalleryLightbox
          photos={lightbox.photos}
          index={lightbox.index}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  )
}

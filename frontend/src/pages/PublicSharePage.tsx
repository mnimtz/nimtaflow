import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Lock, Download, X, Loader2 } from 'lucide-react'

type Item = { id: number; is_video: boolean; width?: number; height?: number }
type Meta = { type: string; title?: string; requires_password: boolean; allow_download: boolean; items: Item[] }

/** Login-free guest view for a shared album / photo / trip. */
export default function PublicSharePage() {
  const { token = '' } = useParams()
  const [meta, setMeta] = useState<Meta | null>(null)
  const [pw, setPw] = useState('')
  const [pwInput, setPwInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lightbox, setLightbox] = useState<Item | null>(null)

  const load = useCallback(async (password?: string) => {
    setLoading(true); setError(null)
    try {
      const q = password ? `?pw=${encodeURIComponent(password)}` : ''
      const r = await fetch(`/api/public/${token}${q}`)
      if (r.status === 404) { setError('Dieser Link ist ungültig oder abgelaufen.'); setMeta(null); return }
      if (!r.ok) { setError('Inhalt konnte nicht geladen werden.'); return }
      const data = (await r.json()) as Meta
      setMeta(data)
      if (password && !data.requires_password) setPw(password)
    } catch { setError('Netzwerkfehler.') } finally { setLoading(false) }
  }, [token])

  useEffect(() => { load() }, [load])

  const mediaUrl = (it: Item, kind: 'thumbnail' | 'original' | 'video', size = 'medium') => {
    const base = `/api/public/${token}/photo/${it.id}/${kind === 'video' ? 'video/stream' : kind}`
    const params = new URLSearchParams()
    if (kind === 'thumbnail') params.set('size', size)
    if (pw) params.set('pw', pw)
    const qs = params.toString()
    return qs ? `${base}?${qs}` : base
  }

  if (loading && !meta) return <Centered><Loader2 className="animate-spin" /></Centered>
  if (error) return <Centered><p className="text-zinc-400">{error}</p></Centered>
  if (!meta) return null

  if (meta.requires_password) {
    return (
      <Centered>
        <div className="w-full max-w-xs text-center space-y-4">
          <Lock className="mx-auto text-indigo-400" size={32} />
          <p className="text-zinc-300">Dieser Link ist passwortgeschützt.</p>
          <input type="password" value={pwInput} onChange={e => setPwInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') load(pwInput) }}
            placeholder="Passwort" autoFocus
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white" />
          <button onClick={() => load(pwInput)}
            className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white py-2.5 text-sm font-medium">
            Ansehen
          </button>
        </div>
      </Centered>
    )
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white">
      <header className="px-5 py-4 border-b border-zinc-800 sticky top-0 bg-zinc-950/90 backdrop-blur z-10">
        <h1 className="text-lg font-semibold">{meta.title || 'Geteilte Galerie'}</h1>
        <p className="text-xs text-zinc-500">{meta.items.length} Medien · geteilt über NimtaFlow</p>
      </header>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1 p-1">
        {meta.items.map(it => (
          <button key={it.id} onClick={() => setLightbox(it)} className="relative aspect-square overflow-hidden bg-zinc-900">
            <img src={mediaUrl(it, 'thumbnail', 'medium')} loading="lazy" className="w-full h-full object-cover" />
            {it.is_video && <span className="absolute bottom-1 left-1 text-xs">▶︎</span>}
          </button>
        ))}
      </div>

      {lightbox && (
        <div className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center" onClick={() => setLightbox(null)}>
          <button onClick={() => setLightbox(null)} className="absolute top-4 right-4 text-white/80 hover:text-white"><X size={28} /></button>
          {lightbox.is_video ? (
            <video src={mediaUrl(lightbox, 'video')} controls autoPlay className="max-h-[90vh] max-w-[95vw]" onClick={e => e.stopPropagation()} />
          ) : (
            <img src={mediaUrl(lightbox, 'thumbnail', 'large')} className="max-h-[90vh] max-w-[95vw] object-contain" onClick={e => e.stopPropagation()} />
          )}
          {meta.allow_download && (
            <a href={mediaUrl(lightbox, 'original')} download onClick={e => e.stopPropagation()}
              className="absolute bottom-5 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-full bg-white/15 hover:bg-white/25 px-4 py-2 text-sm">
              <Download size={16} /> Original herunterladen
            </a>
          )}
        </div>
      )}
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-white p-4">{children}</div>
}

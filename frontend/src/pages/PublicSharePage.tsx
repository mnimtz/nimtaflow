import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Lock, Download, X, Loader2, Calendar, MapPin, Image as ImageIcon } from 'lucide-react'
import { useT } from '../i18n'

type Item = {
  id: number; is_video: boolean; width?: number; height?: number
  filename?: string | null; taken_at?: string | null; place?: string | null
}
type Meta = { type: string; title?: string; requires_password: boolean; allow_download: boolean; items: Item[] }

/** Login-free guest view for a shared album / photo / trip. */
export default function PublicSharePage() {
  const { t, lang } = useT()
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
      if (r.status === 404) { setError(t('share.pub.invalidLink')); setMeta(null); return }
      if (!r.ok) { setError(t('share.pub.loadFailed')); return }
      const data = (await r.json()) as Meta
      setMeta(data)
      if (password && !data.requires_password) setPw(password)
    } catch { setError(t('share.pub.networkError')) } finally { setLoading(false) }
  }, [token, t])

  useEffect(() => { load() }, [load])

  const mediaUrl = (it: Item, kind: 'thumbnail' | 'original' | 'video', size = 'medium') => {
    const base = `/api/public/${token}/photo/${it.id}/${kind === 'video' ? 'video/stream' : kind}`
    const params = new URLSearchParams()
    if (kind === 'thumbnail') params.set('size', size)
    if (pw) params.set('pw', pw)
    const qs = params.toString()
    return qs ? `${base}?${qs}` : base
  }

  const fmtDate = (iso?: string | null) => {
    if (!iso) return null
    const d = new Date(iso)
    if (isNaN(d.getTime())) return null
    return d.toLocaleDateString(lang === 'en' ? 'en-US' : 'de-DE',
      { day: 'numeric', month: 'long', year: 'numeric' })
  }

  if (loading && !meta) return <Centered><Loader2 className="animate-spin text-zinc-500" /></Centered>
  if (error) return <Centered><p className="text-zinc-400">{error}</p></Centered>
  if (!meta) return null

  if (meta.requires_password) {
    return (
      <Centered>
        <div className="w-full max-w-xs text-center space-y-4">
          <Lock className="mx-auto text-amber-400" size={32} />
          <p className="text-zinc-300">{t('share.pub.passwordProtected')}</p>
          <input type="password" value={pwInput} onChange={e => setPwInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') load(pwInput) }}
            placeholder={t('share.pub.password')} autoFocus
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-white" />
          <button onClick={() => load(pwInput)}
            className="w-full rounded-lg bg-amber-500 hover:bg-amber-400 text-zinc-950 py-2.5 text-sm font-semibold">
            {t('share.pub.view')}
          </button>
        </div>
      </Centered>
    )
  }

  // Highlight share = a single rendered video.
  if (meta.type === 'highlight') {
    const vurl = `/api/public/${token}/highlight-video${pw ? `?pw=${encodeURIComponent(pw)}` : ''}`
    return (
      <div className="min-h-screen text-white"
        style={{ background: 'radial-gradient(900px 480px at 80% -8%, rgba(232,181,74,.10), transparent 60%), #0a0a0d' }}>
        <header className="px-5 py-4 border-b border-white/10 sticky top-0 bg-[#0a0a0d]/85 backdrop-blur z-10">
          <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
            <h1 className="text-lg font-semibold truncate">{meta.title || t('share.pub.defaultTitle')}</h1>
            <span className="shrink-0 text-base font-extrabold tracking-tight bg-gradient-to-r from-amber-300 to-amber-500 bg-clip-text text-transparent">NimtaFlow</span>
          </div>
        </header>
        <div className="max-w-3xl mx-auto px-4 py-6 sm:py-10">
          <video src={vurl} controls autoPlay playsInline className="w-full rounded-2xl bg-black shadow-2xl" />
          {meta.allow_download && (
            <div className="mt-5 flex justify-center">
              <a href={vurl} download className="inline-flex items-center gap-2 rounded-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold px-5 py-2.5 text-sm">
                {t('share.pub.downloadOriginal')}
              </a>
            </div>
          )}
        </div>
        <footer className="border-t border-white/10 mt-6 py-6 text-center">
          <a href="https://www.nimtaflow.com" target="_blank" rel="noopener"
            className="text-sm font-bold bg-gradient-to-r from-amber-300 to-amber-500 bg-clip-text text-transparent">
            {t('share.pub.sharedVia')} NimtaFlow
          </a>
        </footer>
      </div>
    )
  }

  const items = meta.items
  const single = items.length === 1 ? items[0] : null
  const countLabel = items.length === 1
    ? t('share.pub.mediaCountOne')
    : t('share.pub.mediaCount', { n: items.length })

  const DetailRow = ({ it, className = '' }: { it: Item; className?: string }) => {
    const date = fmtDate(it.taken_at)
    const dims = it.width && it.height ? `${it.width} × ${it.height}` : null
    if (!date && !it.place && !dims) return null
    return (
      <div className={`flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-sm text-zinc-400 ${className}`}>
        {date && <span className="inline-flex items-center gap-1.5"><Calendar size={14} className="text-zinc-500" />{date}</span>}
        {it.place && <span className="inline-flex items-center gap-1.5"><MapPin size={14} className="text-zinc-500" />{it.place}</span>}
        {dims && <span className="inline-flex items-center gap-1.5"><ImageIcon size={14} className="text-zinc-500" />{dims}</span>}
      </div>
    )
  }

  const DownloadBtn = ({ it, big = false }: { it: Item; big?: boolean }) =>
    meta.allow_download ? (
      <a href={mediaUrl(it, 'original')} download onClick={e => e.stopPropagation()}
        className={`inline-flex items-center gap-2 rounded-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold transition
          ${big ? 'px-5 py-2.5 text-sm' : 'px-4 py-2 text-sm'}`}>
        <Download size={16} /> {big ? t('share.pub.downloadOriginal') : t('share.pub.download')}
      </a>
    ) : null

  return (
    <div className="min-h-screen text-white"
      style={{ background: 'radial-gradient(900px 480px at 80% -8%, rgba(232,181,74,.10), transparent 60%), #0a0a0d' }}>
      {/* Header */}
      <header className="px-5 py-4 border-b border-white/10 sticky top-0 bg-[#0a0a0d]/85 backdrop-blur z-10">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold truncate">{meta.title || t('share.pub.defaultTitle')}</h1>
            <p className="text-xs text-zinc-500">{countLabel}</p>
          </div>
          <span className="shrink-0 text-base font-extrabold tracking-tight bg-gradient-to-r from-amber-300 to-amber-500 bg-clip-text text-transparent">
            NimtaFlow
          </span>
        </div>
      </header>

      {/* Single item → hero, multiple → grid */}
      {single ? (
        <div className="max-w-3xl mx-auto px-4 py-6 sm:py-10">
          <div className="rounded-2xl overflow-hidden bg-black/30 border border-white/10 shadow-2xl">
            {single.is_video ? (
              <video src={mediaUrl(single, 'video')} controls playsInline className="w-full max-h-[70vh] bg-black" />
            ) : (
              <button onClick={() => setLightbox(single)} className="block w-full">
                <img src={mediaUrl(single, 'thumbnail', 'large')} className="w-full max-h-[70vh] object-contain bg-black" />
              </button>
            )}
          </div>
          <DetailRow it={single} className="mt-4" />
          <div className="mt-5 flex justify-center">
            {meta.allow_download
              ? <DownloadBtn it={single} big />
              : <span className="text-xs text-zinc-600">{t('share.pub.noDownload')}</span>}
          </div>
        </div>
      ) : (
        <div className="max-w-6xl mx-auto grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5 p-1.5">
          {items.map(it => (
            <button key={it.id} onClick={() => setLightbox(it)}
              className="group relative aspect-square overflow-hidden rounded-md bg-zinc-900">
              <img src={mediaUrl(it, 'thumbnail', 'medium')} loading="lazy"
                className="w-full h-full object-cover transition group-hover:scale-[1.03]" />
              {it.is_video && (
                <span className="absolute bottom-1.5 left-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium">▶︎ {t('share.pub.video')}</span>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-white/10 mt-6 py-6 text-center">
        <a href="https://www.nimtaflow.com" target="_blank" rel="noopener"
          className="text-sm font-bold bg-gradient-to-r from-amber-300 to-amber-500 bg-clip-text text-transparent">
          {t('share.pub.sharedVia')} NimtaFlow
        </a>
        <p className="mt-1 text-xs text-zinc-600">{t('share.pub.poweredBy')}</p>
      </footer>

      {/* Lightbox (used by grid + single image) */}
      {lightbox && (
        <div className="fixed inset-0 z-50 bg-black/95 flex flex-col items-center justify-center" onClick={() => setLightbox(null)}>
          <button onClick={() => setLightbox(null)} className="absolute top-4 right-4 text-white/80 hover:text-white"><X size={28} /></button>
          <div className="flex-1 min-h-0 w-full flex items-center justify-center p-3">
            {lightbox.is_video ? (
              <video src={mediaUrl(lightbox, 'video')} controls autoPlay playsInline
                className="max-h-[82vh] max-w-[95vw]" onClick={e => e.stopPropagation()} />
            ) : (
              <img src={mediaUrl(lightbox, 'thumbnail', 'large')} className="max-h-[82vh] max-w-[95vw] object-contain"
                onClick={e => e.stopPropagation()} />
            )}
          </div>
          <div className="shrink-0 w-full max-w-3xl px-4 pb-6 text-center space-y-3" onClick={e => e.stopPropagation()}>
            <DetailRow it={lightbox} />
            {meta.allow_download && <div className="flex justify-center"><DownloadBtn it={lightbox} big /></div>}
          </div>
        </div>
      )}
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-white p-4">{children}</div>
}

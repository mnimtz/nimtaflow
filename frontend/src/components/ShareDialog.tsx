import { useState } from 'react'
import { X, Copy, Check, Link as LinkIcon, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { useT } from '../i18n'

export type ShareTarget =
  | { kind: 'album'; albumId: number; title?: string }
  | { kind: 'photo'; photoId: number; title?: string }
  | { kind: 'trip'; tripFrom: string; tripTo: string; title?: string }
  | { kind: 'highlight'; highlightId: number; title?: string }
  | { kind: 'postcard'; photoId: number; params?: Record<string, unknown>; title?: string }

/** Create a public share link for an album, photo or trip — with optional
 *  password, expiry and download toggle. Shows the resulting link to copy. */
export default function ShareDialog({ target, onClose }: { target: ShareTarget; onClose: () => void }) {
  const { t } = useT()
  const [usePassword, setUsePassword] = useState(false)
  const [password, setPassword] = useState('')
  const [useExpiry, setUseExpiry] = useState(false)
  const [expiresDays, setExpiresDays] = useState(7)
  const [allowDownload, setAllowDownload] = useState(true)
  const [creating, setCreating] = useState(false)
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const label = target.kind === 'album' ? t('share.dlg.labelAlbum') : target.kind === 'photo' ? t('share.dlg.labelPhoto') : target.kind === 'highlight' ? t('share.dlg.labelHighlight') : target.kind === 'postcard' ? t('share.dlg.labelPostcard') : t('share.dlg.labelTrip')

  async function create() {
    setCreating(true); setError(null)
    try {
      const body: Record<string, unknown> = {
        share_type: target.kind,
        title: target.title,
        allow_download: allowDownload,
        password: usePassword && password ? password : undefined,
        expires_days: useExpiry ? expiresDays : undefined,
      }
      if (target.kind === 'album') body.album_id = target.albumId
      if (target.kind === 'photo') body.photo_id = target.photoId
      if (target.kind === 'trip') { body.trip_from = target.tripFrom; body.trip_to = target.tripTo }
      if (target.kind === 'highlight') body.highlight_id = target.highlightId
      if (target.kind === 'postcard') { body.photo_id = target.photoId; body.params = target.params }
      const res = await api.post('/shares', body)
      setUrl(res.data.url as string)
    } catch {
      setError(t('share.dlg.createFailed'))
    } finally { setCreating(false) }
  }

  function copy() {
    if (!url) return
    navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="fixed inset-0 z-[100050] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white dark:bg-zinc-900 p-5 shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2"><LinkIcon size={18} /> {t('share.dlg.shareTitle', { label })}</h3>
          <button onClick={onClose} className="p-1 text-zinc-400 hover:text-zinc-200"><X size={20} /></button>
        </div>

        {!url ? (
          <div className="space-y-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={usePassword} onChange={e => setUsePassword(e.target.checked)} />
              {t('share.dlg.usePassword')}
            </label>
            {usePassword && (
              <input type="text" value={password} onChange={e => setPassword(e.target.value)}
                placeholder={t('share.dlg.password')} className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm" />
            )}
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={useExpiry} onChange={e => setUseExpiry(e.target.checked)} />
              {t('share.dlg.expiresAfter')}
            </label>
            {useExpiry && (
              <select value={expiresDays} onChange={e => setExpiresDays(Number(e.target.value))}
                className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-3 py-2 text-sm">
                <option value={1}>{t('share.dlg.day1')}</option>
                <option value={7}>{t('share.dlg.days7')}</option>
                <option value={30}>{t('share.dlg.days30')}</option>
                <option value={90}>{t('share.dlg.days90')}</option>
              </select>
            )}
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={allowDownload} onChange={e => setAllowDownload(e.target.checked)} />
              {t('share.dlg.allowDownload')}
            </label>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <button onClick={create} disabled={creating}
              className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white py-2.5 text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-60">
              {creating ? <Loader2 size={16} className="animate-spin" /> : <LinkIcon size={16} />} {t('share.dlg.createLink')}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-zinc-400">{t('share.dlg.createdInfo', { label, pwSuffix: usePassword ? t('share.dlg.pwSuffix') : '' })}</p>
            <div className="flex items-center gap-2 rounded-lg border border-zinc-300 dark:border-zinc-700 px-3 py-2">
              <span className="text-sm truncate flex-1">{url}</span>
              <button onClick={copy} className="p-1.5 text-zinc-500 hover:text-indigo-500 shrink-0">
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
            <button onClick={onClose} className="w-full rounded-lg bg-zinc-200 dark:bg-zinc-800 py-2.5 text-sm font-medium">{t('share.dlg.done')}</button>
          </div>
        )}
      </div>
    </div>
  )
}

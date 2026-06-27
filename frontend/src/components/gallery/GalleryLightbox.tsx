import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import Lightbox from 'yet-another-react-lightbox'
import 'yet-another-react-lightbox/styles.css'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import Fullscreen from 'yet-another-react-lightbox/plugins/fullscreen'
import Slideshow from 'yet-another-react-lightbox/plugins/slideshow'
import Thumbnails from 'yet-another-react-lightbox/plugins/thumbnails'
import 'yet-another-react-lightbox/plugins/thumbnails.css'
import Counter from 'yet-another-react-lightbox/plugins/counter'
import 'yet-another-react-lightbox/plugins/counter.css'
import Captions from 'yet-another-react-lightbox/plugins/captions'
import 'yet-another-react-lightbox/plugins/captions.css'
import Video from 'yet-another-react-lightbox/plugins/video'
import Download from 'yet-another-react-lightbox/plugins/download'
import { MapContainer, TileLayer, CircleMarker } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Info, Heart, Camera, MapPin, Calendar, Aperture, Users as UsersIcon, Tag as TagIcon, Star, RefreshCw, Sparkles, Share2, Image as ImgIcon } from 'lucide-react'
import ShareDialog from '../ShareDialog'
import { api, thumbUrl, type Photo } from '../../lib/api'
import { useToast } from '../ui/dialogs'
import { useT } from '../../i18n'

function fmtBytes(b?: number) { if (!b) return null; const u = ['B', 'KB', 'MB', 'GB']; let i = 0, n = b; while (n >= 1024 && i < 3) { n /= 1024; i++ } return `${n.toFixed(1)} ${u[i]}` }

function fmtDur(s?: number) { if (!s) return null; const m = Math.floor(s / 60), sec = Math.round(s % 60); return `${m}:${String(sec).padStart(2, '0')} min` }
function fmtDate(v?: string) { return v ? new Date(v).toLocaleString('de', { dateStyle: 'medium', timeStyle: 'short' }) : null }

// Creative scene presets for "animate this photo / put the person into a world".
// labelKey/promptKey are resolved via i18n at render time.
const ANIM_PRESETS: { labelKey: string; promptKey: string | null }[] = [
  { labelKey: 'gallery.animSubtle', promptKey: null },
  { labelKey: 'gallery.animUnderwater', promptKey: 'gallery.animUnderwaterPrompt' },
  { labelKey: 'gallery.animSpace', promptKey: 'gallery.animSpacePrompt' },
  { labelKey: 'gallery.animWinter', promptKey: 'gallery.animWinterPrompt' },
  { labelKey: 'gallery.animFairy', promptKey: 'gallery.animFairyPrompt' },
  { labelKey: 'gallery.animClouds', promptKey: 'gallery.animCloudsPrompt' },
  { labelKey: 'gallery.animCyberpunk', promptKey: 'gallery.animCyberpunkPrompt' },
]

function InfoPanel({ photoId, onClose }: { photoId: number; onClose: () => void }) {
  // staleTime:0 + refetchOnMount so a photo opened before AI finished shows its
  // description/tags/faces once reopened (was caching the empty first response).
  const { data: p } = useQuery<any>({
    queryKey: ['photo-detail', photoId],
    queryFn: () => api.get(`/photos/${photoId}`).then(r => r.data),
    staleTime: 0, refetchOnMount: 'always',
  })
  const { t } = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: settings } = useQuery<Record<string, string>>({
    queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000,
  })
  // Default the Ask-the-photo provider to whatever is actually set up: if a Gemini
  // key is configured (or Gemini is the chosen AI provider) default to Cloud,
  // otherwise Local. In-process local needs a GPU the backend doesn't have, so on
  // most setups Cloud is the one that actually answers.
  const cloudConfigured = !!(settings && (settings['ai.gemini.api_key'] || settings['chat.gemini.api_key'] || settings['ai.provider'] === 'gemini' || settings['chat.provider'] === 'gemini'))
  const [scanning, setScanning] = useState(false)
  const [askQ, setAskQ] = useState('')
  const [askAnswer, setAskAnswer] = useState('')
  const [askBusy, setAskBusy] = useState(false)
  const [askProvider, setAskProvider] = useState<'local' | 'gemini'>('local')
  const [askTouched, setAskTouched] = useState(false)
  useEffect(() => {
    if (!askTouched && settings) setAskProvider(cloudConfigured ? 'gemini' : 'local')
  }, [settings, cloudConfigured, askTouched])
  const ask = async () => {
    if (!askQ.trim()) return
    setAskBusy(true); setAskAnswer('')
    try {
      const r = await api.post(`/photos/${photoId}/ask`, { question: askQ, provider: askProvider })
      setAskAnswer(r.data?.answer || (r.data?.error ? `(${r.data.error})` : 'Keine Antwort.'))
    } catch { setAskAnswer('Fehler bei der Anfrage.') } finally { setAskBusy(false) }
  }
  const reprocess = async () => {
    setScanning(true)
    try {
      await api.post(`/photos/${photoId}/reprocess`)
      toast(t('gallery.reprocessStarted'), 'success')
      // poll the detail for ~30s so the fresh description/faces/tags show up live
      let n = 0
      const iv = setInterval(() => {
        qc.invalidateQueries({ queryKey: ['photo-detail', photoId] })
        if (++n >= 10) { clearInterval(iv); setScanning(false) }
      }, 3000)
    } catch {
      toast(t('gallery.reprocessFailed'), 'error'); setScanning(false)
    }
  }
  const setCover = async (pp: any) => {
    try {
      await api.post(`/people/${pp.person_id}/profile-face/${pp.face_id}`)
      toast(t('gallery.coverSet', { name: pp.name }), 'success')
    } catch {
      toast(t('gallery.coverFailed'), 'error')
    }
  }
  if (!p) return null
  const Row = ({ icon: Icon, label, children }: any) => (
    <div className="flex items-start gap-2 text-sm text-zinc-200">
      {Icon ? <Icon size={15} className="mt-0.5 text-zinc-400 shrink-0" /> : <span className="w-[15px] shrink-0" />}
      <div className="min-w-0">{label && <div className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</div>}{children}</div>
    </div>
  )
  const taken = p.taken_at ? new Date(p.taken_at).toLocaleString('de', { dateStyle: 'full', timeStyle: 'short' }) : null
  const mp = p.width && p.height ? (p.width * p.height / 1e6).toFixed(1) : null
  // tags come back as an array (p.tags); fall back to a keywords string
  const tags: string[] = Array.isArray(p.tags) ? p.tags
    : (p.keywords ? String(p.keywords).split(',').map((k: string) => k.trim()).filter(Boolean) : [])
  const people: any[] = Array.isArray(p.people) ? p.people : []
  const namedPeople = people.filter(pp => pp.name)
  const exposure = [
    p.focal_length && `${Math.round(p.focal_length)} mm`,
    p.focal_length_35mm && `(KB ${p.focal_length_35mm} mm)`,
    p.aperture && `ƒ/${p.aperture}`,
    p.shutter_speed && `${p.shutter_speed}s`,
    p.iso && `ISO ${p.iso}`,
    p.exposure_compensation != null && p.exposure_compensation !== 0 && `${p.exposure_compensation > 0 ? '+' : ''}${p.exposure_compensation} EV`,
  ].filter(Boolean)
  return (
    <div className="fixed z-[100000] bg-zinc-900/95 backdrop-blur border-zinc-700 text-white overflow-y-auto
      inset-x-0 bottom-0 max-h-[60vh] border-t rounded-t-2xl
      md:inset-y-0 md:right-0 md:left-auto md:w-[360px] md:max-h-none md:border-l md:border-t-0 md:rounded-none">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 sticky top-0 bg-zinc-900/95">
        <h3 className="font-semibold">{t('gallery.info')}</h3>
        <button onClick={onClose} className="text-zinc-400 hover:text-white text-sm">{t('gallery.close')}</button>
      </div>
      <div className="p-4 space-y-4">
        <p className="text-sm font-medium text-zinc-100 break-all">{p.filename}</p>

        <a href={p.is_video ? `/api/photos/${p.id}/video/stream` : `/api/photos/${p.id}/original`}
           target="_blank" rel="noopener noreferrer"
           className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium">
          {p.is_video ? t('gallery.openOriginalVideo') : t('gallery.openOriginalFull')}
        </a>

        <button onClick={reprocess} disabled={scanning}
          className="ml-2 inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-white font-medium disabled:opacity-60"
          title={t('gallery.reprocessTitle')}>
          <RefreshCw size={13} className={scanning ? 'animate-spin' : ''} /> {scanning ? t('gallery.scanning') : t('gallery.reprocess')}
        </button>

        {!p.is_video && (
          <div className="mt-3 rounded-lg border border-zinc-700 p-2.5">
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">💬 {t('gallery.askTitle')}</div>
            <div className="flex gap-1.5">
              <input value={askQ} onChange={e => setAskQ(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') ask() }}
                placeholder={t('gallery.askPlaceholder')}
                className="flex-1 px-2 py-1.5 text-sm rounded bg-zinc-800 border border-zinc-700 text-white focus:outline-none focus:ring-1 focus:ring-indigo-500" />
              <button onClick={ask} disabled={askBusy || !askQ.trim()}
                className="px-3 py-1.5 text-sm rounded bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50">
                {askBusy ? '…' : t('gallery.askBtn')}
              </button>
            </div>
            <div className="flex items-center gap-3 mt-1.5 text-[11px] text-zinc-400">
              <label className="flex items-center gap-1 cursor-pointer"><input type="radio" checked={askProvider === 'local'} onChange={() => { setAskTouched(true); setAskProvider('local') }} /> {t('gallery.askLocal')}</label>
              <label className="flex items-center gap-1 cursor-pointer"><input type="radio" checked={askProvider === 'gemini'} onChange={() => { setAskTouched(true); setAskProvider('gemini') }} /> {t('gallery.askCloud')}</label>
            </div>
            {askAnswer && <div className="mt-2 text-sm text-zinc-100 whitespace-pre-wrap bg-zinc-800/60 rounded p-2">{askAnswer}</div>}
          </div>
        )}

        {p.description && (
          <div>
            <p className="text-sm text-zinc-300 italic">{p.description}</p>
            {p.description_model && <p className="text-[11px] text-zinc-500 mt-1">{t('gallery.ai')}: {p.description_model}</p>}
          </div>
        )}

        {taken && <Row icon={Calendar} label={t('gallery.takenAt')}>{taken}</Row>}

        {(p.camera_make || p.camera_model) && (
          <Row icon={Camera} label={t('gallery.camera')}>
            {[p.camera_make, p.camera_model].filter(Boolean).join(' ')}
            {p.lens_model && <div className="text-xs text-zinc-400">{p.lens_model}</div>}
          </Row>
        )}

        {exposure.length > 0 && (
          <Row icon={Aperture} label={t('gallery.exposure')}>
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-zinc-300">{exposure.map((e, i) => <span key={i}>{e}</span>)}</div>
          </Row>
        )}

        {(p.width && p.height) && (
          <Row icon={Info} label={p.is_video ? t('gallery.video') : t('gallery.image')}>
            {p.width} × {p.height}{mp ? ` · ${mp} MP` : ''}
            <div className="text-xs text-zinc-400 flex flex-wrap gap-x-3">
              {fmtBytes(p.file_size) && <span>{fmtBytes(p.file_size)}</span>}
              {p.mime_type && <span>{p.mime_type}</span>}
              {p.is_video && fmtDur(p.duration_seconds) && <span>{fmtDur(p.duration_seconds)}</span>}
              {p.is_video && p.video_codec && <span>{p.video_codec}</span>}
              {p.is_video && p.video_fps && <span>{Math.round(p.video_fps)} fps</span>}
              {p.is_video && p.video_bitrate && <span>{(p.video_bitrate / 1e6).toFixed(1)} Mbit/s</span>}
            </div>
          </Row>
        )}

        {namedPeople.length > 0 && (
          <Row icon={UsersIcon} label={t('gallery.people')}>
            <div className="flex flex-wrap gap-1.5">
              {namedPeople.map(pp => (
                <span key={pp.face_id} className="group flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-indigo-600/30 text-indigo-200 text-xs">
                  {pp.name}
                  {pp.person_id && pp.face_id && (
                    <button onClick={() => setCover(pp)} title={t('gallery.setCoverFor', { name: pp.name })}
                      className="text-indigo-300/70 hover:text-yellow-300 p-0.5"><Star size={11} /></button>
                  )}
                </span>
              ))}
            </div>
          </Row>
        )}

        {(p.city || p.country || p.location_name) && <Row icon={MapPin} label={t('gallery.location')}>{[p.location_name, p.city, p.country].filter(Boolean).join(', ')}</Row>}

        {p.latitude != null && p.longitude != null && (
          <div className="space-y-1.5">
            <div className="rounded-xl overflow-hidden border border-zinc-800 h-40">
              <MapContainer center={[p.latitude, p.longitude]} zoom={13} className="h-full w-full" zoomControl={false} dragging={false} scrollWheelZoom={false}>
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" attribution="&copy; CARTO &copy; OpenStreetMap contributors" />
                <CircleMarker center={[p.latitude, p.longitude]} radius={7} pathOptions={{ color: '#6366f1', fillColor: '#818cf8', fillOpacity: 0.9 }} />
              </MapContainer>
            </div>
            <p className="text-[11px] text-zinc-500">{p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}{p.altitude != null ? ` · ${Math.round(p.altitude)} m` : ''}</p>
          </div>
        )}

        {tags.length > 0 && (
          <Row icon={TagIcon} label={t('gallery.tags')}>
            <div className="flex flex-wrap gap-1.5">
              {tags.slice(0, 30).map((k) => <span key={k} className="px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-300 text-xs">{k}</span>)}
            </div>
          </Row>
        )}

        {(p.user_rating || p.is_favorite) && (
          <Row icon={Heart} label={t('gallery.rating')}>
            {p.user_rating ? '★'.repeat(p.user_rating) + '☆'.repeat(5 - p.user_rating) : ''}{p.is_favorite ? `  ❤️ ${t('gallery.favoriteBadge')}` : ''}
          </Row>
        )}

        <div className="pt-2 border-t border-zinc-800 space-y-1 text-[11px] text-zinc-500">
          <div className="break-all">{p.path}</div>
          {fmtDate(p.indexed_at) && <div>{t('gallery.indexed')}: {fmtDate(p.indexed_at)}</div>}
          {fmtDate(p.processed_at) && <div>{t('gallery.processed')}: {fmtDate(p.processed_at)}</div>}
          {p.ai_error && <div className="text-amber-400">{t('gallery.aiError')}</div>}
        </div>
      </div>
    </div>
  )
}

const POSTCARD_THEMES = [
  { key: 'warm', labelKey: 'gallery.pcThemeWarm' },
  { key: 'gold', labelKey: 'gallery.pcThemeGold' },
  { key: 'dark', labelKey: 'gallery.pcThemeDark' },
  { key: 'film', labelKey: 'gallery.pcThemeFilm' },
]

function PostcardDialog({ photoId, onClose }: { photoId: number; onClose: () => void }) {
  const { t, lang } = useT()
  const toast = useToast()
  const { data: p } = useQuery<any>({
    queryKey: ['photo-detail', photoId],
    queryFn: () => api.get(`/photos/${photoId}`).then(r => r.data),
    staleTime: 60_000,
  })
  const place = p ? ([p.city, p.country].filter(Boolean).join(', ') || p.location_name || '') : ''
  const defaultGreet = lang === 'en'
    ? (place ? `Greetings from ${place}` : 'Warm wishes')
    : (place ? `Grüße aus ${place}` : 'Liebe Grüße')
  const [greet, setGreet] = useState('')
  const [msg, setMsg] = useState('')
  const [theme, setTheme] = useState('warm')
  const [touched, setTouched] = useState(false)
  // Prefill the greeting from the place once the detail loads (unless the user typed).
  useEffect(() => { if (!touched && p) setGreet(defaultGreet) }, [p, defaultGreet, touched])
  // Debounce text → preview URL so typing doesn't fire a request per keystroke.
  const [deb, setDeb] = useState({ g: '', m: '' })
  useEffect(() => { const id = setTimeout(() => setDeb({ g: greet, m: msg }), 350); return () => clearTimeout(id) }, [greet, msg])
  const [busy, setBusy] = useState(false)

  const qs = `lang=${lang}&theme=${theme}&text=${encodeURIComponent(deb.g)}&subtitle=${encodeURIComponent(deb.m)}`
  const apiPath = `/photos/${photoId}/postcard?${qs}`
  const imgSrc = `/api${apiPath}`

  const fetchBlob = async () => (await api.get(apiPath, { responseType: 'blob' })).data as Blob
  const download = async () => {
    setBusy(true)
    try {
      const blob = await fetchBlob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = 'nimtaflow-postkarte.png'; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 30_000)
    } catch { toast(t('gallery.postcardFailed'), 'error') } finally { setBusy(false) }
  }
  const share = async () => {
    setBusy(true)
    try {
      const blob = await fetchBlob()
      const file = new File([blob], 'nimtaflow-postkarte.png', { type: 'image/png' })
      const nav: any = navigator
      if (nav.canShare && nav.canShare({ files: [file] })) {
        await nav.share({ files: [file], title: 'NimtaFlow', text: greet || defaultGreet })
      } else {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url; a.download = 'nimtaflow-postkarte.png'; a.click()
        setTimeout(() => URL.revokeObjectURL(url), 30_000)
        toast(t('gallery.pcShareFallback'), 'info')
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') toast(t('gallery.postcardFailed'), 'error')
    } finally { setBusy(false) }
  }

  const inp = 'w-full px-3 py-2 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500'
  return (
    <div className="fixed inset-0 z-[100001] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 rounded-2xl w-full max-w-2xl border border-zinc-200 dark:border-zinc-800 max-h-[92vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 sticky top-0 bg-white/95 dark:bg-zinc-900/95 backdrop-blur">
          <h3 className="font-semibold text-zinc-900 dark:text-white flex items-center gap-2">🖼️ {t('gallery.postcard')}</h3>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-900 dark:hover:text-white text-sm">{t('gallery.close')}</button>
        </div>
        <div className="p-4 space-y-3">
          <div className="rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-800 bg-zinc-100 dark:bg-zinc-950">
            <img src={imgSrc} alt="Postkarte" className="block w-full" />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">{t('gallery.pcGreeting')}</label>
            <input value={greet} onChange={e => { setTouched(true); setGreet(e.target.value) }} placeholder={defaultGreet} className={inp} maxLength={60} />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">{t('gallery.pcMessage')}</label>
            <input value={msg} onChange={e => setMsg(e.target.value)} placeholder={t('gallery.pcMessagePh')} className={inp} maxLength={80} />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">{t('gallery.pcTheme')}</label>
            <div className="flex flex-wrap gap-1.5">
              {POSTCARD_THEMES.map(th => (
                <button key={th.key} type="button" onClick={() => setTheme(th.key)}
                  className={`px-3 py-1.5 rounded-lg text-sm border ${theme === th.key ? 'bg-indigo-600 text-white border-indigo-600' : 'border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:border-indigo-400'}`}>
                  {t(th.labelKey)}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 pt-1">
            <button onClick={download} disabled={busy} className="px-4 py-2 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50">⬇ {t('gallery.pcDownload')}</button>
            <button onClick={share} disabled={busy} className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-500 disabled:opacity-50 inline-flex items-center gap-1.5"><Share2 size={15} /> {t('gallery.shareTooltip')}</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function GalleryLightbox({ photos, index, onClose, onFavorite, hasMore, onLoadMore }: {
  photos: Photo[]; index: number; onClose: () => void; onFavorite?: (photo: Photo) => void
  hasMore?: boolean; onLoadMore?: () => void
}) {
  const { t } = useT()
  const [cur, setCur] = useState(index)
  const [info, setInfo] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [postcardOpen, setPostcardOpen] = useState(false)
  // Track favorite state locally so the heart updates immediately (the `photos`
  // array is a snapshot frozen when the lightbox opened).
  const [favs, setFavs] = useState<Set<number>>(() => new Set(photos.filter(p => p.is_favorite).map(p => p.id)))
  const toggleFav = (p: Photo) => {
    onFavorite?.(p)
    setFavs(s => { const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n })
  }
  const isFav = (p?: Photo) => !!p && favs.has(p.id)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'i') { setInfo(v => !v) }
      if (e.key === 'f' && photos[cur]) toggleFav(photos[cur])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cur, photos, onFavorite])

  // Fall back to generous dimensions when EXIF width/height are missing —
  // otherwise yet-another-react-lightbox renders the image at its tiny natural
  // (thumbnail) size instead of scaling it to fill the viewport.
  const slides = photos.map(p => p.is_video
    ? { type: 'video' as const, poster: thumbUrl(p, 'large'), width: p.width || 1280, height: p.height || 720, sources: [{ src: `/api/photos/${p.id}/video/stream`, type: 'video/mp4' }], description: p.filename }
    : { src: thumbUrl(p, 'large'), width: p.width || 1600, height: p.height || 1200, description: p.filename, download: { url: `/api/photos/${p.id}/original`, filename: p.filename } })

  // External video-AI ("animate this photo") — only when opted in (Settings → Highlights).
  const toast = useToast()
  const { data: settings } = useQuery<Record<string, string>>({
    queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000,
  })
  const aiOn = (settings?.['highlights.ai_enabled'] ?? 'false') === 'true'
  const [animOpen, setAnimOpen] = useState(false)
  const [animPrompt, setAnimPrompt] = useState('')
  const animate = useMutation({
    mutationFn: ({ id, prompt }: { id: number; prompt: string }) =>
      api.post('/highlights/animate-photo', { photo_id: id, prompt: prompt.trim() || undefined }).then(r => r.data),
    onSuccess: () => { setAnimOpen(false); setAnimPrompt(''); toast(t('gallery.animStarted'), 'success') },
    onError: (e: any) => toast(e?.response?.data?.detail || t('gallery.animFailed'), 'error'),
  })
  const animBtn = (aiOn && photos[cur] && !photos[cur].is_video) ? (
    <button key="animate" type="button" className="yarl__button"
      onClick={() => setAnimOpen(true)} title={t('gallery.animateTooltip')}>
      <Sparkles className="yarl__icon" />
    </button>
  ) : null

  const infoBtn = (
    <button key="info" type="button" className="yarl__button" onClick={() => setInfo(v => !v)} title={t('gallery.infoTooltip')}>
      <Info className="yarl__icon" />
    </button>
  )
  const shareBtn = (
    <button key="share" type="button" className="yarl__button" onClick={() => setShareOpen(true)} title={t('gallery.shareTooltip')}>
      <Share2 className="yarl__icon" />
    </button>
  )
  const postcardBtn = (photos[cur] && !photos[cur].is_video) ? (
    <button key="postcard" type="button" className="yarl__button" onClick={() => setPostcardOpen(true)} title={t('gallery.postcardTooltip')}>
      <ImgIcon className="yarl__icon" />
    </button>
  ) : null
  const favBtn = onFavorite ? (
    <button key="fav" type="button" className="yarl__button" onClick={() => photos[cur] && toggleFav(photos[cur])} title={t('gallery.favoriteTooltip')}>
      <Heart className="yarl__icon" fill={isFav(photos[cur]) ? 'currentColor' : 'none'} color={isFav(photos[cur]) ? '#f87171' : undefined} />
    </button>
  ) : null

  return (
    <>
      <Lightbox
        open index={cur} close={onClose} slides={slides as any}
        on={{ view: ({ index: i }) => {
          setCur(i)
          // Pull the next page as the user nears the end of what's loaded, so
          // browsing covers the whole library instead of looping a few photos.
          if (onLoadMore && hasMore && i >= photos.length - 3) onLoadMore()
        } }}
        plugins={[Zoom, Fullscreen, Slideshow, Thumbnails, Counter, Captions, Video, Download]}
        toolbar={{ buttons: [animBtn, postcardBtn, shareBtn, favBtn, infoBtn, 'download', 'slideshow', 'fullscreen', 'close'].filter(Boolean) as any }}
        zoom={{ maxZoomPixelRatio: 4, scrollToZoom: true }}
        thumbnails={{ position: 'bottom', width: 96, height: 64, border: 0, gap: 6 }}
        counter={{ container: { style: { top: 'unset', bottom: 0 } } }}
        captions={{ descriptionTextAlign: 'center' }}
        carousel={{ finite: true, preload: 3 }}
        styles={{ container: { backgroundColor: 'rgba(0,0,0,0.94)' } }}
        animation={{ fade: 250, swipe: 300 }}
      />
      {info && photos[cur] && createPortal(<InfoPanel photoId={photos[cur].id} onClose={() => setInfo(false)} />, document.body)}
      {shareOpen && photos[cur] && createPortal(<ShareDialog target={{ kind: 'photo', photoId: photos[cur].id, title: photos[cur].filename }} onClose={() => setShareOpen(false)} />, document.body)}
      {postcardOpen && photos[cur] && createPortal(<PostcardDialog photoId={photos[cur].id} onClose={() => setPostcardOpen(false)} />, document.body)}
      {animOpen && photos[cur] && createPortal(
        <div className="fixed inset-0 z-[11000] flex items-center justify-center bg-black/70 p-4" onClick={() => setAnimOpen(false)}>
          <div className="bg-white dark:bg-zinc-900 rounded-2xl p-5 w-full max-w-lg border border-zinc-200 dark:border-zinc-800 space-y-3" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2">
              <Sparkles size={18} className="text-indigo-500" />
              <h2 className="text-lg font-bold text-zinc-900 dark:text-white">{t('gallery.animDialogTitle')}</h2>
            </div>
            <p className="text-xs text-zinc-500">{t('gallery.animDialogHint')}</p>
            <div className="flex flex-wrap gap-1.5">
              {ANIM_PRESETS.map(p => (
                <button key={p.labelKey} onClick={() => setAnimPrompt(p.promptKey ? t(p.promptKey) : '')}
                  className="px-2.5 py-1 rounded-full text-xs border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 hover:border-indigo-400">
                  {t(p.labelKey)}
                </button>
              ))}
            </div>
            <textarea value={animPrompt} onChange={e => setAnimPrompt(e.target.value)} rows={3}
              placeholder={t('gallery.animPromptPlaceholder')}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <p className="text-[11px] text-zinc-400">{t('gallery.animNote')}</p>
            <div className="flex items-center justify-end gap-2">
              <button onClick={() => setAnimOpen(false)} className="px-3 py-1.5 text-sm rounded-lg text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('gallery.cancel')}</button>
              <button onClick={() => photos[cur] && animate.mutate({ id: photos[cur].id, prompt: animPrompt })} disabled={animate.isPending}
                className="px-4 py-1.5 text-sm rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-500 disabled:opacity-50">
                {animate.isPending ? t('gallery.starting') : t('gallery.animate')}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

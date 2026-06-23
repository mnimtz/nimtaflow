import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Trash2, RefreshCw, Check, X, FolderOpen,
  Cpu, Layers, Cog, Map, HardDrive, Video, Terminal,
  Loader2, CircleCheck, CircleX,
  Eye, Zap, Brain, Download, Shield, Lock, KeyRound, Network, Clock,
  MessageCircle, Image as ImageIcon, Plane, Share2, Copy, Sparkles,
} from 'lucide-react'
import { api, type Source } from '../lib/api'
import FolderBrowser from '../components/ui/FolderBrowser'
import { useT } from '../i18n'

// ─── Types ──────────────────────────────────────────────────────────────────

type ModelInfo = {
  id: string
  name: string
  description?: string
  supports_vision: boolean
  supports_embedding: boolean
}

type Settings = Record<string, string>

const DEFAULT_IMAGE_PROMPT = 'Beschreibe dieses Foto sachlich in 2-3 Sätzen auf Deutsch. Nenne Personen, Ort, Aktivität und Stimmung.'
const DEFAULT_VIDEO_PROMPT = 'Beschreibe diese Videoszene sachlich in 2-3 Sätzen auf Deutsch. Nenne Personen, Ort, Aktivität und Stimmung.'
const DEFAULT_TAGS_PROMPT = 'Nenne 5–12 prägnante Schlagwörter (Substantive) zu diesem Bild, kommagetrennt, ohne Sätze, ohne Füllwörter. Beispiel: Strand, Sonnenuntergang, Boot, Meer.'

// ─── Layout helpers ──────────────────────────────────────────────────────────

const SECTIONS = [
  { id: 'sources',   icon: HardDrive, navKey: 'nav.sources' },
  { id: 'gallery',   icon: Layers,    navKey: 'nav.gallery' },
  { id: 'features',  icon: Network,   navKey: 'nav.features' },
  { id: 'ai',        icon: Brain,     navKey: 'nav.ai' },
  { id: 'chat',      icon: MessageCircle, navKey: 'nav.chat' },
  { id: 'video-ai',  icon: Video,     navKey: 'nav.videoAi' },
  { id: 'faces',     icon: Eye,       navKey: 'nav.faces' },
  { id: 'memories',  icon: Clock,     navKey: 'nav.memories' },
  { id: 'highlights', icon: Sparkles, navKey: 'nav.highlights' },
  { id: 'trips',     icon: Plane,     navKey: 'nav.trips' },
  { id: 'sharing',   icon: Share2,    navKey: 'nav.sharing' },
  { id: 'pipeline',  icon: Cog,       navKey: 'nav.pipeline' },
  { id: 'remote',    icon: Network,   navKey: 'nav.remote' },
  { id: 'backup',    icon: HardDrive, navKey: 'nav.backup' },
  { id: 'map',       icon: Map,       navKey: 'nav.map' },
  { id: 'users',     icon: Shield,    navKey: 'nav.users' },
  { id: 'logs',      icon: Terminal,  navKey: 'nav.logs' },
] as const

type SectionId = typeof SECTIONS[number]['id']

function SectionHeader({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">{title}</h2>
      <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">{desc}</p>
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">{children}</label>
}

function Input({ value, onChange, type = 'text', placeholder = '' }: {
  value: string; onChange: (v: string) => void; type?: string; placeholder?: string
}) {
  return (
    <input
      type={type} value={value} placeholder={placeholder}
      onChange={e => onChange(e.target.value)}
      className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-shadow"
    />
  )
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`toggle-root ${value ? 'bg-indigo-500' : 'bg-zinc-300 dark:bg-zinc-700'}`}
    >
      <div className={`toggle-thumb ${value ? 'translate-x-[18px]' : ''}`} />
    </button>
  )
}

function SaveButton({ pending, saved, onClick }: { pending: boolean; saved: boolean; onClick: () => void }) {
  const { t } = useT()
  return (
    <button
      onClick={onClick}
      disabled={pending}
      className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
    >
      {pending ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : null}
      {saved ? t('settings.saved') : t('settings.save')}
    </button>
  )
}

// ─── Model Select ─────────────────────────────────────────────────────────────

function ModelSelect({
  label, value, onChange, models, loading, filter,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  models: ModelInfo[]
  loading: boolean
  filter?: (m: ModelInfo) => boolean
  placeholder?: string
}) {
  const { t } = useT()
  const filtered = filter ? models.filter(filter) : models
  const ph = placeholder ?? t('settings.modelEnterOrPick')
  return (
    <div>
      <Label>{label}</Label>
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-400 py-2">
          <Loader2 size={13} className="animate-spin" /> {t('settings.loadingModels')}
        </div>
      ) : filtered.length > 0 ? (
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">{t('settings.optChoose')}</option>
          {filtered.map(m => (
            <option key={m.id} value={m.id}>
              {m.name}{m.description ? ` (${m.description})` : ''}
            </option>
          ))}
        </select>
      ) : (
        <Input value={value} onChange={onChange} placeholder={ph} />
      )}
    </div>
  )
}

// ─── Provider health badge ────────────────────────────────────────────────────

function HealthBadge({ provider, apiKey, baseUrl }: { provider: string; apiKey?: string; baseUrl?: string }) {
  const { t } = useT()
  const { data, isLoading, refetch } = useQuery<{ ok: boolean; error?: string }>({
    queryKey: ['ai-health', provider, baseUrl],
    queryFn: () => api.get(`/ai/health/${provider}`, { params: { api_key: apiKey, base_url: baseUrl } }).then(r => r.data),
    enabled: false,
    retry: false,
  })

  return (
    <div className="flex items-center gap-2 mt-2">
      <button
        onClick={() => refetch()}
        disabled={isLoading}
        className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1.5 transition-colors"
      >
        {isLoading ? <Loader2 size={11} className="animate-spin" /> : <Zap size={11} />}
        {t('settings.testConnection')}
      </button>
      {data && (
        data.ok
          ? <span className="flex items-center gap-1 text-xs text-emerald-400"><CircleCheck size={11} />{t('settings.reachable')}</span>
          : <span className="flex items-center gap-1 text-xs text-red-400"><CircleX size={11} />{data.error ?? t('settings.error')}</span>
      )}
    </div>
  )
}

// ─── Sections ─────────────────────────────────────────────────────────────────

function SourcesSection() {
  const { t } = useT()
  const [newPath, setNewPath] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const [scanningIds, setScanningIds] = useState<Set<number>>(new Set())
  const qc = useQueryClient()

  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ['sources'],
    queryFn: () => api.get('/sources').then(r => r.data),
    refetchInterval: 5000, // live-update scan status
  })
  // Per-folder indexed counts (images / videos / missing) so the user can sanity-check
  // each source — does the recognised count match what's in the folder?
  const { data: srcCounts = [] } = useQuery<{ id: number; images: number; videos: number; missing: number }[]>({
    queryKey: ['source-counts'],
    queryFn: () => api.get('/sources/counts').then(r => r.data),
    refetchInterval: 15000,
  })
  const countFor = (id: number) => srcCounts.find(c => c.id === id)

  const add = useMutation({
    mutationFn: (path: string) => api.post('/sources', { path }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['sources'] })
      setNewPath('')
      // Mark as scanning so UI shows spinner immediately
      setScanningIds(s => new Set(s).add(res.data.id))
      // After 30s assume scan is done and refresh
      setTimeout(() => {
        setScanningIds(s => { const n = new Set(s); n.delete(res.data.id); return n })
        qc.invalidateQueries({ queryKey: ['sources'] })
      }, 30_000)
    },
  })

  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/sources/${id}`),
    onSuccess: () => {
      // also refresh the gallery/people/stats so removed photos disappear immediately
      qc.invalidateQueries({ queryKey: ['sources'] })
      qc.invalidateQueries({ queryKey: ['photos'] })
      qc.invalidateQueries({ queryKey: ['photo-stats'] })
      qc.invalidateQueries({ queryKey: ['people'] })
      qc.invalidateQueries({ queryKey: ['memories'] })
    },
  })

  const scan = useMutation({
    mutationFn: (id: number) => api.post(`/sources/${id}/scan`).then(r => ({ id, ...r.data })),
    onMutate: (id) => setScanningIds(s => new Set(s).add(id)),
    onSettled: (data) => {
      if (data?.id) setScanningIds(s => { const n = new Set(s); n.delete(data.id); return n })
      qc.invalidateQueries({ queryKey: ['sources'] })
    },
  })

  const patch = useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Partial<Source>) => api.patch(`/sources/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  })

  const reprocess = useMutation({
    mutationFn: ({ id, redoFaces }: { id: number; redoFaces: boolean }) =>
      api.post(`/sources/${id}/reprocess`, null, { params: { redo_faces: redoFaces } }).then(r => r.data),
    onSuccess: (d: { reprocessing: number }) => alert(t('settings.srcReprocessAlert', { n: d.reprocessing })),
  })

  const reprocessFailed = useMutation({
    mutationFn: () => api.post('/photos/reprocess-failed').then(r => r.data),
    onSuccess: (d: { reprocessing: number }) => alert(t('settings.srcReprocessFailedAlert', { n: d.reprocessing })),
  })

  const [verifyResult, setVerifyResult] = useState<string | null>(null)
  const verify = useMutation({
    mutationFn: () => api.post('/sources/verify').then(r => r.data),
    onSuccess: (d: { checked: number; removed_photos: number; removed_files: number }) => {
      setVerifyResult(t('settings.srcVerifyResult', { checked: d.checked, photos: d.removed_photos, files: d.removed_files }))
      qc.invalidateQueries({ queryKey: ['photos'] })
      qc.invalidateQueries({ queryKey: ['photo-stats'] })
      qc.invalidateQueries({ queryKey: ['people'] })
      qc.invalidateQueries({ queryKey: ['memories'] })
    },
  })

  const INTERVALS: { label: string; value: number }[] = [
    { label: t('settings.intervalManual'), value: 0 },
    { label: t('settings.interval15'), value: 15 },
    { label: t('settings.interval30'), value: 30 },
    { label: t('settings.intervalHourly'), value: 60 },
    { label: t('settings.interval6h'), value: 360 },
    { label: t('settings.intervalDaily'), value: 1440 },
  ]

  return (
    <div>
      <SectionHeader title={t('settings.srcTitle')} desc={t('settings.srcDesc')} />

      <div className="space-y-2 mb-5">
        {sources.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 py-2">{t('settings.srcEmpty')}</p>
        )}
        {sources.map(s => {
          const isScanning = scanningIds.has(s.id)
          const watching = s.scan_interval_minutes > 0
          return (
            <div key={s.id} className="px-4 py-3 rounded-xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700">
              <div className="flex items-center gap-3">
                <HardDrive size={15} className={`shrink-0 ${isScanning ? 'text-indigo-400 animate-pulse' : 'text-zinc-400'}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate font-mono">{s.path}</p>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    {isScanning
                      ? t('settings.srcScanning')
                      : s.last_scan_at
                        ? t('settings.srcLastScan', { date: new Date(s.last_scan_at).toLocaleString('de'), n: s.last_scan_count ?? 0 })
                        : t('settings.srcNotScanned')}
                  </p>
                  {(() => { const c = countFor(s.id); return c ? (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                      📷 {c.images.toLocaleString('de')} {t('settings.images')} · 🎬 {c.videos.toLocaleString('de')} {t('settings.videos')}
                      {c.missing > 0 && <span className="text-amber-500"> · ⚠️ {t('settings.srcMissing', { n: c.missing })}</span>}
                    </p>
                  ) : null })()}
                </div>
                <button
                  onClick={() => scan.mutate(s.id)}
                  disabled={isScanning}
                  title={t('settings.srcRescan')}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors disabled:opacity-40"
                >
                  <RefreshCw size={14} className={isScanning ? 'animate-spin' : ''} />
                </button>
                <button
                  onClick={() => { if (confirm(t('settings.srcRemoveConfirm', { path: s.path }))) del.mutate(s.id) }}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Watch / interval controls */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700/60">
                <div className="flex items-center gap-2">
                  <Eye size={13} className={watching ? 'text-indigo-500' : 'text-zinc-400'} />
                  <label className="text-xs text-zinc-500 dark:text-zinc-400">{t('settings.srcWatch')}</label>
                  <select
                    value={s.scan_interval_minutes}
                    onChange={e => patch.mutate({
                      id: s.id,
                      scan_interval_minutes: Number(e.target.value),
                      watch_enabled: Number(e.target.value) > 0,
                    })}
                    className="text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {INTERVALS.map(iv => (
                      <option key={iv.value} value={iv.value}>{iv.label}</option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={s.detect_deletions}
                    onChange={e => patch.mutate({ id: s.id, detect_deletions: e.target.checked })}
                    className="rounded accent-indigo-500"
                  />
                  {t('settings.srcDetectDeletions')}
                </label>
                <div className="flex items-center gap-2">
                  <label className="text-xs text-zinc-500 dark:text-zinc-400">{t('settings.srcAiLabel')}</label>
                  <select
                    value={s.ai_provider ?? ''}
                    onChange={e => patch.mutate({ id: s.id, ai_provider: (e.target.value || null) } as any)}
                    title={t('settings.srcAiTitle')}
                    className="text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">{t('settings.srcAiGlobal')}</option>
                    <option value="gemini">{t('settings.srcAiGemini')}</option>
                    <option value="local">{t('settings.srcAiLocal')}</option>
                    <option value="ollama">Ollama</option>
                    <option value="off">{t('settings.srcAiOff')}</option>
                  </select>
                </div>
                <button
                  onClick={() => { if (confirm(t('settings.srcReprocessConfirm'))) reprocess.mutate({ id: s.id, redoFaces: true }) }}
                  className="ml-auto text-xs text-indigo-500 hover:underline"
                >
                  {t('settings.srcReprocessBtn')}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      <form onSubmit={e => { e.preventDefault(); if (newPath) add.mutate(newPath) }} className="space-y-2">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              value={newPath}
              onChange={e => setNewPath(e.target.value)}
              placeholder={t('settings.srcPathPlaceholder')}
              className="w-full pl-3 pr-10 py-2 text-sm font-mono rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button type="button" onClick={() => setShowBrowser(true)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-zinc-400 hover:text-indigo-500 transition-colors">
              <FolderOpen size={15} />
            </button>
          </div>
          <button type="submit" disabled={!newPath || add.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors shrink-0">
            {add.isPending ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}
            {t('settings.add')}
          </button>
        </div>
        <p className="text-xs text-zinc-400">
          {t('settings.srcAddHint')}
        </p>
      </form>

      {/* Library maintenance */}
      <div className="mt-6 pt-5 border-t border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">{t('settings.srcVerifyTitle')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              {t('settings.srcVerifyDesc')}
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => reprocessFailed.mutate()}
              disabled={reprocessFailed.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-sm font-medium disabled:opacity-50 transition-colors"
              title={t('settings.srcRetryFailedTitle')}
            >
              <RefreshCw size={14} className={reprocessFailed.isPending ? 'animate-spin' : ''} /> {t('settings.srcRetryFailed')}
            </button>
            <button
              onClick={() => { if (confirm(t('settings.srcVerifyConfirm'))) { setVerifyResult(null); verify.mutate() } }}
              disabled={verify.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-sm font-medium disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={14} className={verify.isPending ? 'animate-spin' : ''} /> {t('settings.srcVerifyNow')}
            </button>
          </div>
        </div>
        {verifyResult && <p className="text-xs text-emerald-500 mt-2">✓ {verifyResult}</p>}
      </div>

      {showBrowser && (
        <FolderBrowser initialPath={newPath || '/photos'} onSelect={p => setNewPath(p)} onClose={() => setShowBrowser(false)} />
      )}
    </div>
  )
}

function GallerySection() {
  const { t } = useT()
  const [rowHeight, setRowHeight] = useState(200)
  const [autoplay, setAutoplay] = useState(true)
  const [faceBoxes, setFaceBoxes] = useState(true)
  const [defaultView, setDefaultView] = useState('grid')
  const [saved, setSaved] = useState(false)

  return (
    <div>
      <SectionHeader title={t('settings.galTitle')} desc={t('settings.galDesc')} />
      <div className="space-y-6">
        <div>
          <Label>{t('settings.galDefaultView')}</Label>
          <select value={defaultView} onChange={e => setDefaultView(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="grid">{t('settings.galViewGrid')}</option>
            <option value="timeline">{t('settings.galViewTimeline')}</option>
            <option value="memories">{t('settings.galViewMemories')}</option>
          </select>
        </div>

        <div>
          <Label>{t('settings.galRowHeight', { n: rowHeight })}</Label>
          <input type="range" min={120} max={400} step={20} value={rowHeight}
            onChange={e => setRowHeight(Number(e.target.value))} className="w-full accent-indigo-500" />
          <div className="flex justify-between text-xs text-zinc-400 mt-0.5">
            <span>{t('settings.galCompact')}</span><span>{t('settings.galLarge')}</span>
          </div>
        </div>

        <div className="space-y-4">
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.galAutoplay')}</p>
              <p className="text-xs text-zinc-400 mt-0.5">{t('settings.galAutoplayDesc')}</p>
            </div>
            <Toggle value={autoplay} onChange={setAutoplay} />
          </label>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.galFaceBoxes')}</p>
              <p className="text-xs text-zinc-400 mt-0.5">{t('settings.galFaceBoxesDesc')}</p>
            </div>
            <Toggle value={faceBoxes} onChange={setFaceBoxes} />
          </label>
        </div>

        <SaveButton pending={false} saved={saved} onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2000) }} />
      </div>
    </div>
  )
}

function AISection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()
  const provider = settings['ai.provider'] ?? 'none'

  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
  useEffect(() => {
    if (settingsQuery.data) setSettings(settingsQuery.data)
  }, [settingsQuery.data])

  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => {
      setSaved(true); setTimeout(() => setSaved(false), 2200)
      qc.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  function set(key: string, val: string) {
    setSettings(s => ({ ...s, [key]: val }))
  }

  const geminiKey = settings['ai.gemini.api_key']
  const openaiKey = settings['ai.openai.api_key']
  const ollamaUrl = settings['ai.ollama.url'] || 'http://localhost:11434'
  const openaiBase = settings['ai.openai.base_url'] || 'https://api.openai.com/v1'

  // Dynamic model lists
  const geminiModels = useQuery<ModelInfo[]>({
    queryKey: ['gemini-models', geminiKey],
    queryFn: () => api.get('/ai/models/gemini', { params: { api_key: geminiKey } }).then(r => r.data),
    enabled: !!geminiKey && geminiKey !== '***' && provider === 'gemini',
    staleTime: 300_000,
  })

  const openaiModels = useQuery<ModelInfo[]>({
    queryKey: ['openai-models', openaiKey, openaiBase],
    queryFn: () => api.get('/ai/models/openai', { params: { api_key: openaiKey, base_url: openaiBase } }).then(r => r.data),
    enabled: !!openaiKey && openaiKey !== '***' && (provider === 'openai' || provider === 'azure'),
    staleTime: 300_000,
  })

  const ollamaModels = useQuery<ModelInfo[]>({
    queryKey: ['ollama-models', ollamaUrl],
    queryFn: () => api.get('/ai/models/ollama', { params: { base_url: ollamaUrl } }).then(r => r.data),
    enabled: provider === 'ollama',
    staleTime: 60_000,
  })

  return (
    <div>
      <SectionHeader title={t('settings.aiTitle')} desc={t('settings.aiDesc')} />
      <div className="space-y-7">

        {/* Provider picker */}
        <div>
          <Label>{t('settings.aiActiveProvider')}</Label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {([
              { id: 'none', label: t('settings.aiProviderNone'), sub: t('settings.aiProviderNoneSub') },
              { id: 'gemini', label: 'Gemini', sub: 'Google' },
              { id: 'openai', label: 'OpenAI', sub: 'GPT-4o' },
              { id: 'azure', label: 'Azure', sub: 'Copilot/OAI' },
              { id: 'ollama', label: 'Ollama', sub: t('settings.aiProviderLocalSub') },
              { id: 'local', label: t('settings.aiProviderIntegrated'), sub: t('settings.aiProviderIntegratedSub') },
            ] as const).map(p => (
              <button
                key={p.id}
                onClick={() => set('ai.provider', p.id)}
                className={`px-3 py-2.5 rounded-xl text-sm font-medium border transition-all text-left ${
                  provider === p.id
                    ? 'border-indigo-500 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                    : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-400 dark:hover:border-zinc-500'
                }`}
              >
                <span className="block">{p.label}</span>
                <span className="text-[10px] text-zinc-400">{p.sub}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Gemini settings */}
        {provider === 'gemini' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Google Gemini</p>
            <div>
              <Label>{t('settings.aiApiKey')}</Label>
              <Input value={settings['ai.gemini.api_key'] ?? ''} onChange={v => set('ai.gemini.api_key', v)} type="password" placeholder="AIza..." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label={t('settings.aiVisionModel')}
                value={settings['ai.gemini.model'] ?? ''}
                onChange={v => set('ai.gemini.model', v)}
                models={geminiModels.data ?? []}
                loading={geminiModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="gemini-2.5-flash"
              />
              <ModelSelect
                label={t('settings.aiEmbedModel')}
                value={settings['ai.gemini.embed_model'] ?? ''}
                onChange={v => set('ai.gemini.embed_model', v)}
                models={geminiModels.data ?? []}
                loading={geminiModels.isLoading}
                filter={m => m.supports_embedding}
                placeholder="text-embedding-004"
              />
            </div>
            <HealthBadge provider="gemini" apiKey={settings['ai.gemini.api_key']} />
          </div>
        )}

        {/* OpenAI settings */}
        {provider === 'openai' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">OpenAI</p>
            <div>
              <Label>{t('settings.aiApiKey')}</Label>
              <Input value={settings['ai.openai.api_key'] ?? ''} onChange={v => set('ai.openai.api_key', v)} type="password" placeholder="sk-..." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label={t('settings.aiVisionModel')}
                value={settings['ai.openai.model'] ?? ''}
                onChange={v => set('ai.openai.model', v)}
                models={openaiModels.data ?? []}
                loading={openaiModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="gpt-4o"
              />
              <ModelSelect
                label={t('settings.aiEmbedModel')}
                value={settings['ai.openai.embed_model'] ?? ''}
                onChange={v => set('ai.openai.embed_model', v)}
                models={openaiModels.data ?? []}
                loading={openaiModels.isLoading}
                filter={m => m.supports_embedding}
                placeholder="text-embedding-3-small"
              />
            </div>
            <HealthBadge provider="openai" apiKey={settings['ai.openai.api_key']} />
          </div>
        )}

        {/* Azure / Copilot settings */}
        {provider === 'azure' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Azure OpenAI / Microsoft Copilot</p>
            <div>
              <Label>{t('settings.aiApiKey')}</Label>
              <Input value={settings['ai.openai.api_key'] ?? ''} onChange={v => set('ai.openai.api_key', v)} type="password" placeholder="Azure-Key..." />
            </div>
            <div>
              <Label>{t('settings.aiEndpointUrl')}</Label>
              <Input
                value={settings['ai.openai.base_url'] ?? ''}
                onChange={v => set('ai.openai.base_url', v)}
                placeholder="https://your-resource.openai.azure.com/openai/v1"
              />
              <p className="text-[11px] text-zinc-400 mt-1">{t('settings.aiAzureFormat')}</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label={t('settings.aiVisionDeployment')}
                value={settings['ai.openai.model'] ?? ''}
                onChange={v => set('ai.openai.model', v)}
                models={openaiModels.data ?? []}
                loading={openaiModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="gpt-4o"
              />
              <ModelSelect
                label={t('settings.aiEmbedDeployment')}
                value={settings['ai.openai.embed_model'] ?? ''}
                onChange={v => set('ai.openai.embed_model', v)}
                models={openaiModels.data ?? []}
                loading={openaiModels.isLoading}
                filter={m => m.supports_embedding}
                placeholder="text-embedding-3-small"
              />
            </div>
            <HealthBadge provider="azure" apiKey={settings['ai.openai.api_key']} baseUrl={settings['ai.openai.base_url']} />
          </div>
        )}

        {/* Ollama settings */}
        {provider === 'ollama' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{t('settings.aiOllamaLocal')}</p>
            <div>
              <Label>{t('settings.aiOllamaUrl')}</Label>
              <Input value={settings['ai.ollama.url'] ?? ''} onChange={v => set('ai.ollama.url', v)} placeholder="http://your-host:11434" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label={t('settings.aiVisionModel')}
                value={settings['ai.ollama.vision_model'] ?? ''}
                onChange={v => set('ai.ollama.vision_model', v)}
                models={ollamaModels.data ?? []}
                loading={ollamaModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="llava:7b oder moondream"
              />
              <ModelSelect
                label={t('settings.aiEmbedModel')}
                value={settings['ai.ollama.embed_model'] ?? ''}
                onChange={v => set('ai.ollama.embed_model', v)}
                models={ollamaModels.data ?? []}
                loading={ollamaModels.isLoading}
                filter={m => m.supports_embedding}
                placeholder="nomic-embed-text"
              />
            </div>
            {ollamaModels.data?.length === 0 && !ollamaModels.isLoading && (
              <p className="text-xs text-amber-400">{t('settings.aiOllamaNoModels')}</p>
            )}
            <HealthBadge provider="ollama" baseUrl={settings['ai.ollama.url']} />
          </div>
        )}

        {/* Integrated local model */}
        {provider === 'local' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{t('settings.aiIntegratedModel')}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {([
                { id: 'florence2-base', label: 'Optimum — Florence-2-base', sub: t('settings.aiFlorenceSub') },
                { id: 'qwen2.5-vl-3b', label: 'Best — Qwen2.5-VL-3B', sub: t('settings.aiQwenSub') },
              ] as const).map(m => (
                <button key={m.id} onClick={() => set('ai.local.model', m.id)}
                  className={`px-3 py-2.5 rounded-xl text-sm font-medium border transition-all text-left ${
                    (settings['ai.local.model'] ?? 'florence2-base') === m.id
                      ? 'border-indigo-500 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                      : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-400'
                  }`}>
                  <span className="block">{m.label}</span>
                  <span className="text-[10px] text-zinc-400">{m.sub}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-zinc-400">
              {t('settings.aiIntegratedHint')}
            </p>
          </div>
        )}

        {/* Description prompt */}
        <div>
          <Label>{t('settings.aiImagePrompt')}</Label>
          <textarea
            value={settings['ai.prompt.image'] ?? DEFAULT_IMAGE_PROMPT}
            onChange={e => set('ai.prompt.image', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          />
          <div className="flex justify-between items-center mt-1">
            <p className="text-[11px] text-zinc-400">{t('settings.aiImagePromptHint')}</p>
            <button type="button" onClick={() => set('ai.prompt.image', DEFAULT_IMAGE_PROMPT)}
              className="text-[11px] text-indigo-500 hover:underline">{t('settings.default')}</button>
          </div>
        </div>

        {/* Tags prompt (optional) */}
        <div>
          <Label>{t('settings.aiTagsPrompt')}</Label>
          <textarea
            value={settings['ai.prompt.tags'] ?? ''}
            onChange={e => set('ai.prompt.tags', e.target.value)}
            rows={2}
            placeholder={t('settings.aiTagsPlaceholder', { example: DEFAULT_TAGS_PROMPT })}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          />
          <div className="flex justify-between items-center mt-1">
            <p className="text-[11px] text-zinc-400">
              {t('settings.aiTagsPromptHintA')} <b>{t('settings.aiTagsPromptHintBold')}</b> {t('settings.aiTagsPromptHintB')}
            </p>
            <button type="button" onClick={() => set('ai.prompt.tags', DEFAULT_TAGS_PROMPT)}
              className="text-[11px] text-indigo-500 hover:underline whitespace-nowrap ml-2">{t('settings.template')}</button>
          </div>
        </div>

        {/* Language */}
        <div>
          <Label>{t('settings.aiLanguage')}</Label>
          <select value={settings['ai.language'] ?? 'de'} onChange={e => set('ai.language', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="de">{t('settings.langDe')}</option>
            <option value="en">{t('settings.langEn')}</option>
            <option value="fr">{t('settings.langFr')}</option>
            <option value="es">{t('settings.langEs')}</option>
          </select>
        </div>

        {/* Search accuracy */}
        <div>
          <Label>{t('settings.aiSearchAccuracy', { d: settings['search.max_distance'] ?? '0.78' })}</Label>
          <input type="range" min={0.4} max={1.2} step={0.02}
            value={Number(settings['search.max_distance'] ?? 0.78)}
            onChange={e => set('search.max_distance', e.target.value)}
            className="w-full accent-indigo-500" />
          <div className="flex justify-between text-[11px] text-zinc-400 mt-0.5">
            <span>{t('settings.aiSearchStrict')}</span><span>{t('settings.aiSearchLoose')}</span>
          </div>
        </div>

        {/* AI metadata write-back */}
        <div className="p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <Label>{t('settings.aiWriteback')}</Label>
          <select
            value={settings['xmp.write_mode'] ?? 'off'}
            onChange={e => set('xmp.write_mode', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="off">{t('settings.aiWritebackOff')}</option>
            <option value="file">{t('settings.aiWritebackFile')}</option>
            <option value="file_sidecar">{t('settings.aiWritebackFileSidecar')}</option>
            <option value="sidecar">{t('settings.aiWritebackSidecar')}</option>
          </select>
          <p className="text-xs text-zinc-400 mt-1.5">
            {t('settings.aiWritebackHintA')} <code>dc:description</code>/<code>IPTC:Caption</code> {t('settings.aiWritebackHintB')}
          </p>
          <BackfillXmpButton />
        </div>

        {/* Re-use existing file metadata on scan */}
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.aiForceReindex')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              {t('settings.aiForceReindexDesc')}
            </p>
          </div>
          <Toggle value={(settings['scan.force_reindex'] ?? 'false') === 'true'} onChange={v => set('scan.force_reindex', v ? 'true' : 'false')} />
        </label>

        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.aiFacesOnImport')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              {t('settings.aiFacesOnImportDesc')}
            </p>
          </div>
          <Toggle value={(settings['scan.faces_on_import'] ?? 'true') !== 'false'} onChange={v => set('scan.faces_on_import', v ? 'true' : 'false')} />
        </label>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

function BackfillXmpButton() {
  const { t } = useT()
  const [msg, setMsg] = useState('')
  const m = useMutation({
    mutationFn: () => api.post('/photos/backfill-xmp').then(r => r.data),
    onSuccess: (d: any) => setMsg(t('settings.backfillRunning', { n: d.described_photos })),
    onError: () => setMsg(t('settings.backfillError')),
  })
  return (
    <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
      <button onClick={() => m.mutate()} disabled={m.isPending}
        className="px-3 py-2 rounded-lg border border-indigo-300 dark:border-indigo-700 text-sm text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 disabled:opacity-50">
        {m.isPending ? t('settings.backfillStarting') : t('settings.backfillBtn')}
      </button>
      <p className="text-[11px] text-zinc-400 mt-1.5">
        {t('settings.backfillHint')}
      </p>
      {msg && <p className="text-[11px] text-emerald-500 mt-1">{msg}</p>}
    </div>
  )
}

function VideoAISection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()

  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })
  useEffect(() => {
    if (settingsQuery.data) setSettings(settingsQuery.data)
  }, [settingsQuery.data])

  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => {
      setSaved(true); setTimeout(() => setSaved(false), 2200)
      qc.invalidateQueries({ queryKey: ['settings'] })
    },
  })

  function set(key: string, val: string) {
    setSettings(s => ({ ...s, [key]: val }))
  }

  const vidProvider = settings['video.ai_provider'] ?? 'same'
  const ollamaUrl = settings['video.ollama_url'] || settings['ai.ollama.url'] || 'http://localhost:11434'

  const ollamaModels = useQuery<ModelInfo[]>({
    queryKey: ['ollama-models-video', ollamaUrl],
    queryFn: () => api.get('/ai/models/ollama', { params: { base_url: ollamaUrl } }).then(r => r.data),
    enabled: vidProvider === 'ollama',
    staleTime: 60_000,
  })

  return (
    <div>
      <SectionHeader title={t('settings.vidTitle')} desc={t('settings.vidDesc')} />
      <div className="space-y-7">

        {/* Video AI provider */}
        <div>
          <Label>{t('settings.vidProvider')}</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {([
              { id: 'same', label: t('settings.vidProviderSame'), sub: t('settings.vidProviderSameSub') },
              { id: 'local', label: t('settings.aiProviderIntegrated'), sub: t('settings.aiProviderIntegratedSub') },
              { id: 'ollama', label: 'Ollama', sub: t('settings.vidProviderOllamaSub') },
              { id: 'gemini', label: 'Gemini', sub: t('settings.vidProviderGeminiSub') },
            ] as const).map(p => (
              <button key={p.id} onClick={() => set('video.ai_provider', p.id)}
                className={`px-3 py-2.5 rounded-xl text-sm font-medium border transition-all text-left ${
                  vidProvider === p.id
                    ? 'border-indigo-500 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                    : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-400'
                }`}
              >
                <span className="block">{p.label}</span>
                <span className="text-[10px] text-zinc-400">{p.sub}</span>
              </button>
            ))}
          </div>
          {vidProvider === 'local' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
              {([
                { id: 'florence2-base', label: 'Optimum — Florence-2-base', sub: t('settings.vidFlorenceSub') },
                { id: 'qwen2.5-vl-3b', label: 'Best — Qwen2.5-VL-3B', sub: t('settings.vidQwenSub') },
              ] as const).map(m => (
                <button key={m.id} onClick={() => set('video.local.model', m.id)}
                  className={`px-3 py-2 rounded-xl text-sm font-medium border transition-all text-left ${
                    (settings['video.local.model'] ?? 'florence2-base') === m.id
                      ? 'border-indigo-500 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400'
                      : 'border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-400 hover:border-zinc-400'
                  }`}>
                  <span className="block">{m.label}</span>
                  <span className="text-[10px] text-zinc-400">{m.sub}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {vidProvider === 'ollama' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{t('settings.vidOllamaForVideos')}</p>
            <div>
              <Label>{t('settings.aiOllamaUrl')}</Label>
              <Input value={settings['video.ollama_url'] ?? ollamaUrl} onChange={v => set('video.ollama_url', v)} placeholder="http://your-host:11434" />
            </div>
            <ModelSelect
              label={t('settings.aiVisionModel')}
              value={settings['video.ollama_model'] ?? ''}
              onChange={v => set('video.ollama_model', v)}
              models={ollamaModels.data ?? []}
              loading={ollamaModels.isLoading}
              filter={m => m.supports_vision}
              placeholder="moondream:latest oder llava"
            />
          </div>
        )}

        {/* Video description prompt */}
        <div>
          <Label>{t('settings.vidPrompt')}</Label>
          <textarea
            value={settings['ai.prompt.video'] ?? DEFAULT_VIDEO_PROMPT}
            onChange={e => set('ai.prompt.video', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          />
          <div className="flex justify-between items-center mt-1">
            <p className="text-[11px] text-zinc-400">{t('settings.vidPromptHint')}</p>
            <button type="button" onClick={() => set('ai.prompt.video', DEFAULT_VIDEO_PROMPT)}
              className="text-[11px] text-indigo-500 hover:underline">{t('settings.default')}</button>
          </div>
        </div>

        {/* Video language (shared with images) */}
        <div>
          <Label>{t('settings.vidLanguage')}</Label>
          <select value={settings['ai.language'] ?? 'de'} onChange={e => set('ai.language', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="de">{t('settings.langDe')}</option>
            <option value="en">{t('settings.langEn')}</option>
            <option value="fr">{t('settings.langFr')}</option>
          </select>
          <p className="text-[11px] text-zinc-400 mt-1">{t('settings.vidLanguageHint')}</p>
        </div>

        {/* Where video metadata goes */}
        <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 text-xs text-zinc-500 space-y-1.5">
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">{t('settings.vidMetaTitle')}</p>
          <p>• <b className="text-zinc-600 dark:text-zinc-300">{t('settings.vidMetaDbLabel')}</b> {t('settings.vidMetaDb')}</p>
          <p>• <b className="text-zinc-600 dark:text-zinc-300">{t('settings.vidMetaSidecarLabel')}</b> <code>&lt;video&gt;.xmp</code> {t('settings.vidMetaSidecar')}</p>
          <p>• <b className="text-zinc-600 dark:text-zinc-300">{t('settings.vidMetaEmbedLabel')}</b> {t('settings.vidMetaEmbed')}</p>
        </div>

        {/* Video transcoding */}
        <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{t('settings.vidTranscodeTitle')}</p>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.vidAutoTranscode')}</p>
              <p className="text-xs text-zinc-400">{t('settings.vidAutoTranscodeDesc')}</p>
            </div>
            <Toggle
              value={(settings['video.auto_transcode'] ?? 'false') === 'true'}
              onChange={v => set('video.auto_transcode', v ? 'true' : 'false')}
            />
          </label>
          <div>
            <Label>{t('settings.vidMaxResolution')}</Label>
            <select value={settings['video.transcode_resolution'] ?? '1080'} onChange={e => set('video.transcode_resolution', e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="480">480p</option>
              <option value="720">720p</option>
              <option value="1080">{t('settings.vidRes1080')}</option>
              <option value="original">{t('settings.vidResOriginal')}</option>
            </select>
            <p className="text-[11px] text-zinc-400 mt-1">
              {t('settings.vidResHint')}
            </p>
          </div>
        </div>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

function ChatSettingsSection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000, refetchOnWindowFocus: false,
  })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])
  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2200); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })
  const set = (k: string, v: string) => setSettings(s => ({ ...s, [k]: v }))
  const provider = (settings['chat.provider'] || 'gemini').toLowerCase()

  return (
    <div>
      <SectionHeader title={t('settings.chatTitle')} desc={t('settings.chatDesc')} />
      <div className="space-y-6 max-w-xl">
        <div>
          <Label>{t('settings.chatModel')}</Label>
          <div className="grid grid-cols-2 gap-2 mt-1">
            {([
              { id: 'gemini', label: 'Gemini', sub: t('settings.chatGeminiSub') },
              { id: 'local', label: t('settings.chatLocalLabel'), sub: t('settings.chatLocalSub') },
            ] as const).map(o => (
              <button key={o.id} onClick={() => set('chat.provider', o.id)}
                className={`text-left p-3 rounded-xl border transition ${
                  provider === o.id
                    ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40'
                    : 'border-zinc-200 dark:border-zinc-700 hover:bg-zinc-50 dark:hover:bg-zinc-800'}`}>
                <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{o.label}</p>
                <p className="text-[11px] text-zinc-400 mt-0.5">{o.sub}</p>
              </button>
            ))}
          </div>
          <p className="text-[11px] text-zinc-400 mt-2">
            {t('settings.chatHint')}
          </p>
        </div>
        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

function PipelineSection() {
  const { t } = useT()
  const qc = useQueryClient()
  const [busy, setBusy] = useState('')
  const { data: queues } = useQuery<{ cpu: number | null; gpu: number | null; celery: number | null; error?: string }>({
    queryKey: ['queues'], queryFn: () => api.get('/jobs/queues').then(r => r.data), refetchInterval: 2000,
  })
  const { data: stats } = useQuery<{ total?: number; by_status?: Record<string, number>; coverage?: Record<string, number> }>({
    queryKey: ['photo-stats'], queryFn: () => api.get('/photos/stats').then(r => r.data), refetchInterval: 3000,
  })
  // Remote backlog (descriptions + faces run on the pull-agent, NOT the local GPU
  // queue) + crop-cache warming progress.
  const { data: remote } = useQuery<{ enabled: boolean; pending: number; faces_pending: number; workers: { name: string }[] }>({
    queryKey: ['remote-status'], queryFn: () => api.get('/remote/status').then(r => r.data), refetchInterval: 3000,
  })
  const { data: crops } = useQuery<{ total_faces: number; cached: number }>({
    queryKey: ['crops-status'], queryFn: () => api.get('/people/crops-status').then(r => r.data), refetchInterval: 5000,
  })
  const warmCrops = useMutation({ mutationFn: () => api.post('/people/warm-crops').then(r => r.data) })
  const remoteActive = !!remote?.enabled && (remote?.workers?.length ?? 0) > 0
  const st = stats?.by_status ?? {}
  const cov = stats?.coverage ?? {}
  const errCount = (st['error'] ?? 0) + (cov['ai_error'] ?? 0)

  const act = useMutation({
    mutationFn: (url: string) => api.post(url).then(r => r.data),
    onSuccess: (d: any) => { setBusy(''); qc.invalidateQueries({ queryKey: ['photo-stats'] }); qc.invalidateQueries({ queryKey: ['queues'] }); alert(t('settings.pipActionStarted', { n: d?.reprocessing ?? d?.new ?? 'OK' })) },
    onError: () => setBusy(''),
  })
  const run = (key: string, url: string) => { setBusy(key); act.mutate(url) }

  const QCard = ({ label, val, hint, cls }: { label: string; val: number | null | undefined; hint: string; cls: string }) => (
    <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4">
      <p className={`text-2xl font-bold tabular-nums ${cls}`}>{val == null ? '–' : val.toLocaleString('de')}</p>
      <p className="text-sm text-zinc-700 dark:text-zinc-300">{label}</p>
      <p className="text-[11px] text-zinc-400 mt-0.5">{hint}</p>
    </div>
  )

  return (
    <div>
      <SectionHeader title={t('settings.pipTitle')} desc={t('settings.pipDesc')} />
      <div className="space-y-6 max-w-2xl">

        {/* Live queues */}
        <div>
          <Label>{t('settings.pipQueuesLive')}</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-1">
            <QCard label={t('settings.pipCpuQueue')} val={queues?.cpu} hint={t('settings.pipCpuQueueHint')} cls="text-indigo-500" />
            <QCard label={t('settings.pipGpuQueue')}
              val={queues?.gpu}
              hint={remoteActive ? t('settings.pipGpuQueueRemote') : t('settings.pipGpuQueueLocal')}
              cls="text-zinc-400" />
            <QCard label={t('settings.pipProcessing')} val={st['processing']}
              hint={remoteActive ? t('settings.pipProcessingRemote') : t('settings.pipProcessingLocal')}
              cls="text-sky-500" />
          </div>
          {queues?.error && <p className="text-xs text-amber-500 mt-1">{t('settings.pipQueueError', { error: queues.error })}</p>}
        </div>

        {/* Remote AI backlog — the real description/face work when a remote worker runs */}
        {remoteActive && (
          <div>
            <Label>{t('settings.pipRemoteTitle')}</Label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-1">
              <QCard label={t('settings.pipDescPending')} val={remote?.pending} hint={t('settings.pipDescPendingHint')} cls="text-violet-500" />
              <QCard label={t('settings.pipFacesPending')} val={remote?.faces_pending} hint={t('settings.pipFacesPendingHint')} cls="text-sky-500" />
              <QCard label={t('settings.pipWorkersConnected')} val={remote?.workers?.length} hint={t('settings.pipWorkersConnectedHint')} cls="text-emerald-500" />
            </div>
            <p className="text-[11px] text-zinc-400 mt-1">{t('settings.pipRemoteHint')}</p>
          </div>
        )}

        {/* Crop-cache warming (faster People page) */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 flex items-center gap-1.5"><ImageIcon size={14} /> {t('settings.pipCropCache')}</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {crops && crops.total_faces > 0
                  ? <><b className={crops.cached >= crops.total_faces ? 'text-emerald-500' : 'text-sky-500'}>{crops.cached.toLocaleString('de')}</b> / {crops.total_faces.toLocaleString('de')} {t('settings.pipCropCacheProgress', { pct: Math.round((crops.cached / crops.total_faces) * 100) })}</>
                  : t('settings.pipCropCacheEmpty')}
              </p>
              {crops && crops.total_faces > 0 && crops.cached < crops.total_faces && (
                <div className="mt-2 h-1.5 w-full max-w-xs bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
                  <div className="h-full bg-sky-500 rounded-full transition-all" style={{ width: `${Math.round((crops.cached / crops.total_faces) * 100)}%` }} />
                </div>
              )}
            </div>
            <ActBtn label={crops && crops.cached >= crops.total_faces ? t('settings.pipCropRecheck') : t('settings.pipCropPrepare')} busy={warmCrops.isPending} onClick={() => warmCrops.mutate()} />
          </div>
        </div>

        {/* Error queue */}
        <div className={`rounded-xl border p-4 ${errCount > 0 ? 'border-amber-400/60 bg-amber-500/5' : 'border-zinc-200 dark:border-zinc-700'}`}>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t('settings.pipErrorQueue')}</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {errCount > 0
                  ? <><b className="text-amber-600 dark:text-amber-400">{errCount.toLocaleString('de')}</b> {t('settings.pipErrorCount')}</>
                  : t('settings.pipNoErrors')}
              </p>
            </div>
            <span className={`text-2xl font-bold tabular-nums ${errCount > 0 ? 'text-amber-500' : 'text-emerald-500'}`}>{errCount.toLocaleString('de')}</span>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <ActBtn label={t('settings.pipReprocessAll')} busy={busy === 'failed'} onClick={() => run('failed', '/photos/reprocess-failed')} />
            <ActBtn label={t('settings.pipRetryAi')} busy={busy === 'ai'} onClick={() => run('ai', '/photos/reprocess-missing-ai')} />
          </div>
        </div>

        {/* Batch actions */}
        <div>
          <Label>{t('settings.pipBatch')}</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            <ActBtn label={t('settings.pipScanAll')} busy={busy === 'scan'} onClick={() => run('scan', '/sources/scan-all')} />
            <ActBtn label={t('settings.pipClusterFaces')} busy={busy === 'cluster'} onClick={() => run('cluster', '/people/cluster')} />
          </div>
          <p className="text-[11px] text-zinc-400 mt-2">{t('settings.pipBatchHint')}</p>
        </div>
      </div>
    </div>
  )

  function ActBtn({ label, busy, onClick }: { label: string; busy: boolean; onClick: () => void }) {
    return (
      <button onClick={onClick} disabled={busy}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50">
        <RefreshCw size={14} className={busy ? 'animate-spin' : ''} /> {label}
      </button>
    )
  }
}

function MemoriesSettingsSection() {
  const { t } = useT()
  const qc = useQueryClient()
  const [ids, setIds] = useState<number[]>([])
  const [saved, setSaved] = useState(false)
  const { data: people = [] } = useQuery<{ id: number; name: string; face_count: number; avatar_url?: string }[]>({
    queryKey: ['people'], queryFn: () => api.get('/people').then(r => r.data), staleTime: 60_000,
  })
  const { data: settings } = useQuery<Settings>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  useEffect(() => {
    const raw = settings?.['memories.person_ids'] || ''
    setIds(raw.split(',').map(s => parseInt(s)).filter(n => !isNaN(n)))
  }, [settings])
  const save = useMutation({
    mutationFn: () => api.put('/settings', { 'memories.person_ids': ids.join(',') }),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); qc.invalidateQueries({ queryKey: ['settings'] }); qc.invalidateQueries({ queryKey: ['memories'] }) },
  })
  const [q, setQ] = useState('')
  const named = people.filter(p => (p.name || '').trim()).sort((a, b) => a.name.localeCompare(b.name))
  const selected = named.filter(p => ids.includes(p.id))
  const matches = q.trim() ? named.filter(p => !ids.includes(p.id) && p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 30) : []
  const add = (id: number) => { setIds(s => [...s, id]); setQ('') }
  const remove = (id: number) => setIds(s => s.filter(x => x !== id))
  const av = (id: number) => `/api/people/${id}/avatar?v=${id}`

  return (
    <div>
      <SectionHeader title={t('settings.memTitle')} desc={t('settings.memDesc')} />
      <div className="space-y-4 max-w-2xl">
        <p className="text-sm text-zinc-600 dark:text-zinc-300">{selected.length === 0 ? t('settings.memAllPhotos') : t('settings.memSelectedPersons', { n: selected.length })}</p>

        {selected.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {selected.map(p => (
              <span key={p.id} className="flex items-center gap-1.5 pl-1 pr-2 py-1 rounded-full bg-indigo-600 text-white text-xs">
                <span className="w-5 h-5 rounded-full overflow-hidden bg-white/20"><img src={av(p.id)} alt="" className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} /></span>
                {p.name}
                <button onClick={() => remove(p.id)} className="hover:text-red-200" title={t('settings.remove')}><X size={12} /></button>
              </span>
            ))}
          </div>
        )}

        <div className="relative max-w-xs">
          <input value={q} onChange={e => setQ(e.target.value)} placeholder={t('settings.memAddPerson', { n: named.length })}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          {matches.length > 0 && (
            <div className="absolute z-10 mt-1 w-full max-h-52 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg">
              {matches.map(p => (
                <button key={p.id} onClick={() => add(p.id)} className="flex w-full items-center gap-2 px-3 py-1.5 text-sm text-left text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                  <span className="w-6 h-6 rounded-full overflow-hidden bg-zinc-300 dark:bg-zinc-700 shrink-0"><img src={av(p.id)} alt="" className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} /></span>
                  <span className="truncate">{p.name}</span><span className="ml-auto text-zinc-400 text-xs">{p.face_count}</span>
                </button>
              ))}
            </div>
          )}
          {named.length === 0 && <p className="text-sm text-zinc-400 mt-1">{t('settings.memNoNamed')}</p>}
        </div>

        <button onClick={() => save.mutate()} disabled={save.isPending}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {saved ? t('settings.savedCheck') : t('settings.save')}
        </button>
      </div>
    </div>
  )
}

function HighlightsAISettings() {
  const { t } = useT()
  const qc = useQueryClient()
  const [saved, setSaved] = useState(false)
  const { data: settings } = useQuery<Settings>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  const [weekly, setWeekly] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [provider, setProvider] = useState('veo')
  const [seconds, setSeconds] = useState('4')
  const [budget, setBudget] = useState('300')
  const [falKey, setFalKey] = useState('')
  const [falModel, setFalModel] = useState('fal-ai/minimax/hailuo-02/standard/image-to-video')
  useEffect(() => {
    if (!settings) return
    setWeekly((settings['highlights.weekly_enabled'] ?? 'false') === 'true')
    setEnabled((settings['highlights.ai_enabled'] ?? 'false') === 'true')
    setProvider(String(settings['highlights.ai_provider'] ?? 'veo'))
    setSeconds(String(settings['highlights.ai_clip_seconds'] ?? '4'))
    setBudget(String(settings['highlights.ai_budget_seconds_month'] ?? '300'))
    setFalKey(String(settings['highlights.fal_api_key'] ?? ''))
    setFalModel(String(settings['highlights.fal_model'] ?? 'fal-ai/minimax/hailuo-02/standard/image-to-video'))
  }, [settings])
  const hasGemini = !!(settings?.['ai.gemini.api_key'] || '').trim()
  const save = useMutation({
    mutationFn: () => api.put('/settings', {
      'highlights.weekly_enabled': weekly ? 'true' : 'false',
      'highlights.ai_enabled': enabled ? 'true' : 'false',
      'highlights.ai_provider': provider,
      'highlights.ai_clip_seconds': seconds,
      'highlights.ai_budget_seconds_month': budget,
      'highlights.fal_api_key': falKey,
      'highlights.fal_model': falModel,
    }),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })

  return (
    <div>
      <SectionHeader title={t('settings.hlTitle')} desc={t('settings.hlDesc')} />
      <div className="space-y-4 max-w-2xl">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t('settings.hlWeekly')}</div>
            <div className="text-xs text-zinc-500">{t('settings.hlWeeklyDesc')}</div>
          </div>
          <Toggle value={weekly} onChange={setWeekly} />
        </div>

        <div className="pt-3 border-t border-zinc-200 dark:border-zinc-800" />
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t('settings.hlAiVideo')}</div>
            <div className="text-xs text-zinc-500">{t('settings.hlAiVideoDesc')}</div>
          </div>
          <Toggle value={enabled} onChange={setEnabled} />
        </div>

        <label className="block text-sm text-zinc-700 dark:text-zinc-300">
          {t('settings.hlProvider')}
          <select value={provider} onChange={e => setProvider(e.target.value)}
            className="ml-2 px-2 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="fal">{t('settings.hlProviderFal')}</option>
            <option value="veo">{t('settings.hlProviderVeo')}</option>
            <option value="local">{t('settings.hlProviderLocal')}</option>
          </select>
        </label>

        {provider === 'veo' && enabled && !hasGemini && (
          <p className="text-xs text-amber-600 dark:text-amber-400">{t('settings.hlNoGemini')}</p>
        )}
        {provider === 'fal' && (
          <div className="space-y-2">
            <label className="block text-sm text-zinc-700 dark:text-zinc-300">{t('settings.hlFalKey')}
              <input type="password" value={falKey} onChange={e => setFalKey(e.target.value)} placeholder="fal_…"
                className="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </label>
            <label className="block text-sm text-zinc-700 dark:text-zinc-300">{t('settings.hlFalModel')}
              <input value={falModel} onChange={e => setFalModel(e.target.value)}
                className="mt-1 w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            </label>
            <p className="text-xs text-zinc-400">{t('settings.hlFalModelHintA')} <code>fal-ai/minimax/hailuo-02/standard/image-to-video</code> · <code>fal-ai/stable-video</code>. {t('settings.hlFalModelHintB')} <code>fal-ai/veo3/image-to-video</code>.</p>
            {enabled && !falKey.trim() && <p className="text-xs text-amber-600 dark:text-amber-400">{t('settings.hlNoFalKey')}</p>}
          </div>
        )}

        <div className="flex flex-wrap gap-6">
          <label className="text-sm text-zinc-700 dark:text-zinc-300">
            {t('settings.hlClipLength')}
            <select value={seconds} onChange={e => setSeconds(e.target.value)}
              className="ml-2 px-2 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="4">{t('settings.hlSec', { n: 4 })}</option><option value="6">{t('settings.hlSec', { n: 6 })}</option><option value="8">{t('settings.hlSec', { n: 8 })}</option>
            </select>
            {provider === 'fal' && <span className="ml-1 text-xs text-zinc-400">{t('settings.hlFalModelDep')}</span>}
          </label>
          <label className="text-sm text-zinc-700 dark:text-zinc-300">
            {t('settings.hlMonthBudget')}
            <input type="number" min={0} value={budget} onChange={e => setBudget(e.target.value)}
              className="ml-2 w-24 px-2 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </label>
        </div>
        <div className="text-xs text-zinc-500 rounded-lg bg-zinc-100 dark:bg-zinc-800/60 p-3 space-y-1">
          {provider === 'local' ? (
            <>
              <div className="font-medium text-zinc-700 dark:text-zinc-300">{t('settings.hlLocalTitle')}</div>
              <div><strong>{t('settings.hlLocalCostBold')}</strong>{t('settings.hlLocalCost')}</div>
              <div className="text-zinc-400">{t('settings.hlLocalQueue')}</div>
            </>
          ) : provider === 'veo' ? (
            <>
              <div className="font-medium text-zinc-700 dark:text-zinc-300">{t('settings.hlVeoTitle')}</div>
              <div>{t('settings.hlVeoCost')}</div>
              <div>{t('settings.hlVeoBudget', { budget: budget || '0', cost: ((Number(budget) || 0) * 0.15).toFixed(0) })}</div>
            </>
          ) : (
            <>
              <div className="font-medium text-zinc-700 dark:text-zinc-300">{t('settings.hlFalTitle')}</div>
              <div>{t('settings.hlFalCost')}</div>
              <div>{t('settings.hlFalBudget', { budget: budget || '0', cost: ((Number(budget) || 0) * 0.046).toFixed(0) })}</div>
            </>
          )}
          <div className="text-zinc-400">{t('settings.hlHardLimit')}</div>
        </div>

        <button onClick={() => save.mutate()} disabled={save.isPending}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {saved ? t('settings.savedCheck') : t('settings.save')}
        </button>
      </div>
    </div>
  )
}

function fmtEta(sec: number | null | undefined): string {
  if (sec == null || sec <= 0) return '—'
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60), s = Math.floor(sec % 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}min`
  if (m > 0) return `${m}min ${s}s`
  return `${s}s`
}

function RemoteWorkerSection() {
  const { t } = useT()
  const qc = useQueryClient()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const sQ = useQuery({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  useEffect(() => { if (sQ.data) setSettings(sQ.data) }, [sQ.data])
  const { data: status } = useQuery<{
    enabled: boolean; has_token: boolean; pending: number; faces_pending: number;
    embed_done: number; embed_total: number; avg_dur: number | null;
    roles: { role: string; label: string; pending: number; workers: number; avg_dur: number | null; eta_seconds: number | null; done?: number }[];
    workers: { name: string; role: string; last_seen: number; idle_s: number | null; jobs: number; last_dur: number | null; avg_dur: number | null }[]
  }>({
    queryKey: ['remote-status'], queryFn: () => api.get('/remote/status').then(r => r.data), refetchInterval: 3000,
  })
  // ── Worker command builder (self-service: add any worker type) ──────────────
  const [wType, setWType] = useState<'ollama' | 'bundled'>('ollama')
  const [wMode, setWMode] = useState('describe')       // describe | faces | embed | all
  const [wMedia, setWMedia] = useState('images')       // both | images | videos
  const [wModel, setWModel] = useState('gemma4:26b')   // ollama model OR bundled model
  const [wName, setWName] = useState('mac-describe')
  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); qc.invalidateQueries({ queryKey: ['settings'] }); qc.invalidateQueries({ queryKey: ['remote-status'] }) },
  })
  const set = (k: string, v: string) => setSettings(s => ({ ...s, [k]: v }))
  const enabled = (settings['remote.enabled'] ?? 'false') === 'true'
  const token = settings['remote.token'] ?? ''
  const genToken = () => {
    const t = Array.from(crypto.getRandomValues(new Uint8Array(24))).map(b => b.toString(16).padStart(2, '0')).join('')
    set('remote.token', t)
  }
  const now = Math.floor(Date.now() / 1000)
  const srvHost = `http://${window.location.hostname}:${window.location.port || 8090}`
  const SEL = "w-full px-2 py-1.5 rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 text-sm"
  const tok = token || '<TOKEN>'
  // Generate the start command for the chosen worker type/mode/media/model.
  const cmd = wType === 'ollama'
    ? `# Mac: Ollama läuft + Modell da (ollama pull ${wModel}); mac_describe_agent.py aus dem Repo.\n`
      + `# Einmalig falls nötig: sudo xcodebuild -license\n`
      + `PHOTOFLOW_SERVER=${srvHost} \\\n  PHOTOFLOW_REMOTE_TOKEN=${tok} \\\n`
      + `  WORKER_NAME=${wName} WORKER_MODE=${wMode} WORKER_MEDIA=${wMedia} \\\n`
      + `  OLLAMA_MODEL=${wModel} \\\n  python3 mac_describe_agent.py`
    : `cd /opt/photoflow\n`
      + `PHOTOFLOW_SERVER=${srvHost} PHOTOFLOW_REMOTE_TOKEN=${tok} \\\n`
      + `  WORKER_NAME=${wName} WORKER_MODE=${wMode} WORKER_MEDIA=${wMedia} \\\n`
      + `  docker compose -p photoflow-${wName} -f docker-compose.remote-worker.yml up -d --build`

  return (
    <div>
      <SectionHeader title={t('settings.rwTitle')} desc={t('settings.rwDesc')} />
      <div className="space-y-6 max-w-2xl">
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.rwEnable')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{t('settings.rwEnableDesc')}</p>
          </div>
          <Toggle value={enabled} onChange={v => set('remote.enabled', v ? 'true' : 'false')} />
        </label>

        <div>
          <Label>{t('settings.rwToken')}</Label>
          <div className="flex gap-2">
            <input value={token} onChange={e => set('remote.token', e.target.value)} placeholder={t('settings.rwTokenPlaceholder')}
              className="flex-1 px-3 py-2 text-sm font-mono rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100" />
            <button onClick={genToken} className="px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('settings.rwGenerate')}</button>
          </div>
        </div>

        {/* Worker-Builder: stell zusammen, was für ein Worker auf welchem Gerät laufen soll */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 space-y-3">
          <Label>{t('settings.rwBuilder')}</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
            <label className="space-y-1"><span className="text-xs text-zinc-500">{t('settings.rwType')}</span>
              <select value={wType} onChange={e => setWType(e.target.value as any)} className={SEL}>
                <option value="ollama">{t('settings.rwTypeOllama')}</option>
                <option value="bundled">{t('settings.rwTypeBundled')}</option>
              </select></label>
            <label className="space-y-1"><span className="text-xs text-zinc-500">{t('settings.rwTask')}</span>
              <select value={wMode} onChange={e => setWMode(e.target.value)} className={SEL}>
                <option value="describe">{t('settings.rwTaskDescribe')}</option>
                <option value="embed">{t('settings.rwTaskEmbed')}</option>
                <option value="faces">{t('settings.rwTaskFaces')}</option>
                <option value="all">{t('settings.rwTaskAll')}</option>
              </select></label>
            <label className="space-y-1"><span className="text-xs text-zinc-500">{t('settings.rwMedia')}</span>
              <select value={wMedia} onChange={e => setWMedia(e.target.value)} className={SEL}>
                <option value="images">{t('settings.rwMediaImages')}</option>
                <option value="videos">{t('settings.rwMediaVideos')}</option>
                <option value="both">{t('settings.rwMediaBoth')}</option>
              </select></label>
            <label className="space-y-1"><span className="text-xs text-zinc-500">{t('settings.rwWorkerName')}</span>
              <input value={wName} onChange={e => setWName(e.target.value)} className={SEL} /></label>
            {wType === 'ollama' && (
              <label className="space-y-1 col-span-2"><span className="text-xs text-zinc-500">{t('settings.rwOllamaModel')}</span>
                <input value={wModel} onChange={e => setWModel(e.target.value)} placeholder={t('settings.rwOllamaModelPlaceholder')} className={SEL} /></label>
            )}
          </div>
          <p className="text-[11px] text-zinc-400">
            {t('settings.rwBuilderHint')}
          </p>
        </div>

        <button onClick={() => save.mutate(settings)} disabled={save.isPending}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {saved ? t('settings.savedCheck') : t('settings.save')}
        </button>

        {/* Live status */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{t('settings.rwProcessingLive')}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${status?.enabled ? 'bg-emerald-500/15 text-emerald-500' : 'bg-zinc-500/15 text-zinc-400'}`}>{status?.enabled ? t('settings.rwActive') : t('settings.rwInactive')}</span>
          </div>
          {/* Pro Rolle getrennt — je eigener Backlog, eigenes Ø, eigene Restzeit.
              (Beschreibung ~10s vs Gesichter ~1s NICHT mehr zusammen gemittelt.) */}
          <div className="space-y-2">
            {(status?.roles ?? []).filter(r => r.pending > 0 || r.workers > 0).map(r => {
              const color = r.role === 'describe' ? 'text-violet-500' : r.role === 'embed' ? 'text-sky-500' : 'text-emerald-500'
              const rolW = (status?.workers ?? []).filter(w => w.role === r.role && (w.idle_s == null || w.idle_s < 120))
              return (
                <div key={r.role} className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-3">
                  <div className="flex items-center justify-between flex-wrap gap-x-4 gap-y-1">
                    <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{r.label}</span>
                    <div className="flex gap-4 text-xs text-zinc-500 tabular-nums">
                      <span><b className={color}>{r.pending.toLocaleString('de')}</b> {t('settings.rwOpen')}</span>
                      {r.done != null && <span><b className="text-emerald-500">{r.done.toLocaleString('de')}</b> {t('settings.rwDone')}</span>}
                      <span><b className="text-zinc-700 dark:text-zinc-300">{r.workers}</b> {t('settings.rwWorker')}</span>
                      <span>Ø {r.avg_dur != null ? `${r.avg_dur.toFixed(1)}s` : '—'}</span>
                      <span>{t('settings.rwRemaining')} <b className="text-zinc-700 dark:text-zinc-300">{fmtEta(r.eta_seconds)}</b></span>
                    </div>
                  </div>
                  {rolW.length > 0 && (
                    <ul className="mt-1.5 text-[11px] text-zinc-500 space-y-0.5">
                      {rolW.map(w => {
                        const idle = w.idle_s ?? Math.max(0, now - w.last_seen)
                        return (
                          <li key={w.name} className="flex flex-wrap items-center gap-x-2">
                            <span className={idle < 30 ? 'text-emerald-500' : 'text-zinc-400'}>●</span>
                            <b className="text-zinc-700 dark:text-zinc-300">{w.name}</b>
                            <span>· {t('settings.rwPhotos', { n: w.jobs })}</span>
                            {w.avg_dur != null && <span>· Ø {w.avg_dur.toFixed(1)}s</span>}
                            <span className="text-zinc-400">· {t('settings.rwAgo', { n: idle })}</span>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              )
            })}
            {(status?.workers?.length ?? 0) === 0 && (
              <p className="text-xs text-zinc-400">{t('settings.rwNoWorker')}</p>
            )}
          </div>
        </div>

        {/* Schritt-für-Schritt + generierter Start-Befehl */}
        <div>
          <Label>{t('settings.rwHowToAdd')}</Label>
          {wType === 'ollama' ? (
            <ol className="text-xs text-zinc-500 list-decimal ml-4 space-y-1 mb-2">
              <li>{t('settings.rwOllamaStep1a')} <a className="text-indigo-500" href="https://ollama.com" target="_blank" rel="noreferrer">Ollama</a> {t('settings.rwOllamaStep1b')}</li>
              <li>{t('settings.rwOllamaStep2')} <code>ollama pull {wModel}</code></li>
              <li><code>mac_describe_agent.py</code> {t('settings.rwOllamaStep3')} <code>~/photoflow_worker/</code>).</li>
              <li>{t('settings.rwOllamaStep4')}</li>
              <li>{t('settings.rwOllamaStep5a')} <code>launchctl</code>{t('settings.rwOllamaStep5b')}</li>
            </ol>
          ) : (
            <ol className="text-xs text-zinc-500 list-decimal ml-4 space-y-1 mb-2">
              <li>{t('settings.rwBundledStep1a')} <code>/opt/photoflow</code> {t('settings.rwBundledStep1b')}</li>
              <li>{t('settings.rwBundledStep2')}</li>
              <li>{t('settings.rwBundledStep3')} <code>docker compose -p photoflow-{wName} -f docker-compose.remote-worker.yml down</code></li>
            </ol>
          )}
          <pre className="text-[11px] bg-zinc-900 text-zinc-200 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">{cmd}</pre>
          {!token && <p className="text-[11px] text-amber-500 mt-1">{t('settings.rwNoTokenWarn')}</p>}
        </div>
      </div>

      {/* Live remote-worker log — full width, outside the form column */}
      <div className="mt-8">
        <RemoteWorkerLog />
      </div>
    </div>
  )
}

function RemoteWorkerLog() {
  const { t } = useT()
  const [open, setOpen] = useState(true)
  const { data = [] } = useQuery<{ ts: string; level: string; feature: string; message: string }[]>({
    queryKey: ['logs', 'remote-feed'],
    queryFn: () => api.get('/logs/remote', { params: { limit: 80 } }).then(r => r.data),
    refetchInterval: open ? 3000 : false, staleTime: 0,
  })
  const lines = [...data].reverse()
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <Label>{t('settings.rwLogTitle')}</Label>
        <button onClick={() => setOpen(o => !o)} className="text-xs text-indigo-500 hover:underline">{open ? t('settings.rwLogPause') : t('settings.rwLogResume')}</button>
      </div>
      <div className="h-64 overflow-y-auto rounded-lg bg-zinc-950 p-3 font-mono text-[11px] leading-relaxed">
        {lines.length === 0 ? (
          <p className="text-zinc-500">{t('settings.rwLogEmpty')}</p>
        ) : lines.map((e, i) => (
          <div key={i} className={`whitespace-pre-wrap break-words py-0.5 ${e.level === 'WARNING' || e.level === 'ERROR' ? 'text-amber-400' : 'text-emerald-300'}`}>
            <span className="text-zinc-600">{(e.ts || '').slice(11, 19)} </span>{e.message}
          </div>
        ))}
      </div>
      <p className="text-[11px] text-zinc-400 mt-1">{t('settings.rwLogHint')}</p>
    </div>
  )
}

function FacesSection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()

  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000, refetchOnWindowFocus: false,
  })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])

  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2200); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })
  const set = (k: string, v: string) => setSettings(s => ({ ...s, [k]: v }))

  const enabled = (settings['faces.enabled'] ?? 'true') === 'true'

  return (
    <div>
      <SectionHeader title={t('settings.facTitle')} desc={t('settings.facDesc')} />
      <div className="space-y-6 max-w-xl">
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.facEnable')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{t('settings.facEnableDesc')}</p>
          </div>
          <Toggle value={enabled} onChange={v => set('faces.enabled', v ? 'true' : 'false')} />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>{t('settings.facEngine')}</Label>
            <select value={settings['face.engine'] ?? 'facenet'} onChange={e => set('face.engine', e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="facenet">{t('settings.facEngineFacenet')}</option>
              <option value="insightface">{t('settings.facEngineInsight')}</option>
            </select>
          </div>
          <div>
            <Label>{t('settings.facClusterAlgo')}</Label>
            <select value={settings['face.cluster_algo'] ?? 'dbscan'} onChange={e => set('face.cluster_algo', e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="dbscan">{t('settings.facAlgoDbscan')}</option>
              <option value="hdbscan">{t('settings.facAlgoHdbscan')}</option>
            </select>
          </div>
        </div>
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.facAutoCluster')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{t('settings.facAutoClusterDesc')}</p>
          </div>
          <Toggle value={(settings['face.auto_cluster'] ?? 'true') !== 'false'} onChange={v => set('face.auto_cluster', v ? 'true' : 'false')} />
        </label>
        <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-700/40 text-xs text-amber-700 dark:text-amber-300">
          {t('settings.facEngineWarn')}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <Label>{t('settings.facClusterThreshold')}</Label>
            <Input value={settings['face.clustering_threshold'] ?? '0.5'} onChange={v => set('face.clustering_threshold', v)} placeholder="0.5" />
            <p className="text-xs text-zinc-400 mt-1">{t('settings.facClusterThresholdHint')}</p>
          </div>
          <div>
            <Label>{t('settings.facMinConfidence')}</Label>
            <Input value={settings['face.min_confidence'] ?? '0.7'} onChange={v => set('face.min_confidence', v)} placeholder="0.7" />
          </div>
          <div>
            <Label>{t('settings.facMinSize')}</Label>
            <Input value={settings['face.min_size_px'] ?? '40'} onChange={v => set('face.min_size_px', v)} placeholder="40" />
          </div>
          <div>
            <Label>{t('settings.facMinFaces')}</Label>
            <Input value={settings['face.min_cluster_size'] ?? '3'} onChange={v => set('face.min_cluster_size', v)} placeholder="3" />
          </div>
          <div>
            <Label>{t('settings.facMergeThreshold')}</Label>
            <Input value={settings['face.merge_threshold'] ?? '0.5'} onChange={v => set('face.merge_threshold', v)} placeholder="0.5" />
          </div>
        </div>
        <p className="text-xs text-zinc-400">{t('settings.facMiniHint')}</p>

        <div className="space-y-3 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide flex items-center gap-2">
            <Video size={12} /> {t('settings.facInVideos')}
          </p>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.facDetectInVideos')}</p>
              <p className="text-xs text-zinc-400">{t('settings.facDetectInVideosDesc')}</p>
            </div>
            <Toggle value={(settings['video.face_recognition'] ?? 'false') === 'true'} onChange={v => set('video.face_recognition', v ? 'true' : 'false')} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>{t('settings.facFrameInterval')}</Label>
              <Input value={settings['video.face_interval_sec'] ?? '5'} onChange={v => set('video.face_interval_sec', v)} placeholder="5" />
            </div>
            <div>
              <Label>{t('settings.facMaxFrames')}</Label>
              <Input value={settings['video.max_frames'] ?? '30'} onChange={v => set('video.max_frames', v)} placeholder="30" />
            </div>
          </div>
        </div>

        <p className="text-xs text-emerald-500">
          {t('settings.facActiveHint')}
        </p>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

type BackupFile = { name: string; size_mb: number; created_at: string; type: string }
type HWInfo = { name: string; available: boolean; info: string; encode_h264_codec: string }

function BackupSection() {
  const { t } = useT()
  const [rcloneRemote, setRcloneRemote] = useState('')
  const [keepDays, setKeepDays] = useState(30)
  const [inclThumbs, setInclThumbs] = useState(true)
  const qc = useQueryClient()

  const { data: backups = [], refetch } = useQuery<BackupFile[]>({
    queryKey: ['backups'],
    queryFn: () => api.get('/backup/list').then(r => r.data),
  })

  const { data: hw } = useQuery<HWInfo>({
    queryKey: ['hw-info'],
    queryFn: () => api.get('/backup/hw').then(r => r.data),
    staleTime: 300_000,
  })

  const runBackup = useMutation({
    mutationFn: () => api.post('/backup/run', null, { params: { rclone_remote: rcloneRemote, include_thumbnails: inclThumbs } }),
    onSuccess: () => { refetch() },
  })

  const prune = useMutation({
    mutationFn: () => api.delete('/backup/prune', { params: { keep_days: keepDays } }),
    onSuccess: () => refetch(),
  })

  // Automatic schedule (persisted settings the scheduled_backup beat task reads).
  const { data: appSettings } = useQuery<Settings>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  const [sched, setSched] = useState('off')
  const [savedSched, setSavedSched] = useState(false)
  const [mirrorRemote, setMirrorRemote] = useState('')
  const [mirrorSched, setMirrorSched] = useState('off')
  const [encrypt, setEncrypt] = useState(false)
  const [passphrase, setPassphrase] = useState('')
  useEffect(() => {
    if (!appSettings) return
    if (appSettings['backup.schedule']) setSched(appSettings['backup.schedule'])
    if (appSettings['backup.keep_days']) setKeepDays(Number(appSettings['backup.keep_days']))
    if (appSettings['backup.include_thumbnails'] !== undefined) setInclThumbs(String(appSettings['backup.include_thumbnails']) !== 'false')
    if (appSettings['backup.mirror_remote']) setMirrorRemote(appSettings['backup.mirror_remote'])
    if (appSettings['backup.mirror_schedule']) setMirrorSched(appSettings['backup.mirror_schedule'])
    if (appSettings['backup.encrypt'] !== undefined) setEncrypt(String(appSettings['backup.encrypt']) === 'true')
  }, [appSettings])
  const saveSchedule = useMutation({
    mutationFn: () => api.put('/settings', {
      'backup.schedule': sched, 'backup.keep_days': String(keepDays),
      'backup.rclone_remote': rcloneRemote, 'backup.include_thumbnails': String(inclThumbs),
      'backup.mirror_remote': mirrorRemote, 'backup.mirror_schedule': mirrorSched,
      'backup.encrypt': String(encrypt), ...(passphrase ? { 'backup.passphrase': passphrase } : {}),
    }),
    onSuccess: () => { setSavedSched(true); setTimeout(() => setSavedSched(false), 2000); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })
  const mirrorNow = useMutation({
    mutationFn: () => api.post('/backup/mirror-originals'),
    onSuccess: () => alert(t('settings.bkMirrorStarted')),
    onError: () => alert(t('settings.bkMirrorError')),
  })
  const restore = useMutation({
    mutationFn: (b: BackupFile) => b.type === 'db'
      ? api.post('/backup/restore/db', null, { params: { filename: b.name } })
      : api.post('/backup/restore/files', null, { params: { filename: b.name } }),
    onSuccess: (r: any) => alert(r?.data?.ok === false ? t('settings.bkRestoreErrors') : t('settings.bkRestoreOk')),
    onError: () => alert(t('settings.bkRestoreFailed')),
  })
  const verify = useMutation({
    mutationFn: (name: string) => api.post('/backup/verify', null, { params: { filename: name } }).then(r => r.data),
    onSuccess: (d: any) => alert(d?.ok ? t('settings.bkVerifyOk', { tables: d.tables, photos: d.photo_rows, mb: d.size_mb }) : t('settings.bkVerifyFailed', { error: d?.error ?? t('settings.unknown') })),
  })

  const hwColor = !hw ? 'text-zinc-400'
    : hw.name === 'cuda' ? 'text-green-400'
    : hw.name === 'qsv' ? 'text-blue-400'
    : hw.name === 'vaapi' ? 'text-sky-400'
    : 'text-zinc-400'

  return (
    <div>
      <SectionHeader title={t('settings.bkTitle')} desc={t('settings.bkDesc')} />

      {/* HW acceleration status */}
      <div className="mb-6 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2 flex items-center gap-2">
          <Cpu size={12} /> {t('settings.bkHwAccel')}
        </p>
        {hw ? (
          <div className="flex items-center gap-3">
            <div className={`text-sm font-medium ${hwColor}`}>
              {hw.name === 'cuda' ? 'NVIDIA CUDA / NVENC' :
               hw.name === 'qsv' ? 'Intel Quick Sync' :
               hw.name === 'vaapi' ? 'VAAPI' :
               hw.name === 'videotoolbox' ? 'Apple VideoToolbox' :
               t('settings.bkHwSoftware')}
            </div>
            <span className="text-xs text-zinc-400">{hw.info}</span>
          </div>
        ) : (
          <p className="text-sm text-zinc-400">{t('settings.bkDetectingHw')}</p>
        )}
        <p className="text-xs text-zinc-500 mt-1">{t('settings.bkEncoder')} <code className="text-indigo-400">{hw?.encode_h264_codec ?? '...'}</code></p>
      </div>

      {/* Backup list */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">{t('settings.bkSavedBackups')}</p>
          <button onClick={() => refetch()} className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1">
            <RefreshCw size={11} /> {t('settings.refresh')}
          </button>
        </div>
        {backups.length === 0 && (
          <p className="text-sm text-zinc-400">{t('settings.bkNoBackups')}</p>
        )}
        <div className="space-y-2">
          {backups.map(b => (
            <div key={b.name} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-sm">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${b.type === 'db' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-zinc-500/20 text-zinc-400'}`}>
                {b.type.toUpperCase()}
              </span>
              <span className="flex-1 font-mono text-xs text-zinc-600 dark:text-zinc-400 truncate">{b.name}</span>
              <span className="text-zinc-400 text-xs">{b.size_mb} MB</span>
              {b.type === 'db' && <button onClick={() => verify.mutate(b.name)} className="text-zinc-400 hover:text-zinc-200 text-xs">{t('settings.bkVerify')}</button>}
              <button onClick={() => { if (confirm(t('settings.bkRestoreConfirm', { name: b.name, target: b.type === 'db' ? t('settings.bkDatabase') : t('settings.bkFiles') }))) restore.mutate(b) }}
                className="text-amber-400 hover:text-amber-300 text-xs transition-colors">{t('settings.bkRestore')}</button>
              <a href={`/api/backup/download/${b.name}`} download
                className="text-indigo-400 hover:text-indigo-300 text-xs transition-colors">{t('settings.download')}</a>
            </div>
          ))}
        </div>
      </div>

      {/* Automatic schedule */}
      <div className="mb-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">{t('settings.bkAutoBackup')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>{t('settings.bkSchedule')}</Label>
            <select value={sched} onChange={e => setSched(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100">
              <option value="off">{t('settings.bkSchedOff')}</option>
              <option value="daily">{t('settings.bkSchedDaily')}</option>
              <option value="weekly">{t('settings.bkSchedWeekly')}</option>
            </select>
          </div>
          <div>
            <Label>{t('settings.bkRetention')}</Label>
            <Input value={String(keepDays)} onChange={v => setKeepDays(Number(v) || 30)} placeholder="30" />
          </div>
        </div>
        <label className="flex items-center gap-2 mt-3 text-sm text-zinc-600 dark:text-zinc-300 cursor-pointer">
          <input type="checkbox" checked={inclThumbs} onChange={e => setInclThumbs(e.target.checked)} className="accent-indigo-600" />
          {t('settings.bkInclThumbs')}
          <span className="text-[11px] text-zinc-400">{t('settings.bkInclThumbsHint')}</span>
        </label>
        <button onClick={() => saveSchedule.mutate()} disabled={saveSchedule.isPending}
          className="mt-3 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {savedSched ? t('settings.savedCheck') : t('settings.bkSaveSchedule')}
        </button>
        <p className="text-[11px] text-zinc-400 mt-2">{t('settings.bkScheduleHint', { thumbs: inclThumbs ? t('settings.bkPlusThumbs') : '' })}</p>

        <label className="flex items-center gap-2 mt-3 text-sm text-zinc-600 dark:text-zinc-300 cursor-pointer">
          <input type="checkbox" checked={encrypt} onChange={e => setEncrypt(e.target.checked)} className="accent-indigo-600" />
          {t('settings.bkEncrypt')}
        </label>
        {encrypt && (
          <div className="mt-1">
            <Label>{t('settings.bkPassword')}</Label>
            <Input type="password" value={passphrase} onChange={setPassphrase} placeholder="••••••••" />
            <p className="text-[11px] text-amber-500 mt-1">{t('settings.bkPasswordWarnA')} <code>PHOTOFLOW_BACKUP_PASSPHRASE</code>.)</p>
          </div>
        )}
      </div>

      {/* Originals offsite mirror */}
      <div className="space-y-3 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{t('settings.bkMirrorTitle')}</p>
        <p className="text-[11px] text-zinc-400">{t('settings.bkMirrorDesc')}</p>
        <div className="grid sm:grid-cols-2 gap-3">
          <div>
            <Label>{t('settings.bkRcloneTarget')}</Label>
            <Input value={mirrorRemote} onChange={setMirrorRemote} placeholder="b2:bucket/nimtaflow-originals" />
          </div>
          <div>
            <Label>{t('settings.bkSchedule')}</Label>
            <select value={mirrorSched} onChange={e => setMirrorSched(e.target.value)}
              className="w-full rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 px-3 py-2 text-sm">
              <option value="off">{t('settings.bkSchedOff')}</option><option value="daily">{t('settings.bkSchedDaily')}</option><option value="weekly">{t('settings.bkSchedWeekly')}</option>
            </select>
          </div>
        </div>
        <button onClick={() => mirrorNow.mutate()} disabled={mirrorNow.isPending || !mirrorRemote}
          className="px-4 py-2 rounded-lg border border-zinc-300 dark:border-zinc-600 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-40">
          {t('settings.bkMirrorNow')}
        </button>
      </div>

      {/* Run backup */}
      <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">{t('settings.bkCreateBackup')}</p>
        <div>
          <Label>{t('settings.bkRcloneRemote')}</Label>
          <Input value={rcloneRemote} onChange={setRcloneRemote} placeholder="b2:my-bucket/photoflow oder gdrive:backup" />
          <p className="text-[11px] text-zinc-400 mt-1">{t('settings.bkRcloneRemoteHint')}</p>
        </div>
        <button
          onClick={() => runBackup.mutate()}
          disabled={runBackup.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {runBackup.isPending ? <Loader2 size={14} className="animate-spin" /> : <HardDrive size={14} />}
          {t('settings.bkRunNow')}
        </button>
        {runBackup.isSuccess && (
          <p className="text-xs text-emerald-400 flex items-center gap-1"><CircleCheck size={12} /> {t('settings.bkSuccess')}</p>
        )}
      </div>

      {/* Prune */}
      <div className="mt-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">{t('settings.bkPruneTitle')}</p>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <Label>{t('settings.bkRetentionDays', { n: keepDays })}</Label>
            <input type="range" min={7} max={365} step={7} value={keepDays} onChange={e => setKeepDays(Number(e.target.value))}
              className="w-full accent-indigo-500" />
          </div>
          <button onClick={() => prune.mutate()} disabled={prune.isPending}
            className="px-3 py-2 rounded-lg text-sm bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors shrink-0">
            {t('settings.bkPrune')}
          </button>
        </div>
      </div>
    </div>
  )
}

function TripsSection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000, refetchOnWindowFocus: false,
  })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])
  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2200); qc.invalidateQueries({ queryKey: ['settings'] }); qc.invalidateQueries({ queryKey: ['trips'] }) },
  })
  const set = (k: string, v: string) => setSettings(s => ({ ...s, [k]: v }))

  return (
    <div>
      <SectionHeader title={t('settings.tripsTitle')} desc={t('settings.tripsDesc')} />
      <div className="space-y-5 max-w-xl">
        <div>
          <Label>{t('settings.tripsMinPhotos')}</Label>
          <Input value={settings['trips.min_photos'] ?? '8'} onChange={v => set('trips.min_photos', v.replace(/[^0-9]/g, ''))} type="number" placeholder="8" />
          <p className="text-xs text-zinc-400 mt-1">{t('settings.tripsMinPhotosHint')}</p>
        </div>
        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

type ShareRow = {
  id: number; token: string; url: string; share_type: string; title?: string
  has_password: boolean; expires_at?: string | null; allow_download: boolean; view_count: number
}

function SharingSection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState<number | null>(null)
  const qc = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000, refetchOnWindowFocus: false,
  })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])
  const sharesQuery = useQuery({
    queryKey: ['shares'],
    queryFn: () => api.get('/shares').then(r => r.data as ShareRow[]),
    staleTime: 10_000,
  })
  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2200); qc.invalidateQueries({ queryKey: ['settings'] }); qc.invalidateQueries({ queryKey: ['shares'] }) },
  })
  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/shares/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['shares'] }),
  })
  const set = (k: string, v: string) => setSettings(s => ({ ...s, [k]: v }))
  const copy = (s: ShareRow) => { navigator.clipboard.writeText(s.url); setCopied(s.id); setTimeout(() => setCopied(null), 1500) }
  const typeLabel = (ty: string) => ty === 'album' ? t('settings.shTypeAlbum') : ty === 'photo' ? t('settings.shTypePhoto') : t('settings.shTypeTrip')

  return (
    <div>
      <SectionHeader title={t('settings.shTitle')} desc={t('settings.shDesc')} />
      <div className="space-y-6 max-w-2xl">
        <div>
          <Label>{t('settings.shPublicBaseUrl')}</Label>
          <Input value={settings['share.public_base_url'] ?? ''} onChange={v => set('share.public_base_url', v.trim())}
                 placeholder="https://fotos.example.com" />
          <p className="text-xs text-zinc-400 mt-1">
            {t('settings.shPublicBaseUrlHintA')} <code>https://fotos.example.com/s/&lt;token&gt;</code>{t('settings.shPublicBaseUrlHintB')}
          </p>
          <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
        </div>

        <div>
          <Label>{t('settings.shActiveLinks')} {sharesQuery.data ? `(${sharesQuery.data.length})` : ''}</Label>
          <div className="mt-2 space-y-2">
            {(sharesQuery.data ?? []).length === 0 && (
              <p className="text-sm text-zinc-400">{t('settings.shNoLinks')}</p>
            )}
            {(sharesQuery.data ?? []).map(s => (
              <div key={s.id} className="flex items-center gap-2 rounded-lg border border-zinc-200 dark:border-zinc-700 px-3 py-2">
                <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-500 shrink-0">{typeLabel(s.share_type)}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{s.title || s.url}</div>
                  <div className="text-xs text-zinc-400 truncate">
                    {s.has_password ? t('settings.shPassword') + ' · ' : ''}
                    {s.expires_at ? t('settings.shExpires', { date: new Date(s.expires_at).toLocaleDateString() }) + ' · ' : ''}
                    {s.allow_download ? t('settings.shDownloadOn') : t('settings.shViewOnly')} · {t('settings.shViewCount', { n: s.view_count })}
                  </div>
                </div>
                <button onClick={() => copy(s)} title={t('settings.shCopyLink')}
                  className="p-2 text-zinc-500 hover:text-indigo-500 shrink-0">
                  {copied === s.id ? <Check size={16} /> : <Copy size={16} />}
                </button>
                <button onClick={() => { if (confirm(t('settings.shRevokeConfirm'))) del.mutate(s.id) }}
                  title={t('settings.shRevoke')} className="p-2 text-red-500 hover:text-red-400 shrink-0">
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function MapSection() {
  const { t } = useT()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then(r => r.data as Settings),
    staleTime: 30_000, refetchOnWindowFocus: false,
  })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])
  const save = useMutation({
    mutationFn: (s: Settings) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2200); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })
  const set = (k: string, v: string) => setSettings(s => ({ ...s, [k]: v }))

  return (
    <div>
      <SectionHeader title={t('settings.mapTitle')} desc={t('settings.mapDesc')} />
      <div className="space-y-5 max-w-xl">
        <div>
          <Label>{t('settings.mapDefaultLayer')}</Label>
          <select value={settings['map.default_layer'] ?? 'osm'} onChange={e => set('map.default_layer', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="osm">{t('settings.mapLayerOsm')}</option>
            <option value="satellite">{t('settings.mapLayerSatellite')}</option>
            <option value="dark">{t('settings.mapLayerDark')}</option>
            <option value="light">{t('settings.mapLayerLight')}</option>
            <option value="voyager">Voyager (CARTO)</option>
            <option value="topo">Topo (OpenTopoMap)</option>
            <option value="maptiler">{t('settings.mapLayerMaptiler')}</option>
            <option value="maptiler_sat">{t('settings.mapLayerMaptilerSat')}</option>
          </select>
          <p className="text-xs text-zinc-400 mt-1">{t('settings.mapLayerHint')}</p>
        </div>

        <div>
          <Label>{t('settings.mapMaptilerKey')}</Label>
          <Input value={settings['map.maptiler_key'] ?? ''} onChange={v => set('map.maptiler_key', v)} type="password" placeholder={t('settings.mapMaptilerKeyPlaceholder')} />
          <p className="text-xs text-zinc-400 mt-1">{t('settings.mapMaptilerKeyHint')}</p>
        </div>

        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.mapStreetView')}</p>
            <p className="text-xs text-zinc-400 mt-0.5">{t('settings.mapStreetViewDesc')}</p>
          </div>
          <Toggle value={(settings['map.streetview'] ?? 'true') !== 'false'} onChange={v => set('map.streetview', v ? 'true' : 'false')} />
        </label>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

// ─── Log viewer ───────────────────────────────────────────────────────────────

type LogEntry = { ts: string; level: string; feature: string; message: string }

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-zinc-400',
  INFO: 'text-emerald-400',
  WARNING: 'text-amber-400',
  ERROR: 'text-red-400',
}

function FeaturesSection() {
  const { t } = useT()
  const qc = useQueryClient()
  const [settings, setSettings] = useState<Settings>({})
  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])
  const setBool = (k: string, v: boolean) => {
    const next = { ...settings, [k]: v ? 'true' : 'false' }
    setSettings(next); api.put('/settings', next).then(() => qc.invalidateQueries({ queryKey: ['settings'] }))
  }
  const Row = ({ k, title, desc }: { k: string; title: string; desc: string }) => (
    <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
      <div className="pr-4"><p className="text-sm text-zinc-700 dark:text-zinc-300">{title}</p><p className="text-xs text-zinc-500 mt-0.5">{desc}</p></div>
      <Toggle value={(settings[k] ?? 'false') === 'true'} onChange={v => setBool(k, v)} />
    </label>
  )
  return (
    <div>
      <SectionHeader title={t('settings.featTitle')} desc={t('settings.featDesc')} />
      <div className="space-y-3 max-w-xl">
        <Row k="features.relationships" title={t('settings.featRelationships')} desc={t('settings.featRelationshipsDesc')} />
        <Row k="map.globe_default" title={t('settings.featGlobe')} desc={t('settings.featGlobeDesc')} />
      </div>
    </div>
  )
}

type AppUser = { id: number; email: string; name: string; role: 'admin' | 'user'; is_active: boolean; last_login: string | null; access_config?: Record<string, any> | null }

function UsersSection() {
  const { t } = useT()
  const qc = useQueryClient()
  const [settings, setSettings] = useState<Settings>({})
  const [pwFor, setPwFor] = useState<number | null>(null)
  const [pw, setPw] = useState('')
  const [accFor, setAccFor] = useState<number | null>(null)
  const [acc, setAcc] = useState<Record<string, any>>({})
  const [editFor, setEditFor] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [add, setAdd] = useState({ email: '', name: '', password: '', role: 'user' })
  const [showAdd, setShowAdd] = useState(false)

  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  useEffect(() => { if (settingsQuery.data) setSettings(settingsQuery.data) }, [settingsQuery.data])
  const enforce = (settings['auth.enforce'] ?? 'true') === 'true'
  const setEnforce = (v: boolean) => {
    const next = { ...settings, 'auth.enforce': v ? 'true' : 'false' }
    setSettings(next); api.put('/settings', next).then(() => qc.invalidateQueries({ queryKey: ['settings'] }))
  }

  const usersQuery = useQuery<AppUser[]>({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data), retry: false })
  const peopleQuery = useQuery<{ id: number; name: string }[]>({ queryKey: ['people-min'], queryFn: () => api.get('/people').then(r => r.data), staleTime: 60_000 })
  const srcQuery = useQuery<{ id: number; path: string }[]>({ queryKey: ['sources'], queryFn: () => api.get('/sources').then(r => r.data), staleTime: 60_000 })
  const namedPeople = (peopleQuery.data || []).filter(p => (p.name || '').trim())
  const sourcePaths = (srcQuery.data || []).map(s => s.path)
  const toggleIn = (arr: any[] | undefined, v: any) => {
    const s = new Set(arr || []); s.has(v) ? s.delete(v) : s.add(v); return [...s]
  }
  const inval = () => qc.invalidateQueries({ queryKey: ['users'] })
  const createU = useMutation({ mutationFn: () => api.post('/users', add), onSuccess: () => { inval(); setShowAdd(false); setAdd({ email: '', name: '', password: '', role: 'user' }) } })
  const patchU = useMutation({ mutationFn: ({ id, body }: { id: number; body: Partial<AppUser> }) => api.patch(`/users/${id}`, body), onSuccess: inval })
  const delU = useMutation({ mutationFn: (id: number) => api.delete(`/users/${id}`), onSuccess: inval })
  const setPwM = useMutation({ mutationFn: ({ id, password }: { id: number; password: string }) => api.post(`/users/${id}/password`, { password }), onSuccess: () => { setPwFor(null); setPw('') } })

  const notAuthed = usersQuery.isError
  const sel = 'px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div>
      <SectionHeader title={t('settings.usrTitle')} desc={t('settings.usrDesc')} />

      {notAuthed ? (
        <div className="max-w-xl p-4 rounded-xl border border-amber-300 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/20 text-sm text-amber-800 dark:text-amber-200">
          <p className="flex items-center gap-2 font-medium"><Lock size={15} /> {t('settings.usrLoginAsAdmin')}</p>
          <p className="mt-1 text-amber-700 dark:text-amber-300/90">{t('settings.usrAdminOnlyHintA')} <strong>admin@photoflow.local</strong> / <strong>Nimtz@1977</strong>.</p>
          <a href="/login" className="inline-flex items-center gap-1.5 mt-3 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500"><KeyRound size={14} /> {t('settings.usrToLogin')}</a>
        </div>
      ) : (
        <div className="space-y-6 max-w-2xl">
          {/* Login enforce */}
          <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">{t('settings.usrEnforceLogin')}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{t('settings.usrEnforceLoginDesc')}</p>
            </div>
            <Toggle value={enforce} onChange={setEnforce} />
          </label>

          {/* User list */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-200 dark:divide-zinc-800">
            {(usersQuery.data ?? []).map(u => (
              <div key={u.id} className="p-3 flex flex-wrap items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs font-semibold shrink-0">{u.name.charAt(0).toUpperCase()}</div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate">{u.name} {!u.is_active && <span className="text-xs text-zinc-500">{t('settings.usrDisabled')}</span>}</p>
                  <p className="text-xs text-zinc-500 truncate">{u.email}</p>
                </div>
                <select className={sel} value={u.role} onChange={e => patchU.mutate({ id: u.id, body: { role: e.target.value as 'admin' | 'user' } })}>
                  <option value="admin">{t('settings.usrRoleAdmin')}</option>
                  <option value="user">{t('settings.usrRoleUser')}</option>
                </select>
                <button onClick={() => patchU.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                  className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                  {u.is_active ? t('settings.usrDeactivate') : t('settings.usrActivate')}
                </button>
                {u.role !== 'admin' && (
                  <button onClick={() => { setAccFor(accFor === u.id ? null : u.id); setAcc(u.access_config || {}) }}
                    className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('settings.usrAccess')}</button>
                )}
                <button onClick={() => { setEditFor(editFor === u.id ? null : u.id); setEditName(u.name); setEditEmail(u.email) }}
                  className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('settings.edit')}</button>
                <button onClick={() => { setPwFor(pwFor === u.id ? null : u.id); setPw('') }}
                  className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('settings.usrPassword')}</button>
                <button onClick={() => delU.mutate(u.id)} className="text-zinc-400 hover:text-red-500" title={t('settings.delete')}><Trash2 size={15} /></button>
                {editFor === u.id && (
                  <div className="w-full flex flex-wrap gap-2 mt-1">
                    <input value={editName} onChange={e => setEditName(e.target.value)} placeholder={t('settings.name')}
                      className="flex-1 min-w-[8rem] px-3 py-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm" />
                    <input value={editEmail} onChange={e => setEditEmail(e.target.value)} placeholder={t('settings.usrEmailLogin')} type="email"
                      className="flex-1 min-w-[10rem] px-3 py-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm" />
                    <button onClick={() => { patchU.mutate({ id: u.id, body: { name: editName, email: editEmail } as any }); setEditFor(null) }}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500">{t('settings.save')}</button>
                    <p className="w-full text-[11px] text-amber-600 dark:text-amber-400">{t('settings.usrEmailWarn')}</p>
                  </div>
                )}
                {pwFor === u.id && (
                  <div className="w-full flex gap-2 mt-1">
                    <input type="text" value={pw} onChange={e => setPw(e.target.value)} placeholder={t('settings.usrNewPassword')}
                      className="flex-1 px-3 py-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    <button onClick={() => setPwM.mutate({ id: u.id, password: pw })} disabled={pw.length < 6}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50">{t('settings.usrSet')}</button>
                  </div>
                )}
                {accFor === u.id && (
                  <div className="w-full mt-2 p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">{t('settings.usrVisibleFrom')}</label>
                        <input type="date" value={acc.visible_from || ''} onChange={e => setAcc(a => ({ ...a, visible_from: e.target.value || undefined }))} className={sel + ' w-full'} />
                      </div>
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">{t('settings.usrVisibleUntil')}</label>
                        <input type="date" value={acc.visible_until || ''} onChange={e => setAcc(a => ({ ...a, visible_until: e.target.value || undefined }))} className={sel + ' w-full'} />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">{t('settings.usrIsPerson')}</label>
                      <select value={acc.person_id ?? ''} onChange={e => setAcc(a => ({ ...a, person_id: e.target.value ? Number(e.target.value) : undefined }))} className={sel + ' w-full'}>
                        <option value="">{t('settings.usrNotLinked')}</option>
                        {namedPeople.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">{t('settings.usrOnlyPersons')}</label>
                      <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto p-1 rounded-lg border border-zinc-200 dark:border-zinc-700">
                        {namedPeople.map(p => {
                          const on = (acc.visible_person_ids || []).includes(p.id)
                          return <button key={p.id} type="button" onClick={() => setAcc(a => ({ ...a, visible_person_ids: toggleIn(a.visible_person_ids, p.id) }))}
                            className={`px-2 py-0.5 rounded-full text-xs ${on ? 'bg-indigo-600 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}>{p.name}</button>
                        })}
                        {namedPeople.length === 0 && <span className="text-xs text-zinc-400">{t('settings.usrNoNamedPersons')}</span>}
                      </div>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">{t('settings.usrOnlyFolders')}</label>
                        <div className="space-y-1 max-h-28 overflow-y-auto p-1 rounded-lg border border-zinc-200 dark:border-zinc-700">
                          {sourcePaths.map(path => (
                            <label key={path} className="flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300">
                              <input type="checkbox" checked={(acc.folder_whitelist || []).includes(path)} onChange={() => setAcc(a => ({ ...a, folder_whitelist: toggleIn(a.folder_whitelist, path) }))} className="accent-indigo-500" />
                              <span className="truncate">{path}</span>
                            </label>
                          ))}
                          {sourcePaths.length === 0 && <span className="text-xs text-zinc-400">{t('settings.usrNoSources')}</span>}
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">{t('settings.usrHideFolders')}</label>
                        <div className="space-y-1 max-h-28 overflow-y-auto p-1 rounded-lg border border-zinc-200 dark:border-zinc-700">
                          {sourcePaths.map(path => (
                            <label key={path} className="flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300">
                              <input type="checkbox" checked={(acc.folder_blacklist || []).includes(path)} onChange={() => setAcc(a => ({ ...a, folder_blacklist: toggleIn(a.folder_blacklist, path) }))} className="accent-indigo-500" />
                              <span className="truncate">{path}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {([['allow_download', t('settings.download')], ['allow_map', t('settings.usrAccMap')], ['allow_pipeline', t('settings.usrAccPipeline')]] as const).map(([k, lbl]) => (
                        <label key={k} className="flex items-center gap-1.5 text-sm text-zinc-700 dark:text-zinc-300">
                          <input type="checkbox" checked={acc[k] ?? true} onChange={e => setAcc(a => ({ ...a, [k]: e.target.checked }))} className="accent-indigo-500" /> {lbl}
                        </label>
                      ))}
                    </div>
                    <div className="flex justify-end">
                      <button onClick={() => patchU.mutate({ id: u.id, body: { access_config: acc } as any })}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500">{t('settings.usrSaveAccess')}</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Add user */}
          {showAdd ? (
            <div className="p-3 rounded-xl border border-zinc-200 dark:border-zinc-700 space-y-2">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <input value={add.email} onChange={e => setAdd(a => ({ ...a, email: e.target.value }))} placeholder={t('settings.usrEmail')} className={sel + ' w-full'} />
                <input value={add.name} onChange={e => setAdd(a => ({ ...a, name: e.target.value }))} placeholder={t('settings.name')} className={sel + ' w-full'} />
                <input type="text" value={add.password} onChange={e => setAdd(a => ({ ...a, password: e.target.value }))} placeholder={t('settings.usrPasswordMin')} className={sel + ' w-full'} />
                <select value={add.role} onChange={e => setAdd(a => ({ ...a, role: e.target.value }))} className={sel + ' w-full'}>
                  <option value="user">{t('settings.usrRoleUser')}</option>
                  <option value="admin">{t('settings.usrRoleAdmin')}</option>
                </select>
              </div>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('settings.cancel')}</button>
                <button onClick={() => createU.mutate()} disabled={createU.isPending || !add.email || !add.name || add.password.length < 6}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">{t('settings.usrCreate')}</button>
              </div>
              {createU.isError && <p className="text-xs text-red-500">{t('settings.usrCreateFailed')}</p>}
            </div>
          ) : (
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
              <Plus size={15} /> {t('settings.usrAddUser')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function LogsSection() {
  const { t } = useT()
  const [feature, setFeature] = useState('all')
  const [level, setLevel] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)

  const { data = [], refetch, isLoading } = useQuery<LogEntry[]>({
    queryKey: ['logs', feature, level],
    queryFn: () => api.get(feature === 'all' ? '/logs' : `/logs/${feature}`, {
      params: { limit: 300, ...(level ? { level } : {}) }
    }).then(r => r.data),
    refetchInterval: autoRefresh ? 5000 : false,
    staleTime: 0,
  })

  const reversed = [...data].reverse()

  function exportLogs() {
    const text = data.map(e => `${e.ts} [${e.level}] (${e.feature}) ${e.message}`).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `photoflow-logs-${feature}-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <SectionHeader title={t('settings.logTitle')} desc={t('settings.logDesc')} />

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <select value={feature} onChange={e => setFeature(e.target.value)}
          className="px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none">
          <option value="all">{t('settings.logAllFeatures')}</option>
          <option value="scanner">{t('settings.logScanner')}</option>
          <option value="ai">AI</option>
          <option value="video">{t('settings.logVideo')}</option>
          <option value="faces">{t('settings.logFaces')}</option>
          <option value="remote">{t('settings.logRemote')}</option>
          <option value="system">{t('settings.logSystem')}</option>
        </select>

        <select value={level} onChange={e => setLevel(e.target.value)}
          className="px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none">
          <option value="">{t('settings.logAllLevels')}</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>

        <label className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400 cursor-pointer">
          <Toggle value={autoRefresh} onChange={setAutoRefresh} />
          {t('settings.logAutoRefresh')}
        </label>

        <div className="ml-auto flex items-center gap-2">
          <button onClick={exportLogs} disabled={data.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40">
            <Download size={13} /> {t('settings.logExport')}
          </button>
          <button onClick={() => refetch()} disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors">
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} /> {t('settings.refresh')}
          </button>
        </div>
      </div>

      {/* Log output */}
      <div className="bg-zinc-950 rounded-xl border border-zinc-800 overflow-hidden">
        <div className="px-4 py-2 border-b border-zinc-800 flex items-center gap-2">
          <Terminal size={13} className="text-zinc-500" />
          <span className="text-xs text-zinc-500">{t('settings.logEntries', { n: data.length })}</span>
          {data.length === 0 && !isLoading && (
            <span className="text-xs text-zinc-600 ml-2">{t('settings.logEmpty')}</span>
          )}
        </div>
        <div className="h-[calc(100vh-280px)] min-h-[400px] overflow-auto font-mono text-[13px] leading-relaxed p-4 space-y-0.5">
          {isLoading && <span className="text-zinc-500">{t('settings.loading')}</span>}
          {reversed.map((e, i) => (
            <div key={i} className="flex gap-3 hover:bg-white/[0.03] px-1 py-1 rounded items-start">
              <span className="text-zinc-600 shrink-0 tabular-nums">{e.ts}</span>
              <span className={`${LEVEL_COLORS[e.level] ?? 'text-zinc-400'} shrink-0 w-16`}>{e.level}</span>
              <span className="text-indigo-400/70 shrink-0 w-16">{e.feature}</span>
              <span className="text-zinc-200 flex-1 min-w-0 whitespace-pre-wrap break-words">{e.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Main ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const { t } = useT()
  const [section, setSection] = useState<SectionId>('sources')

  // Settings are global/admin (sources, API keys, providers, instance flags). A
  // restricted/demo user must not see or change them. In open mode (no login) me is
  // null → treated as admin, so single-admin use is unaffected.
  const { data: me } = useQuery<{ role: string }>({
    queryKey: ['me'], queryFn: () => api.get('/auth/me').then(r => r.data),
    retry: false, staleTime: 300_000, enabled: !!localStorage.getItem('access_token'),
  })
  const isAdmin = !me || me.role === 'admin'
  if (!isAdmin) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <div className="max-w-sm">
          <Lock size={32} className="mx-auto text-zinc-400 mb-3" />
          <h2 className="text-base font-semibold text-zinc-800 dark:text-zinc-200">{t('settings.adminOnlyTitle')}</h2>
          <p className="text-sm text-zinc-500 mt-1">{t('settings.adminOnlyDesc')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <nav className="w-48 shrink-0 border-r border-zinc-200 dark:border-zinc-800 py-4 space-y-0.5 px-2">
        {SECTIONS.map(({ id, icon: Icon, navKey }) => (
          <button key={id} onClick={() => setSection(id)}
            className={`w-full flex items-center gap-2.5 text-left px-3 py-2 rounded-lg text-sm transition-colors ${
              section === id
                ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 font-medium'
                : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
            }`}
          >
            <Icon size={15} />
            {t(`settings.${navKey}`)}
          </button>
        ))}
      </nav>

      {/* Content — full width (sections cap their own width where it helps readability) */}
      <div className="flex-1 overflow-auto p-6">
        {section === 'sources'  && <SourcesSection />}
        {section === 'gallery'  && <GallerySection />}
        {section === 'features' && <FeaturesSection />}
        {section === 'ai'       && <AISection />}
        {section === 'chat'     && <ChatSettingsSection />}
        {section === 'video-ai' && <VideoAISection />}
        {section === 'faces'    && <FacesSection />}
        {section === 'memories' && <MemoriesSettingsSection />}
        {section === 'highlights' && <HighlightsAISettings />}
        {section === 'trips'    && <TripsSection />}
        {section === 'sharing'  && <SharingSection />}
        {section === 'pipeline' && <PipelineSection />}
        {section === 'remote'   && <RemoteWorkerSection />}
        {section === 'backup'   && <BackupSection />}
        {section === 'map'      && <MapSection />}
        {section === 'users'    && <UsersSection />}
        {section === 'logs'     && <LogsSection />}
      </div>
    </div>
  )
}

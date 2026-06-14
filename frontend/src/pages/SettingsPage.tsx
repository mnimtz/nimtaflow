import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Trash2, RefreshCw, Check, X, FolderOpen,
  Cpu, Layers, Cog, Map, HardDrive, Video, Terminal,
  Loader2, CircleCheck, CircleX,
  Eye, Zap, Brain, Download,
} from 'lucide-react'
import { api, type Source } from '../lib/api'
import FolderBrowser from '../components/ui/FolderBrowser'

// ─── Types ──────────────────────────────────────────────────────────────────

type ModelInfo = {
  id: string
  name: string
  description?: string
  supports_vision: boolean
  supports_embedding: boolean
}

type Settings = Record<string, string>

// ─── Layout helpers ──────────────────────────────────────────────────────────

const SECTIONS = [
  { id: 'sources',   icon: HardDrive, label: 'Foto-Quellen' },
  { id: 'gallery',   icon: Layers,    label: 'Galerie' },
  { id: 'ai',        icon: Brain,     label: 'Foto-AI' },
  { id: 'video-ai',  icon: Video,     label: 'Video-AI & Gesichter' },
  { id: 'pipeline',  icon: Cog,       label: 'Pipeline' },
  { id: 'backup',    icon: HardDrive, label: 'Backup' },
  { id: 'map',       icon: Map,       label: 'Karte' },
  { id: 'logs',      icon: Terminal,  label: 'Logs' },
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
  return (
    <button
      onClick={onClick}
      disabled={pending}
      className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
    >
      {pending ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : null}
      {saved ? 'Gespeichert' : 'Speichern'}
    </button>
  )
}

// ─── Model Select ─────────────────────────────────────────────────────────────

function ModelSelect({
  label, value, onChange, models, loading, filter,
  placeholder = 'Modell eingeben oder aus Liste wählen',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  models: ModelInfo[]
  loading: boolean
  filter?: (m: ModelInfo) => boolean
  placeholder?: string
}) {
  const filtered = filter ? models.filter(filter) : models
  return (
    <div>
      <Label>{label}</Label>
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-zinc-400 py-2">
          <Loader2 size={13} className="animate-spin" /> Lade Modelle...
        </div>
      ) : filtered.length > 0 ? (
        <select
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">— auswählen —</option>
          {filtered.map(m => (
            <option key={m.id} value={m.id}>
              {m.name}{m.description ? ` (${m.description})` : ''}
            </option>
          ))}
        </select>
      ) : (
        <Input value={value} onChange={onChange} placeholder={placeholder} />
      )}
    </div>
  )
}

// ─── Provider health badge ────────────────────────────────────────────────────

function HealthBadge({ provider, apiKey, baseUrl }: { provider: string; apiKey?: string; baseUrl?: string }) {
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
        Verbindung testen
      </button>
      {data && (
        data.ok
          ? <span className="flex items-center gap-1 text-xs text-emerald-400"><CircleCheck size={11} />Erreichbar</span>
          : <span className="flex items-center gap-1 text-xs text-red-400"><CircleX size={11} />{data.error ?? 'Fehler'}</span>
      )}
    </div>
  )
}

// ─── Sections ─────────────────────────────────────────────────────────────────

function SourcesSection() {
  const [newPath, setNewPath] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const [scanningIds, setScanningIds] = useState<Set<number>>(new Set())
  const qc = useQueryClient()

  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ['sources'],
    queryFn: () => api.get('/sources').then(r => r.data),
    refetchInterval: 5000, // live-update scan status
  })

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

  const INTERVALS: { label: string; value: number }[] = [
    { label: 'Manuell (kein Auto-Scan)', value: 0 },
    { label: 'Alle 15 Minuten', value: 15 },
    { label: 'Alle 30 Minuten', value: 30 },
    { label: 'Stündlich', value: 60 },
    { label: 'Alle 6 Stunden', value: 360 },
    { label: 'Täglich', value: 1440 },
  ]

  return (
    <div>
      <SectionHeader title="Foto-Quellen" desc="Ordner die PhotoFlow überwachen soll. Scan + Verarbeitung starten automatisch." />

      <div className="space-y-2 mb-5">
        {sources.length === 0 && (
          <p className="text-sm text-zinc-500 dark:text-zinc-400 py-2">Noch keine Quellen. Ordner unten hinzufügen.</p>
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
                      ? '⏳ Scannt und verarbeitet Fotos…'
                      : s.last_scan_at
                        ? `Letzter Scan: ${new Date(s.last_scan_at).toLocaleString('de')} · ${s.last_scan_count ?? 0} neue Fotos`
                        : 'Noch nicht gescannt'}
                  </p>
                </div>
                <button
                  onClick={() => scan.mutate(s.id)}
                  disabled={isScanning}
                  title="Erneut scannen"
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors disabled:opacity-40"
                >
                  <RefreshCw size={14} className={isScanning ? 'animate-spin' : ''} />
                </button>
                <button
                  onClick={() => { if (confirm(`Ordner „${s.path}" entfernen?\n\nAlle daraus indizierten Fotos, Thumbnails, Vorschauen und Gesichter werden aus PhotoFlow gelöscht. Die Originaldateien auf der Festplatte bleiben unberührt.`)) del.mutate(s.id) }}
                  className="p-1.5 rounded-lg text-zinc-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {/* Watch / interval controls */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700/60">
                <div className="flex items-center gap-2">
                  <Eye size={13} className={watching ? 'text-indigo-500' : 'text-zinc-400'} />
                  <label className="text-xs text-zinc-500 dark:text-zinc-400">Überwachung:</label>
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
                  Gelöschte Dateien erkennen
                </label>
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
              placeholder="/photos  oder  /photos/2024"
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
            Hinzufügen
          </button>
        </div>
        <p className="text-xs text-zinc-400">
          Nach dem Hinzufügen startet der Scan automatisch. Mehrere Ordner können einzeln hinzugefügt werden.
        </p>
      </form>

      {showBrowser && (
        <FolderBrowser initialPath={newPath || '/photos'} onSelect={p => setNewPath(p)} onClose={() => setShowBrowser(false)} />
      )}
    </div>
  )
}

function GallerySection() {
  const [rowHeight, setRowHeight] = useState(200)
  const [autoplay, setAutoplay] = useState(true)
  const [faceBoxes, setFaceBoxes] = useState(true)
  const [defaultView, setDefaultView] = useState('grid')
  const [saved, setSaved] = useState(false)

  return (
    <div>
      <SectionHeader title="Galerie" desc="Anzeige, Thumbnails und Video-Verhalten anpassen." />
      <div className="space-y-6">
        <div>
          <Label>Standard-Ansicht</Label>
          <select value={defaultView} onChange={e => setDefaultView(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="grid">Raster (Justified Grid)</option>
            <option value="timeline">Timeline</option>
            <option value="memories">Erinnerungen</option>
          </select>
        </div>

        <div>
          <Label>Zeilenhöhe: {rowHeight}px</Label>
          <input type="range" min={120} max={400} step={20} value={rowHeight}
            onChange={e => setRowHeight(Number(e.target.value))} className="w-full accent-indigo-500" />
          <div className="flex justify-between text-xs text-zinc-400 mt-0.5">
            <span>Kompakt (120px)</span><span>Groß (400px)</span>
          </div>
        </div>

        <div className="space-y-4">
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">Videos automatisch abspielen</p>
              <p className="text-xs text-zinc-400 mt-0.5">Video startet beim Öffnen im Lightbox</p>
            </div>
            <Toggle value={autoplay} onChange={setAutoplay} />
          </label>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">Gesichtsrahmen anzeigen</p>
              <p className="text-xs text-zinc-400 mt-0.5">Erkannte Gesichter im Lightbox hervorheben</p>
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
      <SectionHeader title="Foto-AI" desc={'AI nur für Fotos: Bildbeschreibungen, Tags und Embeddings. Videos werden separat unter „Video-AI & Gesichter“ konfiguriert.'} />
      <div className="space-y-7">

        {/* Provider picker */}
        <div>
          <Label>Aktiver Provider</Label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {([
              { id: 'none', label: 'Kein AI', sub: 'Nur EXIF' },
              { id: 'gemini', label: 'Gemini', sub: 'Google' },
              { id: 'openai', label: 'OpenAI', sub: 'GPT-4o' },
              { id: 'azure', label: 'Azure', sub: 'Copilot/OAI' },
              { id: 'ollama', label: 'Ollama', sub: 'Lokal' },
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
              <Label>API Key</Label>
              <Input value={settings['ai.gemini.api_key'] ?? ''} onChange={v => set('ai.gemini.api_key', v)} type="password" placeholder="AIza..." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label="Vision-Modell"
                value={settings['ai.gemini.model'] ?? ''}
                onChange={v => set('ai.gemini.model', v)}
                models={geminiModels.data ?? []}
                loading={geminiModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="gemini-2.5-flash"
              />
              <ModelSelect
                label="Embedding-Modell"
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
              <Label>API Key</Label>
              <Input value={settings['ai.openai.api_key'] ?? ''} onChange={v => set('ai.openai.api_key', v)} type="password" placeholder="sk-..." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label="Vision-Modell"
                value={settings['ai.openai.model'] ?? ''}
                onChange={v => set('ai.openai.model', v)}
                models={openaiModels.data ?? []}
                loading={openaiModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="gpt-4o"
              />
              <ModelSelect
                label="Embedding-Modell"
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
              <Label>API Key</Label>
              <Input value={settings['ai.openai.api_key'] ?? ''} onChange={v => set('ai.openai.api_key', v)} type="password" placeholder="Azure-Key..." />
            </div>
            <div>
              <Label>Endpoint URL</Label>
              <Input
                value={settings['ai.openai.base_url'] ?? ''}
                onChange={v => set('ai.openai.base_url', v)}
                placeholder="https://your-resource.openai.azure.com/openai/v1"
              />
              <p className="text-[11px] text-zinc-400 mt-1">Format: https://&lt;resource&gt;.openai.azure.com/openai/v1</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label="Vision-Deployment"
                value={settings['ai.openai.model'] ?? ''}
                onChange={v => set('ai.openai.model', v)}
                models={openaiModels.data ?? []}
                loading={openaiModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="gpt-4o"
              />
              <ModelSelect
                label="Embedding-Deployment"
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
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Ollama (lokal)</p>
            <div>
              <Label>Ollama URL</Label>
              <Input value={settings['ai.ollama.url'] ?? ''} onChange={v => set('ai.ollama.url', v)} placeholder="http://your-host:11434" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <ModelSelect
                label="Vision-Modell"
                value={settings['ai.ollama.vision_model'] ?? ''}
                onChange={v => set('ai.ollama.vision_model', v)}
                models={ollamaModels.data ?? []}
                loading={ollamaModels.isLoading}
                filter={m => m.supports_vision}
                placeholder="llava:7b oder moondream"
              />
              <ModelSelect
                label="Embedding-Modell"
                value={settings['ai.ollama.embed_model'] ?? ''}
                onChange={v => set('ai.ollama.embed_model', v)}
                models={ollamaModels.data ?? []}
                loading={ollamaModels.isLoading}
                filter={m => m.supports_embedding}
                placeholder="nomic-embed-text"
              />
            </div>
            {ollamaModels.data?.length === 0 && !ollamaModels.isLoading && (
              <p className="text-xs text-amber-400">Keine Modelle gefunden — läuft Ollama unter der angegebenen URL?</p>
            )}
            <HealthBadge provider="ollama" baseUrl={settings['ai.ollama.url']} />
          </div>
        )}

        {/* Language */}
        <div>
          <Label>Sprache für Beschreibungen</Label>
          <select value={settings['ai.language'] ?? 'de'} onChange={e => set('ai.language', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="de">Deutsch</option>
            <option value="en">Englisch</option>
            <option value="fr">Französisch</option>
            <option value="es">Spanisch</option>
          </select>
        </div>

        {/* XMP auto-write */}
        <label className="flex items-start justify-between gap-4 p-3 rounded-xl border border-zinc-200 dark:border-zinc-700 cursor-pointer">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">AI-Beschreibung automatisch in XMP schreiben</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              Legt eine <code>.xmp</code>-Sidecar-Datei neben das Original mit <code>dc:description</code> + Schlagwörtern.
              Originale bleiben unverändert. Praktisch für Lightroom/digiKam/Immich-Export.
            </p>
          </div>
          <Toggle
            value={String(settings['xmp.auto_write'] ?? '').toLowerCase() === 'true'}
            onChange={v => set('xmp.auto_write', v ? 'true' : 'false')}
          />
        </label>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

function VideoAISection() {
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
      <SectionHeader title="Video-AI & Gesichtserkennung" desc="Separate AI-Konfiguration für Video-Analyse und Gesichtserkennung in Videos." />
      <div className="space-y-7">

        {/* Video AI provider */}
        <div>
          <Label>Video-AI Provider</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {([
              { id: 'same', label: 'Wie Fotos', sub: 'Gleicher Provider' },
              { id: 'ollama', label: 'Ollama', sub: 'Lokal / privat' },
              { id: 'gemini', label: 'Gemini', sub: 'Google Video AI' },
              { id: 'moondream', label: 'Moondream', sub: 'Eingebaut (klein, schnell)' },
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
        </div>

        {vidProvider === 'ollama' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Ollama für Videos</p>
            <div>
              <Label>Ollama URL</Label>
              <Input value={settings['video.ollama_url'] ?? ollamaUrl} onChange={v => set('video.ollama_url', v)} placeholder="http://your-host:11434" />
            </div>
            <ModelSelect
              label="Vision-Modell"
              value={settings['video.ollama_model'] ?? ''}
              onChange={v => set('video.ollama_model', v)}
              models={ollamaModels.data ?? []}
              loading={ollamaModels.isLoading}
              filter={m => m.supports_vision}
              placeholder="moondream:latest oder llava"
            />
          </div>
        )}

        {vidProvider === 'moondream' && (
          <div className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">Moondream (eingebaut)</p>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              Moondream 2 (~1.7GB) läuft direkt im Backend — kein externer Dienst nötig.
              Beim ersten Start wird das Modell automatisch heruntergeladen.
            </p>
            <div className="mt-3">
              <Label>Modell-Variante</Label>
              <select value={settings['video.moondream_model'] ?? 'moondream2'} onChange={e => set('video.moondream_model', e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="moondream2">Moondream 2 (Standard)</option>
                <option value="moondream2-int4">Moondream 2 INT4 (kleiner)</option>
              </select>
            </div>
          </div>
        )}

        {/* Face recognition in videos */}
        <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide flex items-center gap-2">
            <Eye size={12} /> Gesichtserkennung in Videos
          </p>
          <div className="space-y-3">
            <label className="flex items-center justify-between">
              <div>
                <p className="text-sm text-zinc-700 dark:text-zinc-300">Gesichtserkennung in Videos aktivieren</p>
                <p className="text-xs text-zinc-400">Frames werden extrahiert und analysiert (langsamer)</p>
              </div>
              <Toggle
                value={(settings['video.face_recognition'] ?? 'false') === 'true'}
                onChange={v => set('video.face_recognition', v ? 'true' : 'false')}
              />
            </label>

            <div>
              <Label>Frame-Intervall (Sekunden)</Label>
              <Input value={settings['video.face_interval_sec'] ?? '5'}
                onChange={v => set('video.face_interval_sec', v)} placeholder="5" />
              <p className="text-[11px] text-zinc-400 mt-1">Alle N Sekunden ein Frame für Gesichtserkennung extrahieren</p>
            </div>

            <div>
              <Label>Max. Frames pro Video</Label>
              <Input value={settings['video.max_frames'] ?? '30'}
                onChange={v => set('video.max_frames', v)} placeholder="30" />
            </div>
          </div>
        </div>

        {/* Video transcoding */}
        <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Transkodierung (WebM/VP9)</p>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">Automatisch transkodieren</p>
              <p className="text-xs text-zinc-400">Videos automatisch in WebM konvertieren (breitere Browser-Kompatibilität)</p>
            </div>
            <Toggle
              value={(settings['video.auto_transcode'] ?? 'false') === 'true'}
              onChange={v => set('video.auto_transcode', v ? 'true' : 'false')}
            />
          </label>
          <div>
            <Label>Max. Auflösung</Label>
            <select value={settings['video.transcode_resolution'] ?? '720'} onChange={e => set('video.transcode_resolution', e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="480">480p</option>
              <option value="720">720p (empfohlen)</option>
              <option value="1080">1080p</option>
              <option value="original">Original</option>
            </select>
          </div>
        </div>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

function PipelineSection() {
  return (
    <div>
      <SectionHeader title="Pipeline" desc="Batch-Verarbeitung, Parallelität und automatischer Scan-Zeitplan." />
      <p className="text-sm text-zinc-400">Kommt bald.</p>
    </div>
  )
}

type BackupFile = { name: string; size_mb: number; created_at: string; type: string }
type HWInfo = { name: string; available: boolean; info: string; encode_h264_codec: string }

function BackupSection() {
  const [rcloneRemote, setRcloneRemote] = useState('')
  const [keepDays, setKeepDays] = useState(30)
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
    mutationFn: () => api.post('/backup/run', null, { params: { rclone_remote: rcloneRemote } }),
    onSuccess: () => { refetch() },
  })

  const prune = useMutation({
    mutationFn: () => api.delete('/backup/prune', { params: { keep_days: keepDays } }),
    onSuccess: () => refetch(),
  })

  const hwColor = !hw ? 'text-zinc-400'
    : hw.name === 'cuda' ? 'text-green-400'
    : hw.name === 'qsv' ? 'text-blue-400'
    : hw.name === 'vaapi' ? 'text-sky-400'
    : 'text-zinc-400'

  return (
    <div>
      <SectionHeader title="Backup & Hardware" desc="Datenbank-Sicherung, Offsiste-Sync und Hardware-Beschleunigung." />

      {/* HW acceleration status */}
      <div className="mb-6 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2 flex items-center gap-2">
          <Cpu size={12} /> Hardware-Beschleunigung
        </p>
        {hw ? (
          <div className="flex items-center gap-3">
            <div className={`text-sm font-medium ${hwColor}`}>
              {hw.name === 'cuda' ? 'NVIDIA CUDA / NVENC' :
               hw.name === 'qsv' ? 'Intel Quick Sync' :
               hw.name === 'vaapi' ? 'VAAPI' :
               hw.name === 'videotoolbox' ? 'Apple VideoToolbox' :
               'Software (libx264/libvpx-vp9)'}
            </div>
            <span className="text-xs text-zinc-400">{hw.info}</span>
          </div>
        ) : (
          <p className="text-sm text-zinc-400">Erkenne Hardware...</p>
        )}
        <p className="text-xs text-zinc-500 mt-1">Encoder: <code className="text-indigo-400">{hw?.encode_h264_codec ?? '...'}</code></p>
      </div>

      {/* Backup list */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Gespeicherte Backups</p>
          <button onClick={() => refetch()} className="text-xs text-zinc-400 hover:text-zinc-200 flex items-center gap-1">
            <RefreshCw size={11} /> Aktualisieren
          </button>
        </div>
        {backups.length === 0 && (
          <p className="text-sm text-zinc-400">Noch keine Backups erstellt.</p>
        )}
        <div className="space-y-2">
          {backups.map(b => (
            <div key={b.name} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-sm">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${b.type === 'db' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-zinc-500/20 text-zinc-400'}`}>
                {b.type.toUpperCase()}
              </span>
              <span className="flex-1 font-mono text-xs text-zinc-600 dark:text-zinc-400 truncate">{b.name}</span>
              <span className="text-zinc-400 text-xs">{b.size_mb} MB</span>
              <a href={`/api/backup/download/${b.name}`} download
                className="text-indigo-400 hover:text-indigo-300 text-xs transition-colors">Download</a>
            </div>
          ))}
        </div>
      </div>

      {/* Run backup */}
      <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Backup erstellen</p>
        <div>
          <Label>Rclone Remote (optional)</Label>
          <Input value={rcloneRemote} onChange={setRcloneRemote} placeholder="b2:my-bucket/photoflow oder gdrive:backup" />
          <p className="text-[11px] text-zinc-400 mt-1">Leer lassen = nur lokal. rclone muss auf dem Server konfiguriert sein.</p>
        </div>
        <button
          onClick={() => runBackup.mutate()}
          disabled={runBackup.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
        >
          {runBackup.isPending ? <Loader2 size={14} className="animate-spin" /> : <HardDrive size={14} />}
          Backup jetzt starten
        </button>
        {runBackup.isSuccess && (
          <p className="text-xs text-emerald-400 flex items-center gap-1"><CircleCheck size={12} /> Backup erfolgreich!</p>
        )}
      </div>

      {/* Prune */}
      <div className="mt-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">Alte Backups löschen</p>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <Label>Aufbewahrung (Tage): {keepDays}</Label>
            <input type="range" min={7} max={365} step={7} value={keepDays} onChange={e => setKeepDays(Number(e.target.value))}
              className="w-full accent-indigo-500" />
          </div>
          <button onClick={() => prune.mutate()} disabled={prune.isPending}
            className="px-3 py-2 rounded-lg text-sm bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors shrink-0">
            Bereinigen
          </button>
        </div>
      </div>
    </div>
  )
}

function MapSection() {
  return (
    <div>
      <SectionHeader title="Karten-Provider" desc="Wähle den Kartendienst für die Weltkarte." />
      <p className="text-sm text-zinc-400">Kommt bald.</p>
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

function LogsSection() {
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
      <SectionHeader title="Feature-Logs" desc="Detaillierte Logs pro Funktion für Diagnose und Fehlersuche." />

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap mb-4">
        <select value={feature} onChange={e => setFeature(e.target.value)}
          className="px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none">
          <option value="all">Alle Features</option>
          <option value="scanner">Scanner</option>
          <option value="ai">AI</option>
          <option value="video">Video</option>
          <option value="faces">Gesichter</option>
          <option value="system">System</option>
        </select>

        <select value={level} onChange={e => setLevel(e.target.value)}
          className="px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none">
          <option value="">Alle Level</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>

        <label className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400 cursor-pointer">
          <Toggle value={autoRefresh} onChange={setAutoRefresh} />
          Auto-Refresh (5s)
        </label>

        <div className="ml-auto flex items-center gap-2">
          <button onClick={exportLogs} disabled={data.length === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors disabled:opacity-40">
            <Download size={13} /> Export
          </button>
          <button onClick={() => refetch()} disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors">
            <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} /> Aktualisieren
          </button>
        </div>
      </div>

      {/* Log output */}
      <div className="bg-zinc-950 rounded-xl border border-zinc-800 overflow-hidden">
        <div className="px-4 py-2 border-b border-zinc-800 flex items-center gap-2">
          <Terminal size={13} className="text-zinc-500" />
          <span className="text-xs text-zinc-500">{data.length} Einträge</span>
          {data.length === 0 && !isLoading && (
            <span className="text-xs text-zinc-600 ml-2">— Noch keine Logs. Log-Dateien entstehen beim ersten Scan/AI-Lauf.</span>
          )}
        </div>
        <div className="h-[calc(100vh-280px)] min-h-[400px] overflow-auto font-mono text-[13px] leading-relaxed p-4 space-y-0.5">
          {isLoading && <span className="text-zinc-500">Lade...</span>}
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
  const [section, setSection] = useState<SectionId>('sources')

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <nav className="w-48 shrink-0 border-r border-zinc-200 dark:border-zinc-800 py-4 space-y-0.5 px-2">
        {SECTIONS.map(({ id, icon: Icon, label }) => (
          <button key={id} onClick={() => setSection(id)}
            className={`w-full flex items-center gap-2.5 text-left px-3 py-2 rounded-lg text-sm transition-colors ${
              section === id
                ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400 font-medium'
                : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
            }`}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </nav>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6 max-w-2xl">
        {section === 'sources'  && <SourcesSection />}
        {section === 'gallery'  && <GallerySection />}
        {section === 'ai'       && <AISection />}
        {section === 'video-ai' && <VideoAISection />}
        {section === 'pipeline' && <PipelineSection />}
        {section === 'backup'   && <BackupSection />}
        {section === 'map'      && <MapSection />}
        {section === 'logs'     && <LogsSection />}
      </div>
    </div>
  )
}

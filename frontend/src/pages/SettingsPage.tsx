import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, Trash2, RefreshCw, Check, X, FolderOpen,
  Cpu, Layers, Cog, Map, HardDrive, Video, Terminal,
  Loader2, CircleCheck, CircleX,
  Eye, Zap, Brain, Download, Shield, Lock, KeyRound, Network, Clock,
  MessageCircle, Image as ImageIcon,
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

const DEFAULT_IMAGE_PROMPT = 'Beschreibe dieses Foto sachlich in 2-3 Sätzen auf Deutsch. Nenne Personen, Ort, Aktivität und Stimmung.'
const DEFAULT_VIDEO_PROMPT = 'Beschreibe diese Videoszene sachlich in 2-3 Sätzen auf Deutsch. Nenne Personen, Ort, Aktivität und Stimmung.'
const DEFAULT_TAGS_PROMPT = 'Nenne 5–12 prägnante Schlagwörter (Substantive) zu diesem Bild, kommagetrennt, ohne Sätze, ohne Füllwörter. Beispiel: Strand, Sonnenuntergang, Boot, Meer.'

// ─── Layout helpers ──────────────────────────────────────────────────────────

const SECTIONS = [
  { id: 'sources',   icon: HardDrive, label: 'Foto-Quellen' },
  { id: 'gallery',   icon: Layers,    label: 'Galerie' },
  { id: 'features',  icon: Network,   label: 'Funktionen' },
  { id: 'ai',        icon: Brain,     label: 'Bilder-AI' },
  { id: 'chat',      icon: MessageCircle, label: 'Chat-Assistent' },
  { id: 'video-ai',  icon: Video,     label: 'Video-AI' },
  { id: 'faces',     icon: Eye,       label: 'Personen & Gesichter' },
  { id: 'memories',  icon: Clock,     label: 'Erinnerungen' },
  { id: 'pipeline',  icon: Cog,       label: 'Pipeline' },
  { id: 'remote',    icon: Network,   label: 'Remote-Worker' },
  { id: 'backup',    icon: HardDrive, label: 'Backup' },
  { id: 'map',       icon: Map,       label: 'Karte' },
  { id: 'users',     icon: Shield,    label: 'Benutzer & Login' },
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

  const reprocess = useMutation({
    mutationFn: ({ id, redoFaces }: { id: number; redoFaces: boolean }) =>
      api.post(`/sources/${id}/reprocess`, null, { params: { redo_faces: redoFaces } }).then(r => r.data),
    onSuccess: (d: { reprocessing: number }) => alert(`${d.reprocessing} Dateien werden neu verarbeitet (Thumbnails + AI${'' }).`),
  })

  const reprocessFailed = useMutation({
    mutationFn: () => api.post('/photos/reprocess-failed').then(r => r.data),
    onSuccess: (d: { reprocessing: number }) => alert(`${d.reprocessing} fehlerhafte/unfertige Dateien werden erneut verarbeitet.`),
  })

  const [verifyResult, setVerifyResult] = useState<string | null>(null)
  const verify = useMutation({
    mutationFn: () => api.post('/sources/verify').then(r => r.data),
    onSuccess: (d: { checked: number; removed_photos: number; removed_files: number }) => {
      setVerifyResult(`${d.checked} Einträge geprüft · ${d.removed_photos} verwaiste entfernt · ${d.removed_files} Dateien gelöscht`)
      qc.invalidateQueries({ queryKey: ['photos'] })
      qc.invalidateQueries({ queryKey: ['photo-stats'] })
      qc.invalidateQueries({ queryKey: ['people'] })
      qc.invalidateQueries({ queryKey: ['memories'] })
    },
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
                <div className="flex items-center gap-2">
                  <label className="text-xs text-zinc-500 dark:text-zinc-400">KI:</label>
                  <select
                    value={s.ai_provider ?? ''}
                    onChange={e => patch.mutate({ id: s.id, ai_provider: (e.target.value || null) } as any)}
                    title="Welche KI für diesen Ordner genutzt wird"
                    className="text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="">Global (Standard)</option>
                    <option value="gemini">Gemini (Cloud)</option>
                    <option value="local">Embedded (lokal)</option>
                    <option value="ollama">Ollama</option>
                    <option value="off">Keine KI</option>
                  </select>
                </div>
                <button
                  onClick={() => { if (confirm('Alle Dateien dieses Ordners neu verarbeiten (Thumbnails + AI + Gesichter)?')) reprocess.mutate({ id: s.id, redoFaces: true }) }}
                  className="ml-auto text-xs text-indigo-500 hover:underline"
                >
                  ↻ Neu verarbeiten
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

      {/* Library maintenance */}
      <div className="mt-6 pt-5 border-t border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Bilddatenbank überprüfen</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              Gleicht alle Einträge mit der Festplatte ab und entfernt verwaiste Fotos, Thumbnails, Vorschauen
              und Gesichter von Dateien/Ordnern, die es nicht mehr gibt.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => reprocessFailed.mutate()}
              disabled={reprocessFailed.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-sm font-medium disabled:opacity-50 transition-colors"
              title="Fehlerhafte oder unfertige Dateien erneut verarbeiten"
            >
              <RefreshCw size={14} className={reprocessFailed.isPending ? 'animate-spin' : ''} /> Fehler erneut
            </button>
            <button
              onClick={() => { if (confirm('Bibliothek überprüfen und verwaiste Einträge (gelöschte Dateien) entfernen?')) { setVerifyResult(null); verify.mutate() } }}
              disabled={verify.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 text-sm font-medium disabled:opacity-50 transition-colors"
            >
              <RefreshCw size={14} className={verify.isPending ? 'animate-spin' : ''} /> Jetzt überprüfen
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
              { id: 'local', label: 'Integriert', sub: 'Lokal, eingebaut' },
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

        {/* Integrated local model */}
        {provider === 'local' && (
          <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-800/30">
            <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Integriertes Modell (läuft lokal, kein Ollama/Cloud)</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {([
                { id: 'florence2-base', label: 'Optimum — Florence-2-base', sub: '~0.7 GB · schnell · läuft in 4 GB' },
                { id: 'qwen2.5-vl-3b', label: 'Best — Qwen2.5-VL-3B', sub: '~7 GB · multilingual · braucht ~12 GB RAM' },
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
              Das Modell wird beim ersten Lauf einmalig heruntergeladen (in den Modell-Cache) und danach lokal ausgeführt.
              Florence-2 liefert englische Captions, die für Deutsch lokal übersetzt werden; Qwen schreibt direkt Deutsch.
            </p>
          </div>
        )}

        {/* Description prompt */}
        <div>
          <Label>Prompt für Bildbeschreibung</Label>
          <textarea
            value={settings['ai.prompt.image'] ?? DEFAULT_IMAGE_PROMPT}
            onChange={e => set('ai.prompt.image', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          />
          <div className="flex justify-between items-center mt-1">
            <p className="text-[11px] text-zinc-400">Geht an Gemini/OpenAI/Ollama/Qwen. (Florence-2 nutzt feste Tasks.)</p>
            <button type="button" onClick={() => set('ai.prompt.image', DEFAULT_IMAGE_PROMPT)}
              className="text-[11px] text-indigo-500 hover:underline">Standard</button>
          </div>
        </div>

        {/* Tags prompt (optional) */}
        <div>
          <Label>Prompt für Schlagwörter / Tags (optional)</Label>
          <textarea
            value={settings['ai.prompt.tags'] ?? ''}
            onChange={e => set('ai.prompt.tags', e.target.value)}
            rows={2}
            placeholder={'Leer lassen = Tags aus der Beschreibung (schnell). Beispiel: ' + DEFAULT_TAGS_PROMPT}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          />
          <div className="flex justify-between items-center mt-1">
            <p className="text-[11px] text-zinc-400">
              Leer = Tags aus der Beschreibung (kostenlos). Gesetzt = der VLM erzeugt echte Schlagwörter per
              eigenem Durchlauf — <b>verdoppelt die GPU-Zeit pro Foto</b>. (Qwen/Gemini/Ollama; Florence ignoriert.)
            </p>
            <button type="button" onClick={() => set('ai.prompt.tags', DEFAULT_TAGS_PROMPT)}
              className="text-[11px] text-indigo-500 hover:underline whitespace-nowrap ml-2">Vorlage</button>
          </div>
        </div>

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

        {/* Search accuracy */}
        <div>
          <Label>Such-Genauigkeit (max. Distanz: {settings['search.max_distance'] ?? '0.78'})</Label>
          <input type="range" min={0.4} max={1.2} step={0.02}
            value={Number(settings['search.max_distance'] ?? 0.78)}
            onChange={e => set('search.max_distance', e.target.value)}
            className="w-full accent-indigo-500" />
          <div className="flex justify-between text-[11px] text-zinc-400 mt-0.5">
            <span>streng / exakt</span><span>locker / mehr Treffer</span>
          </div>
        </div>

        {/* AI metadata write-back */}
        <div className="p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <Label>AI-Beschreibung & Tags zurückschreiben</Label>
          <select
            value={settings['xmp.write_mode'] ?? 'off'}
            onChange={e => set('xmp.write_mode', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="off">Nur in die PhotoFlow-DB</option>
            <option value="file">DB + ins Bild (EXIF/IPTC/XMP eingebettet)</option>
            <option value="file_sidecar">DB + ins Bild + .xmp-Sidecar</option>
            <option value="sidecar">DB + .xmp-Sidecar (Original unberührt)</option>
          </select>
          <p className="text-xs text-zinc-400 mt-1.5">
            Schreibt <code>dc:description</code>/<code>IPTC:Caption</code> + Schlagwörter.
            „Ins Bild" verändert die Originaldatei (mit Backup bei der ersten Änderung), „Sidecar" legt eine
            <code>.xmp</code> daneben. Kompatibel mit Lightroom, digiKam, Immich.
          </p>
          <BackfillXmpButton />
        </div>

        {/* Re-use existing file metadata on scan */}
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">KI trotz vorhandener Metadaten neu erkennen</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              Standard AUS: Hat eine Datei bereits eine Beschreibung (eingebettetes XMP oder <code>.xmp</code>-Sidecar),
              wird sie beim Scan <strong>übernommen</strong> und die KI übersprungen (schnell, spart GPU — z. B. nach
              Re-Import/Wiederherstellung). AN = immer neu mit KI beschreiben.
            </p>
          </div>
          <Toggle value={(settings['scan.force_reindex'] ?? 'false') === 'true'} onChange={v => set('scan.force_reindex', v ? 'true' : 'false')} />
        </label>

        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">Gesichter auch bei importierten Metadaten erkennen</p>
            <p className="text-xs text-zinc-400 mt-0.5">
              Standard AN: Gesichter stehen <strong>nicht</strong> in den Dateimetadaten — auch wenn Beschreibung/Tags
              übernommen wurden, läuft eine reine Gesichtserkennung (ohne erneute KI-Beschreibung). AUS = importierte
              Fotos ganz ohne KI/Gesichter.
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
  const [msg, setMsg] = useState('')
  const m = useMutation({
    mutationFn: () => api.post('/photos/backfill-xmp').then(r => r.data),
    onSuccess: (d: any) => setMsg(`Läuft im Hintergrund für ${d.described_photos} beschriebene Fotos — Fortschritt im AI-Log.`),
    onError: () => setMsg('Fehler beim Starten.'),
  })
  return (
    <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
      <button onClick={() => m.mutate()} disabled={m.isPending}
        className="px-3 py-2 rounded-lg border border-indigo-300 dark:border-indigo-700 text-sm text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 disabled:opacity-50">
        {m.isPending ? 'Startet …' : 'Vorhandene Beschreibungen jetzt in die Dateien schreiben'}
      </button>
      <p className="text-[11px] text-zinc-400 mt-1.5">
        Einmaliger Nachtrag: schreibt bereits erzeugte Beschreibungen + Tags aus der DB in die Bilddateien
        (nötig für Fotos, die der Remote-Worker verarbeitet hat, bevor das Datei-Schreiben aktiv war).
      </p>
      {msg && <p className="text-[11px] text-emerald-500 mt-1">{msg}</p>}
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
      <SectionHeader title="Video-AI" desc="Separate AI-Konfiguration für Video-Analyse. Gesichter werden unter „Personen & Gesichter“ konfiguriert." />
      <div className="space-y-7">

        {/* Video AI provider */}
        <div>
          <Label>Video-AI Provider</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {([
              { id: 'same', label: 'Wie Fotos', sub: 'Gleicher Provider' },
              { id: 'local', label: 'Integriert', sub: 'Lokal, eingebaut' },
              { id: 'ollama', label: 'Ollama', sub: 'Lokal / privat' },
              { id: 'gemini', label: 'Gemini', sub: 'Google Video AI' },
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
                { id: 'florence2-base', label: 'Optimum — Florence-2-base', sub: '~0.7 GB · schnell' },
                { id: 'qwen2.5-vl-3b', label: 'Best — Qwen2.5-VL-3B', sub: '~7 GB · multilingual' },
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

        {/* Video description prompt */}
        <div>
          <Label>Prompt für Videobeschreibung</Label>
          <textarea
            value={settings['ai.prompt.video'] ?? DEFAULT_VIDEO_PROMPT}
            onChange={e => set('ai.prompt.video', e.target.value)}
            rows={3}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
          />
          <div className="flex justify-between items-center mt-1">
            <p className="text-[11px] text-zinc-400">Angewendet auf den extrahierten Video-Frame.</p>
            <button type="button" onClick={() => set('ai.prompt.video', DEFAULT_VIDEO_PROMPT)}
              className="text-[11px] text-indigo-500 hover:underline">Standard</button>
          </div>
        </div>

        {/* Video transcoding */}
        <div className="space-y-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide">Transkodierung (H.264 MP4, faststart)</p>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">Alle Videos vorab transkodieren</p>
              <p className="text-xs text-zinc-400">Standardmäßig AUS: Videos werden beim ersten Abspielen transkodiert (gecacht). AN = jedes Video direkt beim Scan vorab konvertieren — sofort abspielbar, aber rechenintensiv (HW/QSV, sonst CPU).</p>
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

function ChatSettingsSection() {
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
      <SectionHeader title="Chat-Assistent" desc={'Unterhaltung über die Foto-Sammlung (RAG). Der Assistent durchsucht die Bilder per Vektorsuche (pgvector) und antwortet nur anhand der gefundenen Fotos. Öffnen über „Chat" in der Navigation.'} />
      <div className="space-y-6 max-w-xl">
        <div>
          <Label>Modell für den Chat</Label>
          <div className="grid grid-cols-2 gap-2 mt-1">
            {([
              { id: 'gemini', label: 'Gemini', sub: 'Cloud · Tool-Agent · Kosten pro Frage' },
              { id: 'local', label: 'Lokal (Qwen)', sub: 'privat · gratis · langsamer (Asus-GPU)' },
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
            Gemini nutzt den unter <b>Bilder-AI</b> hinterlegten API-Key als Tool-Agent (entscheidet selbst, wann er sucht).
            Lokal läuft über den Remote-Worker (Qwen) — gratis, aber langsamer. Beide antworten nur auf Basis gefundener Fotos.
          </p>
        </div>
        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
    </div>
  )
}

function PipelineSection() {
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
    onSuccess: (d: any) => { setBusy(''); qc.invalidateQueries({ queryKey: ['photo-stats'] }); qc.invalidateQueries({ queryKey: ['queues'] }); alert(`${d?.reprocessing ?? d?.new ?? 'OK'} — Aktion gestartet.`) },
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
      <SectionHeader title="Pipeline" desc="Live-Warteschlangen, Fehler-Queue und Stapel-Verarbeitung." />
      <div className="space-y-6 max-w-2xl">

        {/* Live queues */}
        <div>
          <Label>Warteschlangen (live)</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-1">
            <QCard label="CPU-Queue" val={queues?.cpu} hint="Scans, Thumbnails (4 parallel)" cls="text-indigo-500" />
            <QCard label="GPU-Queue (lokal)"
              val={queues?.gpu}
              hint={remoteActive ? 'bei aktivem Remote-Worker ungenutzt → läuft remote' : 'lokale KI + Gesichter (1 Slot)'}
              cls="text-zinc-400" />
            <QCard label="In Arbeit" val={st['processing']}
              hint={remoteActive ? 'an Remote-Worker übergeben, wartet auf Beschreibung' : 'aktuell verarbeitet'}
              cls="text-sky-500" />
          </div>
          {queues?.error && <p className="text-xs text-amber-500 mt-1">Queue-Status nicht lesbar: {queues.error}</p>}
        </div>

        {/* Remote AI backlog — the real description/face work when a remote worker runs */}
        {remoteActive && (
          <div>
            <Label>Remote-Verarbeitung (KI auf der GPU)</Label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-1">
              <QCard label="Beschreibungen offen" val={remote?.pending} hint="in der Warteschlange für die Describe-Worker" cls="text-violet-500" />
              <QCard label="Gesichter offen" val={remote?.faces_pending} hint="in der Warteschlange für die Faces-Worker" cls="text-sky-500" />
              <QCard label="Worker verbunden" val={remote?.workers?.length} hint="Details: Einstellungen → Remote-Worker" cls="text-emerald-500" />
            </div>
            <p className="text-[11px] text-zinc-400 mt-1">Beschreibung + Gesichter laufen über den Remote-Worker (Pull über HTTP) — deshalb ist die lokale GPU-Queue leer, der Rückstau steht hier.</p>
          </div>
        )}

        {/* Crop-cache warming (faster People page) */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="min-w-0">
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200 flex items-center gap-1.5"><ImageIcon size={14} /> Crop-Cache (Personen-Vorschauen)</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {crops && crops.total_faces > 0
                  ? <><b className={crops.cached >= crops.total_faces ? 'text-emerald-500' : 'text-sky-500'}>{crops.cached.toLocaleString('de')}</b> / {crops.total_faces.toLocaleString('de')} Gesichts-Crops erzeugt ({Math.round((crops.cached / crops.total_faces) * 100)}%) — vorab erzeugen lässt die Personen-Seite sofort laden.</>
                  : 'Vorschau-Crops für die Personen-Seite.'}
              </p>
              {crops && crops.total_faces > 0 && crops.cached < crops.total_faces && (
                <div className="mt-2 h-1.5 w-full max-w-xs bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
                  <div className="h-full bg-sky-500 rounded-full transition-all" style={{ width: `${Math.round((crops.cached / crops.total_faces) * 100)}%` }} />
                </div>
              )}
            </div>
            <ActBtn label={crops && crops.cached >= crops.total_faces ? 'Crops neu prüfen' : 'Crops vorbereiten'} busy={warmCrops.isPending} onClick={() => warmCrops.mutate()} />
          </div>
        </div>

        {/* Error queue */}
        <div className={`rounded-xl border p-4 ${errCount > 0 ? 'border-amber-400/60 bg-amber-500/5' : 'border-zinc-200 dark:border-zinc-700'}`}>
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Fehler-Queue</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                {errCount > 0
                  ? <><b className="text-amber-600 dark:text-amber-400">{errCount.toLocaleString('de')}</b> Fotos mit Fehler (Verarbeitung abgebrochen oder KI fehlgeschlagen).</>
                  : 'Keine Fehler — alles sauber verarbeitet. ✅'}
              </p>
            </div>
            <span className={`text-2xl font-bold tabular-nums ${errCount > 0 ? 'text-amber-500' : 'text-emerald-500'}`}>{errCount.toLocaleString('de')}</span>
          </div>
          <div className="flex flex-wrap gap-2 mt-3">
            <ActBtn label="Alle Fehler neu verarbeiten" busy={busy === 'failed'} onClick={() => run('failed', '/photos/reprocess-failed')} />
            <ActBtn label="KI nachholen" busy={busy === 'ai'} onClick={() => run('ai', '/photos/reprocess-missing-ai')} />
          </div>
        </div>

        {/* Batch actions */}
        <div>
          <Label>Stapel-Verarbeitung</Label>
          <div className="flex flex-wrap gap-2 mt-1">
            <ActBtn label="Alle Ordner scannen" busy={busy === 'scan'} onClick={() => run('scan', '/sources/scan-all')} />
            <ActBtn label="Gesichter clustern" busy={busy === 'cluster'} onClick={() => run('cluster', '/people/cluster')} />
          </div>
          <p className="text-[11px] text-zinc-400 mt-2">Live-Logs und Verlauf findest du unter <b>Pipeline</b> in der Navigation.</p>
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
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })
  const toggle = (id: number) => setIds(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id])

  return (
    <div>
      <SectionHeader title="Erinnerungen" desc="Heute vor 1, 2, … Jahren — in der Galerie. Optional nur Fotos mit bestimmten Personen." />
      <div className="space-y-4 max-w-2xl">
        <p className="text-sm text-zinc-600 dark:text-zinc-300">{ids.length === 0 ? 'Alle Fotos' : `Nur Fotos mit ${ids.length} ausgewählten Person(en)`}</p>
        <div className="flex flex-wrap gap-2">
          {[...people].sort((a, b) => b.face_count - a.face_count).map(p => (
            <button key={p.id} onClick={() => toggle(p.id)}
              className={`flex items-center gap-1.5 pl-1 pr-2.5 py-1 rounded-full border text-xs transition-colors ${ids.includes(p.id)
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}>
              <span className="w-5 h-5 rounded-full overflow-hidden bg-zinc-300 dark:bg-zinc-700 flex items-center justify-center text-[9px]">
                {p.avatar_url ? <img src={p.avatar_url} alt="" className="w-full h-full object-cover" /> : (p.name?.[0] ?? '?')}
              </span>
              {p.name} <span className="opacity-60">{p.face_count}</span>
            </button>
          ))}
          {people.length === 0 && <p className="text-sm text-zinc-400">Noch keine Personen — erst Gesichter clustern.</p>}
        </div>
        <button onClick={() => save.mutate()} disabled={save.isPending}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {saved ? '✓ Gespeichert' : 'Speichern'}
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
  const qc = useQueryClient()
  const [settings, setSettings] = useState<Settings>({})
  const [saved, setSaved] = useState(false)
  const sQ = useQuery({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  useEffect(() => { if (sQ.data) setSettings(sQ.data) }, [sQ.data])
  const { data: status } = useQuery<{
    enabled: boolean; has_token: boolean; pending: number; faces_pending: number;
    embed_done: number; embed_total: number; avg_dur: number | null; eta_seconds: number | null;
    workers: { name: string; last_seen: number; idle_s: number | null; jobs: number; last_dur: number | null; avg_dur: number | null }[]
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
      <SectionHeader title="Remote-Worker" desc="Eine GPU auf einem anderen Rechner zur Beschleunigung der KI-Erstverarbeitung dazuschalten (über HTTP, kein geteilter Speicher)." />
      <div className="space-y-6 max-w-2xl">
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">Remote-Worker aktivieren</p>
            <p className="text-xs text-zinc-400 mt-0.5">Wenn aktiv und ein Worker verbunden ist, werden KI-Jobs an ihn ausgelagert statt lokal (CPU) gerechnet.</p>
          </div>
          <Toggle value={enabled} onChange={v => set('remote.enabled', v ? 'true' : 'false')} />
        </label>

        <div>
          <Label>Zugriffs-Token (geteiltes Geheimnis)</Label>
          <div className="flex gap-2">
            <input value={token} onChange={e => set('remote.token', e.target.value)} placeholder="noch keins"
              className="flex-1 px-3 py-2 text-sm font-mono rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100" />
            <button onClick={genToken} className="px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800">Generieren</button>
          </div>
        </div>

        {/* Worker-Builder: stell zusammen, was für ein Worker auf welchem Gerät laufen soll */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 space-y-3">
          <Label>Worker einrichten (Befehl generieren)</Label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
            <label className="space-y-1"><span className="text-xs text-zinc-500">Typ</span>
              <select value={wType} onChange={e => setWType(e.target.value as any)} className={SEL}>
                <option value="ollama">Ollama (Mac, nativ)</option>
                <option value="bundled">Gebündelt (GPU-Box, Docker)</option>
              </select></label>
            <label className="space-y-1"><span className="text-xs text-zinc-500">Aufgabe</span>
              <select value={wMode} onChange={e => setWMode(e.target.value)} className={SEL}>
                <option value="describe">Beschreibung</option>
                <option value="embed">Embeddings (jina)</option>
                <option value="faces">Gesichter</option>
                <option value="all">Alles</option>
              </select></label>
            <label className="space-y-1"><span className="text-xs text-zinc-500">Medien</span>
              <select value={wMedia} onChange={e => setWMedia(e.target.value)} className={SEL}>
                <option value="images">Nur Bilder</option>
                <option value="videos">Nur Videos</option>
                <option value="both">Bilder + Videos</option>
              </select></label>
            <label className="space-y-1"><span className="text-xs text-zinc-500">Worker-Name</span>
              <input value={wName} onChange={e => setWName(e.target.value)} className={SEL} /></label>
            {wType === 'ollama' && (
              <label className="space-y-1 col-span-2"><span className="text-xs text-zinc-500">Ollama-Modell</span>
                <input value={wModel} onChange={e => setWModel(e.target.value)} placeholder="z.B. gemma4:26b, qwen3-vl:8b" className={SEL} /></label>
            )}
          </div>
          <p className="text-[11px] text-zinc-400">
            Beispiele: M3 = Ollama · Beschreibung · nur Bilder · gemma4:26b · „m3-describe". M5 = Ollama · Beschreibung · nur Videos · qwen3-vl:8b.
            Asus = Gebündelt · Embeddings (oder Gesichter). Embeddings/Gesichter brauchen die GPU-Box (jina/InsightFace).
          </p>
        </div>

        <button onClick={() => save.mutate(settings)} disabled={save.isPending}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {saved ? '✓ Gespeichert' : 'Speichern'}
        </button>

        {/* Live status */}
        <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Verarbeitung – Live</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${status?.enabled ? 'bg-emerald-500/15 text-emerald-500' : 'bg-zinc-500/15 text-zinc-400'}`}>{status?.enabled ? 'aktiv' : 'inaktiv'}</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
            <div><span className="text-2xl font-bold tabular-nums text-violet-500">{status?.pending ?? 0}</span><p className="text-xs text-zinc-400">Beschreibungen offen <span className="text-zinc-500">(in Schlange)</span></p></div>
            <div><span className="text-2xl font-bold tabular-nums text-sky-500">{status?.faces_pending ?? 0}</span><p className="text-xs text-zinc-400">Gesichter offen</p></div>
            <div><span className="text-2xl font-bold tabular-nums text-indigo-500">{status?.workers?.length ?? 0}</span><p className="text-xs text-zinc-400">verbundene Worker</p></div>
            <div><span className="text-2xl font-bold tabular-nums text-zinc-400">{status?.avg_dur != null ? `${status.avg_dur.toFixed(1)}s` : '—'}</span><p className="text-xs text-zinc-400">Ø pro Foto</p></div>
            <div><span className="text-2xl font-bold tabular-nums text-emerald-500">{fmtEta(status?.eta_seconds)}</span><p className="text-xs text-zinc-400">Restzeit Beschreib.</p></div>
          </div>
          {status && status.embed_total > 0 && (
            <div className="text-[11px] text-zinc-400">
              Embeddings (Bildsuche): <b className={status.embed_done >= status.embed_total ? 'text-emerald-500' : 'text-sky-500'}>{status.embed_done.toLocaleString('de')}</b> / {status.embed_total.toLocaleString('de')} ({Math.round(status.embed_done / status.embed_total * 100)}%)
              <div className="mt-1 h-1.5 w-full max-w-xs bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
                <div className="h-full bg-sky-500 rounded-full transition-all" style={{ width: `${Math.round(status.embed_done / status.embed_total * 100)}%` }} />
              </div>
            </div>
          )}
          {status?.eta_seconds != null && status.eta_seconds > 0 && (
            <p className="text-[11px] text-zinc-400">
              Hochrechnung: {status.pending} Fotos × {status.avg_dur?.toFixed(1)}s ÷ {status.workers.length} Worker.
              Bei diesem Tempo voraussichtlich fertig in <b className="text-zinc-600 dark:text-zinc-300">{fmtEta(status.eta_seconds)}</b>.
            </p>
          )}
          {(status?.workers?.length ?? 0) > 0 ? (
            <ul className="text-xs text-zinc-500 space-y-1">
              {status!.workers.map(w => {
                const idle = w.idle_s ?? Math.max(0, now - w.last_seen)
                return (
                  <li key={w.name} className="flex flex-wrap items-center gap-x-2">
                    <span className={idle < 30 ? 'text-emerald-500' : 'text-zinc-400'}>●</span>
                    <b className="text-zinc-700 dark:text-zinc-300">{w.name}</b>
                    {/* type from the worker name: a "faces" worker only sweeps faces, everything else describes */}
                    {/faces/i.test(w.name)
                      ? <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-500">Gesichter</span>
                      : <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/15 text-violet-500">Beschreibung</span>}
                    <span>· {w.jobs} Fotos</span>
                    {w.last_dur != null && <span>· letztes {w.last_dur.toFixed(1)}s</span>}
                    {w.avg_dur != null && <span>· Ø {w.avg_dur.toFixed(1)}s</span>}
                    <span className="text-zinc-400">· aktiv vor {idle}s</span>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="text-xs text-zinc-400">Kein Worker verbunden — KI-Jobs werden lokal (CPU) verarbeitet.</p>
          )}
        </div>

        {/* Generated start command for the chosen worker */}
        <div>
          <Label>Start-Befehl (auf dem Worker-Gerät ausführen)</Label>
          <p className="text-xs text-zinc-400 mb-2">{wType === 'ollama'
            ? <>Mac mit Ollama: <code>mac_describe_agent.py</code> aus dem Repo, Token oben speichern, im Terminal ausführen. Stoppen mit Ctrl-C.</>
            : <>GPU-Box (Repo unter <code>/opt/photoflow</code>): Token oben speichern, dann ausführen. Stoppen mit <code>docker compose -p photoflow-{wName} -f docker-compose.remote-worker.yml down</code>.</>}</p>
          <pre className="text-[11px] bg-zinc-900 text-zinc-200 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap">{cmd}</pre>
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
        <Label>Remote-Worker-Log (live)</Label>
        <button onClick={() => setOpen(o => !o)} className="text-xs text-indigo-500 hover:underline">{open ? 'Pausieren' : 'Aktualisieren'}</button>
      </div>
      <div className="h-64 overflow-y-auto rounded-lg bg-zinc-950 p-3 font-mono text-[11px] leading-relaxed">
        {lines.length === 0 ? (
          <p className="text-zinc-500">Noch keine Remote-Aktivität. Sobald ein Worker Fotos verarbeitet, erscheinen hier die Einträge (Dauer pro Foto, Beschreibung).</p>
        ) : lines.map((e, i) => (
          <div key={i} className={`whitespace-pre-wrap break-words py-0.5 ${e.level === 'WARNING' || e.level === 'ERROR' ? 'text-amber-400' : 'text-emerald-300'}`}>
            <span className="text-zinc-600">{(e.ts || '').slice(11, 19)} </span>{e.message}
          </div>
        ))}
      </div>
      <p className="text-[11px] text-zinc-400 mt-1">Zeigt jede vom Remote-Worker abgeschlossene Aufgabe mit Verarbeitungsdauer. Vollständige Logs unter „Logs“ → Remote-Worker.</p>
    </div>
  )
}

function FacesSection() {
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
      <SectionHeader title="Personen & Gesichter" desc="Gesichtserkennung und automatisches Personen-Clustering (lokal, InsightFace)." />
      <div className="space-y-6 max-w-xl">
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">Gesichtserkennung aktivieren</p>
            <p className="text-xs text-zinc-400 mt-0.5">Erkennt Gesichter pro Foto, speichert Position + Embedding für Clustering.</p>
          </div>
          <Toggle value={enabled} onChange={v => set('faces.enabled', v ? 'true' : 'false')} />
        </label>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>Engine (Erkennung + Embedding)</Label>
            <select value={settings['face.engine'] ?? 'facenet'} onChange={e => set('face.engine', e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="facenet">facenet (MTCNN + VGGFace2, leicht)</option>
              <option value="insightface">InsightFace / ArcFace (genauer)</option>
            </select>
          </div>
          <div>
            <Label>Clustering-Algorithmus</Label>
            <select value={settings['face.cluster_algo'] ?? 'dbscan'} onChange={e => set('face.cluster_algo', e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
              <option value="dbscan">DBSCAN (Standard)</option>
              <option value="hdbscan">HDBSCAN (variable Dichte)</option>
            </select>
          </div>
        </div>
        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">Automatisch clustern</p>
            <p className="text-xs text-zinc-400 mt-0.5">Gruppiert erkannte Gesichter alle 5 Min. selbstständig zu Personen.</p>
          </div>
          <Toggle value={(settings['face.auto_cluster'] ?? 'true') !== 'false'} onChange={v => set('face.auto_cluster', v ? 'true' : 'false')} />
        </label>
        <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-900/15 border border-amber-200 dark:border-amber-700/40 text-xs text-amber-700 dark:text-amber-300">
          Beide Engines liefern 512-dim-Embeddings — aber in <strong>unterschiedlichen Vektorräumen</strong>.
          Nach einem Engine-Wechsel die Gesichter neu erkennen lassen („Neu verarbeiten“ pro Ordner),
          damit alte und neue Embeddings nicht gemischt werden. InsightFace lädt beim ersten Lauf ein Modell (~300&nbsp;MB).
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <Label>Cluster-Schwelle</Label>
            <Input value={settings['face.clustering_threshold'] ?? '0.6'} onChange={v => set('face.clustering_threshold', v)} placeholder="0.6" />
          </div>
          <div>
            <Label>Min. Konfidenz</Label>
            <Input value={settings['face.min_confidence'] ?? '0.7'} onChange={v => set('face.min_confidence', v)} placeholder="0.7" />
          </div>
          <div>
            <Label>Min. Größe (px)</Label>
            <Input value={settings['face.min_size_px'] ?? '40'} onChange={v => set('face.min_size_px', v)} placeholder="40" />
          </div>
          <div>
            <Label>Min. Gesichter/Person</Label>
            <Input value={settings['face.min_cluster_size'] ?? '3'} onChange={v => set('face.min_cluster_size', v)} placeholder="3" />
          </div>
          <div>
            <Label>Zusammenführen-Schwelle</Label>
            <Input value={settings['face.merge_threshold'] ?? '0.5'} onChange={v => set('face.merge_threshold', v)} placeholder="0.5" />
          </div>
        </div>
        <p className="text-xs text-zinc-400">Gegen tausende Mini-Gesichter: <b>Min. Größe</b> filtert winzige Hintergrund-Gesichter schon bei der Erkennung weg, <b>Min. Gesichter/Person</b> verhindert 1–2-Foto-„Personen" (Reste bleiben unter „Gesichter", werden aber nicht zu Personen).</p>

        <div className="space-y-3 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide flex items-center gap-2">
            <Video size={12} /> Gesichter in Videos
          </p>
          <label className="flex items-center justify-between">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">Auch in Videos erkennen</p>
              <p className="text-xs text-zinc-400">Extrahiert Frames und analysiert sie (langsamer).</p>
            </div>
            <Toggle value={(settings['video.face_recognition'] ?? 'false') === 'true'} onChange={v => set('video.face_recognition', v ? 'true' : 'false')} />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Frame-Intervall (s)</Label>
              <Input value={settings['video.face_interval_sec'] ?? '5'} onChange={v => set('video.face_interval_sec', v)} placeholder="5" />
            </div>
            <div>
              <Label>Max. Frames/Video</Label>
              <Input value={settings['video.max_frames'] ?? '30'} onChange={v => set('video.max_frames', v)} placeholder="30" />
            </div>
          </div>
        </div>

        <p className="text-xs text-emerald-500">
          Gesichtserkennung ist aktiv — Gesichter werden beim Verarbeiten erkannt, gespeichert und
          (sofern aktiviert) automatisch zu Personen gruppiert. Gruppen benennen/zusammenführen unter „Personen“.
        </p>

        <SaveButton pending={save.isPending} saved={saved} onClick={() => save.mutate(settings)} />
      </div>
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

  // Automatic schedule (persisted settings the scheduled_backup beat task reads).
  const { data: appSettings } = useQuery<Settings>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data as Settings), staleTime: 30_000 })
  const [sched, setSched] = useState('off')
  const [savedSched, setSavedSched] = useState(false)
  useEffect(() => { if (appSettings?.['backup.schedule']) setSched(appSettings['backup.schedule']); if (appSettings?.['backup.keep_days']) setKeepDays(Number(appSettings['backup.keep_days'])) }, [appSettings])
  const saveSchedule = useMutation({
    mutationFn: () => api.put('/settings', { 'backup.schedule': sched, 'backup.keep_days': String(keepDays), 'backup.rclone_remote': rcloneRemote }),
    onSuccess: () => { setSavedSched(true); setTimeout(() => setSavedSched(false), 2000); qc.invalidateQueries({ queryKey: ['settings'] }) },
  })
  const restore = useMutation({
    mutationFn: (b: BackupFile) => b.type === 'db'
      ? api.post('/backup/restore/db', null, { params: { filename: b.name } })
      : api.post('/backup/restore/files', null, { params: { filename: b.name } }),
    onSuccess: (r: any) => alert(r?.data?.ok === false ? 'Wiederherstellung mit Fehlern — Server-Logs prüfen.' : 'Wiederhergestellt. Ggf. Seite neu laden / Backend neu starten.'),
    onError: () => alert('Wiederherstellung fehlgeschlagen.'),
  })
  const verify = useMutation({
    mutationFn: (name: string) => api.post('/backup/verify', null, { params: { filename: name } }).then(r => r.data),
    onSuccess: (d: any) => alert(d?.ok ? `✓ Backup ok — ${d.tables} Tabellen, ${d.photo_rows} Fotos (${d.size_mb} MB).` : `⚠ Verifikation fehlgeschlagen: ${d?.error ?? 'unbekannt'}`),
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
              {b.type === 'db' && <button onClick={() => verify.mutate(b.name)} className="text-zinc-400 hover:text-zinc-200 text-xs">Prüfen</button>}
              <button onClick={() => { if (confirm(`„${b.name}" wiederherstellen? Überschreibt aktuelle ${b.type === 'db' ? 'Datenbank' : 'Dateien'}.`)) restore.mutate(b) }}
                className="text-amber-400 hover:text-amber-300 text-xs transition-colors">Restore</button>
              <a href={`/api/backup/download/${b.name}`} download
                className="text-indigo-400 hover:text-indigo-300 text-xs transition-colors">Download</a>
            </div>
          ))}
        </div>
      </div>

      {/* Automatic schedule */}
      <div className="mb-4 p-4 rounded-xl border border-zinc-200 dark:border-zinc-700">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">Automatische Sicherung</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label>Zeitplan</Label>
            <select value={sched} onChange={e => setSched(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100">
              <option value="off">Aus</option>
              <option value="daily">Täglich</option>
              <option value="weekly">Wöchentlich</option>
            </select>
          </div>
          <div>
            <Label>Aufbewahrung (Tage)</Label>
            <Input value={String(keepDays)} onChange={v => setKeepDays(Number(v) || 30)} placeholder="30" />
          </div>
        </div>
        <button onClick={() => saveSchedule.mutate()} disabled={saveSchedule.isPending}
          className="mt-3 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {savedSched ? '✓ Gespeichert' : 'Zeitplan speichern'}
        </button>
        <p className="text-[11px] text-zinc-400 mt-2">Sichert automatisch DB + Thumbnails + Config (inkl. optionalem Rclone-Ziel unten). Alte Backups werden nach der Aufbewahrungsdauer entfernt.</p>
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
      <SectionHeader title="Karte" desc="Kartendarstellung der Fotos mit GPS-Daten." />
      <div className="space-y-5 max-w-xl">
        <div>
          <Label>Standard-Kartenebene</Label>
          <select value={settings['map.default_layer'] ?? 'osm'} onChange={e => set('map.default_layer', e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="osm">Standard (OpenStreetMap)</option>
            <option value="satellite">Satellit (Esri)</option>
            <option value="dark">Dunkel (CARTO)</option>
            <option value="light">Hell (CARTO)</option>
            <option value="voyager">Voyager (CARTO)</option>
            <option value="topo">Topo (OpenTopoMap)</option>
            <option value="google">Google</option>
            <option value="google_sat">Google Satellit</option>
            <option value="google_hybrid">Google Hybrid</option>
            <option value="maptiler">MapTiler (Key nötig)</option>
            <option value="maptiler_sat">MapTiler Satellit (Key nötig)</option>
          </select>
          <p className="text-xs text-zinc-400 mt-1">Alle Ebenen sind kostenlos & ohne API-Key. Auf der Karte jederzeit umschaltbar.</p>
        </div>

        <div>
          <Label>MapTiler API-Key (optional)</Label>
          <Input value={settings['map.maptiler_key'] ?? ''} onChange={v => set('map.maptiler_key', v)} type="password" placeholder="dein MapTiler-Key" />
          <p className="text-xs text-zinc-400 mt-1">Aktiviert zusätzlich die Ebenen „MapTiler" und „MapTiler Satellit" (kostenloser Key auf maptiler.com). Leer lassen = nur freie Ebenen.</p>
        </div>

        <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <div>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">Street-View-Link anzeigen</p>
            <p className="text-xs text-zinc-400 mt-0.5">Öffnet Google Street View an den Foto-Koordinaten (kostenlos, kein Key).</p>
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
      <SectionHeader title="Funktionen" desc="Optionale Bereiche der App ein- oder ausblenden." />
      <div className="space-y-3 max-w-xl">
        <Row k="features.relationships" title="Beziehungen / Stammbaum" desc="Familien- & Freundes-Netzwerk in der Seitenleiste. Personen verknüpfen und als Graph anzeigen." />
        <Row k="map.globe_default" title="Karte als 3D-Globus öffnen" desc="Standardansicht der Karte ist die 3D-Weltkugel statt der flachen Karte." />
      </div>
    </div>
  )
}

type AppUser = { id: number; email: string; name: string; role: 'admin' | 'user'; is_active: boolean; last_login: string | null; access_config?: Record<string, any> | null }

function UsersSection() {
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
  const inval = () => qc.invalidateQueries({ queryKey: ['users'] })
  const createU = useMutation({ mutationFn: () => api.post('/users', add), onSuccess: () => { inval(); setShowAdd(false); setAdd({ email: '', name: '', password: '', role: 'user' }) } })
  const patchU = useMutation({ mutationFn: ({ id, body }: { id: number; body: Partial<AppUser> }) => api.patch(`/users/${id}`, body), onSuccess: inval })
  const delU = useMutation({ mutationFn: (id: number) => api.delete(`/users/${id}`), onSuccess: inval })
  const setPwM = useMutation({ mutationFn: ({ id, password }: { id: number; password: string }) => api.post(`/users/${id}/password`, { password }), onSuccess: () => { setPwFor(null); setPw('') } })

  const notAuthed = usersQuery.isError
  const sel = 'px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div>
      <SectionHeader title="Benutzer & Login" desc="Konten verwalten und festlegen, ob für PhotoFlow ein Login nötig ist." />

      {notAuthed ? (
        <div className="max-w-xl p-4 rounded-xl border border-amber-300 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/20 text-sm text-amber-800 dark:text-amber-200">
          <p className="flex items-center gap-2 font-medium"><Lock size={15} /> Als Administrator anmelden</p>
          <p className="mt-1 text-amber-700 dark:text-amber-300/90">Die Benutzerverwaltung ist nur für angemeldete Admins sichtbar. Start-Login: <strong>admin@photoflow.local</strong> / <strong>Nimtz@1977</strong>.</p>
          <a href="/login" className="inline-flex items-center gap-1.5 mt-3 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500"><KeyRound size={14} /> Zur Anmeldung</a>
        </div>
      ) : (
        <div className="space-y-6 max-w-2xl">
          {/* Login enforce */}
          <label className="flex items-center justify-between p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
            <div>
              <p className="text-sm text-zinc-700 dark:text-zinc-300">Login erzwingen</p>
              <p className="text-xs text-zinc-500 mt-0.5">Wenn aktiv, ist die Web-Oberfläche nur nach Anmeldung nutzbar. (Die iOS-App ist nicht betroffen.)</p>
            </div>
            <Toggle value={enforce} onChange={setEnforce} />
          </label>

          {/* User list */}
          <div className="rounded-xl border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-200 dark:divide-zinc-800">
            {(usersQuery.data ?? []).map(u => (
              <div key={u.id} className="p-3 flex flex-wrap items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs font-semibold shrink-0">{u.name.charAt(0).toUpperCase()}</div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100 truncate">{u.name} {!u.is_active && <span className="text-xs text-zinc-500">(deaktiviert)</span>}</p>
                  <p className="text-xs text-zinc-500 truncate">{u.email}</p>
                </div>
                <select className={sel} value={u.role} onChange={e => patchU.mutate({ id: u.id, body: { role: e.target.value as 'admin' | 'user' } })}>
                  <option value="admin">Admin</option>
                  <option value="user">Benutzer</option>
                </select>
                <button onClick={() => patchU.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                  className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                  {u.is_active ? 'Deaktivieren' : 'Aktivieren'}
                </button>
                {u.role !== 'admin' && (
                  <button onClick={() => { setAccFor(accFor === u.id ? null : u.id); setAcc(u.access_config || {}) }}
                    className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Zugriff</button>
                )}
                <button onClick={() => { setEditFor(editFor === u.id ? null : u.id); setEditName(u.name); setEditEmail(u.email) }}
                  className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Bearbeiten</button>
                <button onClick={() => { setPwFor(pwFor === u.id ? null : u.id); setPw('') }}
                  className="text-xs px-2 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Passwort</button>
                <button onClick={() => delU.mutate(u.id)} className="text-zinc-400 hover:text-red-500" title="Löschen"><Trash2 size={15} /></button>
                {editFor === u.id && (
                  <div className="w-full flex flex-wrap gap-2 mt-1">
                    <input value={editName} onChange={e => setEditName(e.target.value)} placeholder="Name"
                      className="flex-1 min-w-[8rem] px-3 py-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm" />
                    <input value={editEmail} onChange={e => setEditEmail(e.target.value)} placeholder="E-Mail (= Login)" type="email"
                      className="flex-1 min-w-[10rem] px-3 py-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm" />
                    <button onClick={() => { patchU.mutate({ id: u.id, body: { name: editName, email: editEmail } as any }); setEditFor(null) }}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500">Speichern</button>
                    <p className="w-full text-[11px] text-amber-600 dark:text-amber-400">⚠ Die E-Mail ist dein Login — sie muss ein echtes E-Mail-Format haben (z. B. name@domain). Der Anzeigename oben ist frei wählbar.</p>
                  </div>
                )}
                {pwFor === u.id && (
                  <div className="w-full flex gap-2 mt-1">
                    <input type="text" value={pw} onChange={e => setPw(e.target.value)} placeholder="Neues Passwort (min. 6)"
                      className="flex-1 px-3 py-1.5 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                    <button onClick={() => setPwM.mutate({ id: u.id, password: pw })} disabled={pw.length < 6}
                      className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50">Setzen</button>
                  </div>
                )}
                {accFor === u.id && (
                  <div className="w-full mt-2 p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">Sichtbar ab (Datum)</label>
                        <input type="date" value={acc.visible_from || ''} onChange={e => setAcc(a => ({ ...a, visible_from: e.target.value || undefined }))} className={sel + ' w-full'} />
                      </div>
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">Sichtbar bis (Datum)</label>
                        <input type="date" value={acc.visible_until || ''} onChange={e => setAcc(a => ({ ...a, visible_until: e.target.value || undefined }))} className={sel + ' w-full'} />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-500 mb-1">Nur diese Personen-IDs (kommagetrennt, leer = alle)</label>
                      <input type="text" value={(acc.visible_person_ids || []).join(',')}
                        onChange={e => setAcc(a => ({ ...a, visible_person_ids: e.target.value.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n)) }))}
                        placeholder="z.B. 19,20" className={sel + ' w-full'} />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">Nur diese Ordner (ein Pfad pro Zeile, leer = alle)</label>
                        <textarea rows={2} value={(acc.folder_whitelist || []).join('\n')}
                          onChange={e => setAcc(a => ({ ...a, folder_whitelist: e.target.value.split('\n').map(s => s.trim()).filter(Boolean) }))}
                          placeholder="/photos/Familie" className={sel + ' w-full resize-none'} />
                      </div>
                      <div>
                        <label className="block text-xs text-zinc-500 mb-1">Diese Ordner ausblenden (ein Pfad pro Zeile)</label>
                        <textarea rows={2} value={(acc.folder_blacklist || []).join('\n')}
                          onChange={e => setAcc(a => ({ ...a, folder_blacklist: e.target.value.split('\n').map(s => s.trim()).filter(Boolean) }))}
                          placeholder="/photos/Privat" className={sel + ' w-full resize-none'} />
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      {([['allow_download', 'Download'], ['allow_map', 'Karte'], ['allow_pipeline', 'Pipeline']] as const).map(([k, lbl]) => (
                        <label key={k} className="flex items-center gap-1.5 text-sm text-zinc-700 dark:text-zinc-300">
                          <input type="checkbox" checked={acc[k] ?? true} onChange={e => setAcc(a => ({ ...a, [k]: e.target.checked }))} className="accent-indigo-500" /> {lbl}
                        </label>
                      ))}
                    </div>
                    <div className="flex justify-end">
                      <button onClick={() => patchU.mutate({ id: u.id, body: { access_config: acc } as any })}
                        className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500">Zugriff speichern</button>
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
                <input value={add.email} onChange={e => setAdd(a => ({ ...a, email: e.target.value }))} placeholder="E-Mail" className={sel + ' w-full'} />
                <input value={add.name} onChange={e => setAdd(a => ({ ...a, name: e.target.value }))} placeholder="Name" className={sel + ' w-full'} />
                <input type="text" value={add.password} onChange={e => setAdd(a => ({ ...a, password: e.target.value }))} placeholder="Passwort (min. 6)" className={sel + ' w-full'} />
                <select value={add.role} onChange={e => setAdd(a => ({ ...a, role: e.target.value }))} className={sel + ' w-full'}>
                  <option value="user">Benutzer</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div className="flex gap-2 justify-end">
                <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Abbrechen</button>
                <button onClick={() => createU.mutate()} disabled={createU.isPending || !add.email || !add.name || add.password.length < 6}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">Anlegen</button>
              </div>
              {createU.isError && <p className="text-xs text-red-500">Anlegen fehlgeschlagen (E-Mail evtl. vergeben).</p>}
            </div>
          ) : (
            <button onClick={() => setShowAdd(true)} className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
              <Plus size={15} /> Benutzer hinzufügen
            </button>
          )}
        </div>
      )}
    </div>
  )
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
          <option value="remote">Remote-Worker</option>
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

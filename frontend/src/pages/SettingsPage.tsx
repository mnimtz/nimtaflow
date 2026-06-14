import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, RefreshCw, Check, X, FolderOpen } from 'lucide-react'
import { api, Source } from '../lib/api'
import FolderBrowser from '../components/ui/FolderBrowser'

const SECTIONS = ['Quellen', 'AI-Provider', 'Pipeline', 'Karte', 'Backup'] as const
type Section = typeof SECTIONS[number]

export default function SettingsPage() {
  const [section, setSection] = useState<Section>('Quellen')

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <nav className="w-44 shrink-0 border-r border-gray-200 dark:border-gray-800 py-4 space-y-1 px-2">
        {SECTIONS.map((s) => (
          <button
            key={s}
            onClick={() => setSection(s)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
              section === s
                ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 font-medium'
                : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            {s}
          </button>
        ))}
      </nav>

      {/* Content */}
      <div className="flex-1 overflow-auto p-6 max-w-2xl">
        {section === 'Quellen' && <SourcesSection />}
        {section === 'AI-Provider' && <AISection />}
        {section === 'Pipeline' && <PipelineSection />}
        {section === 'Karte' && <MapSection />}
        {section === 'Backup' && <BackupSection />}
      </div>
    </div>
  )
}

function SectionHeader({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-lg font-bold text-gray-900 dark:text-white">{title}</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{desc}</p>
    </div>
  )
}

function SourcesSection() {
  const [newPath, setNewPath] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const qc = useQueryClient()

  const { data: sources = [] } = useQuery<Source[]>({
    queryKey: ['sources'],
    queryFn: () => api.get('/sources').then((r) => r.data),
  })

  const addMutation = useMutation({
    mutationFn: (path: string) => api.post('/sources', { path }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sources'] }); setNewPath('') },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/sources/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  })

  const scanMutation = useMutation({
    mutationFn: (id: number) => api.post(`/sources/${id}/scan`),
  })

  return (
    <div>
      <SectionHeader title="Foto-Quellen" desc="Ordner die PhotoFlow überwachen soll. Originale werden niemals verändert." />

      <div className="space-y-3 mb-4">
        {sources.map((s) => (
          <div key={s.id} className="flex items-center gap-3 p-3 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{s.path}</p>
              <p className="text-xs text-gray-400 mt-0.5">
                {s.last_scan_at ? `Letzter Scan: ${new Date(s.last_scan_at).toLocaleString('de')}` : 'Noch nicht gescannt'}
                {s.last_scan_count !== null ? ` · ${s.last_scan_count} neue Fotos` : ''}
              </p>
            </div>
            <button
              onClick={() => scanMutation.mutate(s.id)}
              disabled={scanMutation.isPending}
              className="p-1.5 rounded text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
              title="Jetzt scannen"
            >
              <RefreshCw size={15} />
            </button>
            <button
              onClick={() => deleteMutation.mutate(s.id)}
              className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); if (newPath) addMutation.mutate(newPath) }}
        className="space-y-2"
      >
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="/photos"
              className="w-full pl-3 pr-10 py-2 text-sm font-mono rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={() => setShowBrowser(true)}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-gray-400 hover:text-indigo-600 transition-colors"
              title="Ordner durchsuchen"
            >
              <FolderOpen size={16} />
            </button>
          </div>
          <button
            type="submit"
            disabled={!newPath || addMutation.isPending}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors shrink-0"
          >
            <Plus size={15} />
            Hinzufügen
          </button>
        </div>
        <p className="text-xs text-gray-400">
          Tippe einen Pfad ein oder klicke <FolderOpen size={12} className="inline" /> um den Server-Dateisystem zu durchsuchen.
        </p>
      </form>

      {showBrowser && (
        <FolderBrowser
          initialPath={newPath || '/'}
          onSelect={(path) => setNewPath(path)}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </div>
  )
}

function AISection() {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()

  const { data } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get('/settings').then((r) => r.data as Record<string, string>),
    onSuccess: (d: Record<string, string>) => setSettings(d),
  } as any)

  const saveMutation = useMutation({
    mutationFn: (s: Record<string, string>) => api.put('/settings', s),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000) },
  })

  function field(key: string, label: string, type = 'text', placeholder = '') {
    return (
      <div key={key}>
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{label}</label>
        <input
          type={type}
          value={settings[key] ?? ''}
          onChange={(e) => setSettings((s) => ({ ...s, [key]: e.target.value }))}
          placeholder={placeholder}
          className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>
    )
  }

  return (
    <div>
      <SectionHeader title="AI-Provider" desc="Konfiguriere Cloud oder lokale AI. Alle Felder sind optional." />

      <div className="space-y-6">
        <div className="space-y-3">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Aktiver Provider</p>
          <select
            value={settings['ai.provider'] ?? 'none'}
            onChange={(e) => setSettings((s) => ({ ...s, 'ai.provider': e.target.value }))}
            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="none">Kein AI (nur EXIF)</option>
            <option value="gemini">Google Gemini</option>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic Claude</option>
            <option value="ollama">Ollama (lokal)</option>
          </select>
        </div>

        <div className="space-y-3">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Google Gemini</p>
          {field('ai.gemini.api_key', 'API Key', 'password', 'AIza…')}
          {field('ai.gemini.model', 'Modell', 'text', 'gemini-2.5-flash')}
          {field('ai.gemini.embed_model', 'Embedding-Modell', 'text', 'text-embedding-004')}
        </div>

        <div className="space-y-3">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Ollama (lokal)</p>
          {field('ai.ollama.url', 'Ollama URL', 'text', 'http://your-host:11434')}
          {field('ai.ollama.vision_model', 'Vision-Modell', 'text', 'llava:7b')}
          {field('ai.ollama.embed_model', 'Embedding-Modell', 'text', 'nomic-embed-text')}
        </div>

        <div className="space-y-3">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">Sprache für Beschreibungen</p>
          <select
            value={settings['ai.language'] ?? 'de'}
            onChange={(e) => setSettings((s) => ({ ...s, 'ai.language': e.target.value }))}
            className="w-full px-3 py-2 text-sm rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="de">Deutsch</option>
            <option value="en">Englisch</option>
            <option value="fr">Französisch</option>
          </select>
        </div>

        <button
          onClick={() => saveMutation.mutate(settings)}
          disabled={saveMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saved ? <><Check size={15} /> Gespeichert</> : 'Speichern'}
        </button>
      </div>
    </div>
  )
}

function PipelineSection() {
  return (
    <div>
      <SectionHeader title="Pipeline-Einstellungen" desc="Batch-Größe, Parallelität und automatischer Scan." />
      <p className="text-sm text-gray-500 dark:text-gray-400">Kommt bald.</p>
    </div>
  )
}

function MapSection() {
  return (
    <div>
      <SectionHeader title="Karten-Provider" desc="Wähle den Kartendienst für die Weltkarte." />
      <p className="text-sm text-gray-500 dark:text-gray-400">Kommt bald.</p>
    </div>
  )
}

function BackupSection() {
  return (
    <div>
      <SectionHeader title="Backup" desc="Automatische Datenbank-Backups." />
      <p className="text-sm text-gray-500 dark:text-gray-400">Kommt bald.</p>
    </div>
  )
}

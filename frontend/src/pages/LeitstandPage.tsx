// v1.560: Neuer einheitlicher Leitstand — 6 Kacheln, identisch zu iOS.
// Datenquelle: GET /api/v1/leitstand — ein Endpoint, eine Wahrheit.
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useT } from '../i18n'
import {
  FileText, Film, FileCode, Users, RefreshCw, Cpu, Play, PlayCircle
} from 'lucide-react'

type Slice = { done: number; total: number; pct: number; rate_pro_stunde?: number }
type Leitstand = {
  updated_at: string
  kacheln: {
    descriptions: {
      title: string
      text: Slice
      structured: Slice
      ohne_beschreibung: number
      detail: string
    }
    videos: {
      title: string
      transcode: Slice
      beschreibung: Slice
      fehler: number
    }
    metadata: {
      title: string
      sidecar: Slice
      fehlend: number
      action_label: string
      action_task: string
      detail: string
    }
    people: {
      title: string
      namen: number
      faces_zugeordnet: number
      faces_offen: number
      faces_vorschlaege: number
    }
    reingest: {
      title: string
      pending: number
      in_batch: number
      done_last_hour: number
      eta_stunden: number | null
    }
    workers: {
      name: string
      status: 'aktiv' | 'idle' | 'offline'
      letzte_arbeit_vor_sekunden: number | null
      durchschnitt_sek: number
      rate_pro_stunde: number
    }[]
    warteschlangen: Record<string, number>
  }
}

const fmt = (n: number) => (n ?? 0).toLocaleString('de')
const fmtSec = (s: number | null) => s == null ? '—' : s < 60 ? `${s}s` : s < 3600 ? `${Math.round(s/60)} Min` : `${Math.round(s/3600)} h`
const barColor = (pct: number) => pct >= 95 ? 'bg-emerald-500' : pct >= 60 ? 'bg-amber-500' : 'bg-rose-500'

function Bar({ pct, className = '' }: { pct: number; className?: string }) {
  return (
    <div className={`h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden ${className}`}>
      <div className={`h-full ${barColor(pct)}`} style={{ width: `${Math.min(100, pct)}%` }} />
    </div>
  )
}

function Card({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-5">
      <header className="flex items-center gap-2 mb-4">
        <Icon size={18} className="text-indigo-500" />
        <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{title}</h2>
      </header>
      {children}
    </section>
  )
}

function Metric({ label, done, total, pct, suffix }: { label: string; done: number; total: number; pct: number; suffix?: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-xs text-zinc-500">{label}</span>
        <span className="text-xs tabular-nums text-zinc-600 dark:text-zinc-300">
          {fmt(done)} <span className="text-zinc-400">/ {fmt(total)}</span> {suffix ?? ''}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Bar pct={pct} className="flex-1" />
        <span className="text-xs tabular-nums text-zinc-500 w-12 text-right">{pct.toFixed(1)}%</span>
      </div>
    </div>
  )
}

export default function LeitstandPage() {
  const { t } = useT()
  const { data, dataUpdatedAt, isLoading } = useQuery<Leitstand>({
    queryKey: ['leitstand-v2'],
    queryFn: () => api.get('/v1/leitstand').then(r => r.data),
    refetchInterval: 3000,
  })

  const backfill = useMutation({
    mutationFn: () => api.post('/v1/ops/xmp-backfill/start', { full: true }),
  })
  const cloudFallback = useMutation({
    mutationFn: () => api.post('/v1/ops/video-cloud-fallback/start', { limit: 500 }),
  })
  const resetAiErrors = useMutation({
    mutationFn: () => api.post('/v1/ops/reset-ai-errors', { kind: 'all' }),
  })

  const k = data?.kacheln
  const stamp = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString('de') : '—'

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      <header className="flex items-baseline justify-between">
        <h1 className="text-xl font-bold text-zinc-900 dark:text-white">Leitstand</h1>
        <div className="flex items-center gap-2 text-xs text-zinc-500">
          <RefreshCw size={12} className={isLoading ? 'animate-spin' : ''} />
          <span>aktualisiert {stamp} · alle 3 s</span>
        </div>
      </header>

      {!k && (
        <div className="text-zinc-500">Lade …</div>
      )}

      {k && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

          {/* 1. Beschreibungen */}
          <Card title={k.descriptions.title} icon={FileText}>
            <div className="space-y-3">
              <Metric label="Freitext-Beschreibung" {...k.descriptions.text} />
              <Metric label="Strukturiertes JSON (28 Felder)" {...k.descriptions.structured} />
              {k.descriptions.structured.rate_pro_stunde != null && (
                <div className="text-xs text-zinc-500 tabular-nums">
                  aktuell {fmt(k.descriptions.structured.rate_pro_stunde)} Fotos/h neu strukturiert
                </div>
              )}
              <p className="text-xs text-zinc-500 pt-2">{k.descriptions.detail}</p>
            </div>
          </Card>

          {/* 2. Videos */}
          <Card title={k.videos.title} icon={Film}>
            <div className="space-y-3">
              <Metric label="1080p-Version bereit" {...k.videos.transcode} />
              <Metric label="KI-Beschreibung" {...k.videos.beschreibung} />
              {k.videos.fehler > 0 && (
                <div className="flex items-center justify-between text-xs pt-2">
                  <span className="text-rose-500">{fmt(k.videos.fehler)} Videos mit Fehler</span>
                  <button
                    onClick={() => cloudFallback.mutate()}
                    disabled={cloudFallback.isPending}
                    className="px-3 py-1 rounded-lg bg-indigo-600 text-white text-xs hover:bg-indigo-700 disabled:opacity-40"
                  >
                    Cloud (Gemini) nachziehen
                  </button>
                </div>
              )}
            </div>
          </Card>

          {/* 3. Metadaten auf Platte */}
          <Card title={k.metadata.title} icon={FileCode}>
            <div className="space-y-3">
              <Metric label="XMP-Sidecar geschrieben" {...k.metadata.sidecar} />
              <p className="text-xs text-zinc-500">{k.metadata.detail}</p>
              {k.metadata.fehlend > 0 && (
                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-zinc-500">{fmt(k.metadata.fehlend)} fehlen noch</span>
                  <button
                    onClick={() => backfill.mutate()}
                    disabled={backfill.isPending}
                    className="px-3 py-1 rounded-lg bg-indigo-600 text-white text-xs hover:bg-indigo-700 disabled:opacity-40"
                  >
                    {k.metadata.action_label}
                  </button>
                </div>
              )}
            </div>
          </Card>

          {/* 4. Personen */}
          <Card title={k.people.title} icon={Users}>
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Benannte Personen" val={k.people.namen} />
              <Stat label="Gesichter zugeordnet" val={k.people.faces_zugeordnet} />
              <Stat label="Offene Gesichter" val={k.people.faces_offen} tone={k.people.faces_offen > 1000 ? 'warn' : 'ok'} />
              <Stat label="Vorschläge" val={k.people.faces_vorschlaege} />
            </div>
          </Card>

          {/* 5. Reingest */}
          <Card title={k.reingest.title} icon={PlayCircle}>
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Aktuell in Bearbeitung" val={k.reingest.pending} tone={k.reingest.pending > 0 ? 'info' : 'ok'} />
              <Stat label="Gesamter Batch offen" val={k.reingest.in_batch} />
              <Stat label="Letzte Stunde fertig" val={k.reingest.done_last_hour} />
              <Stat label="Restzeit (grob)"
                    val={k.reingest.eta_stunden == null ? '—' : `${k.reingest.eta_stunden} h`} />
            </div>
          </Card>

          {/* 6. Worker */}
          <Card title="Worker-Fleet" icon={Cpu}>
            <div className="space-y-2">
              {k.workers.map(w => (
                <div key={w.name} className="flex items-center justify-between p-2 rounded-lg bg-zinc-50 dark:bg-zinc-800/50">
                  <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${
                      w.status === 'aktiv' ? 'bg-emerald-500' :
                      w.status === 'idle' ? 'bg-amber-500' : 'bg-rose-500'}`} />
                    <span className="text-sm font-medium">{w.name}</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs tabular-nums text-zinc-500">
                    <span>{fmt(w.rate_pro_stunde)} /h</span>
                    <span>Ø {w.durchschnitt_sek}s</span>
                    <span>{w.status === 'offline' ? 'offline' : `zuletzt ${fmtSec(w.letzte_arbeit_vor_sekunden)}`}</span>
                  </div>
                </div>
              ))}
              {k.workers.length === 0 && <div className="text-sm text-zinc-500">Keine Worker aktiv.</div>}
              <div className="pt-2 flex items-center justify-between text-xs text-zinc-500">
                <span>Warteschlangen:</span>
                <span className="tabular-nums">
                  cpu {k.warteschlangen.cpu ?? 0} · gpu {k.warteschlangen.gpu ?? 0} · scan {k.warteschlangen.scan ?? 0} · video {k.warteschlangen.video ?? 0}
                </span>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

function Stat({ label, val, tone }: { label: string; val: number | string; tone?: 'ok' | 'warn' | 'info' }) {
  const cls = tone === 'warn' ? 'text-amber-600 dark:text-amber-400'
    : tone === 'info' ? 'text-indigo-600 dark:text-indigo-400'
    : 'text-zinc-900 dark:text-zinc-100'
  return (
    <div>
      <div className={`text-2xl font-semibold tabular-nums ${cls}`}>
        {typeof val === 'number' ? fmt(val) : val}
      </div>
      <div className="text-xs text-zinc-500">{label}</div>
    </div>
  )
}

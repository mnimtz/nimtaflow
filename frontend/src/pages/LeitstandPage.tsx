import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../lib/api'
import { Image as ImageIcon, FileText, Film, Layers, Users, Sparkles, Clock, MapPin, RefreshCw } from 'lucide-react'
import PipelinePage from './PipelinePage'

type Role = {
  role: string; label: string; pending: number; done?: number
  workers: number; avg_dur: number | null; eta_seconds: number | null
}
type Worker = {
  name: string; role: string; last_seen: number; idle_s: number | null
  jobs: number; last_dur: number | null; avg_dur: number | null
}
type Lib = {
  photos: number; videos: number; images: number; described: number
  with_faces: number; named_persons: number; embeddings: number; thumbnails: number
}
type Status = { enabled: boolean; roles: Role[]; workers: Worker[]; library?: Lib }

// Display order = the actual processing chain.
const CHAIN = ['thumbnails', 'describe', 'transcode', 'video', 'embed', 'faces']
const BAR: Record<string, string> = {
  thumbnails: 'bg-amber-500', describe: 'bg-violet-500', transcode: 'bg-rose-500',
  video: 'bg-fuchsia-500', embed: 'bg-sky-500', faces: 'bg-emerald-500',
}

function fmtEta(s: number | null | undefined): string {
  if (s == null || s <= 0) return '—'
  if (s < 60) return `${Math.round(s)}s`
  if (s < 3600) return `${Math.round(s / 60)}m`
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}
const de = (n: number) => (n ?? 0).toLocaleString('de')

export default function LeitstandPage() {
  const [tab, setTab] = useState<'overview' | 'pipeline'>('overview')
  const { data, dataUpdatedAt } = useQuery<Status>({
    queryKey: ['leitstand'],
    queryFn: () => api.get('/remote/status').then(r => r.data),
    refetchInterval: 3000,
  })
  const { data: stats, refetch: refetchStats } = useQuery<any>({
    queryKey: ['photo-stats-leitstand'],
    queryFn: () => api.get('/photos/stats').then(r => r.data),
    refetchInterval: 5000,
  })
  const scanMeta = useMutation({
    mutationFn: () => api.post('/photos/scan-metadata').then(r => r.data),
    onSuccess: (d: any) => {
      refetchStats()
      alert(`${de(d?.candidates ?? 0)} Foto(s) werden auf Datum/GPS gescannt — Ergebnisse erscheinen in den nächsten Minuten.`)
    },
    onError: () => alert('Metadaten-Scan konnte nicht gestartet werden.'),
  })
  const roles = [...(data?.roles ?? [])].sort(
    (a, b) => CHAIN.indexOf(a.role) - CHAIN.indexOf(b.role))
  const workers = [...(data?.workers ?? [])].sort((a, b) => (a.idle_s ?? 1e9) - (b.idle_s ?? 1e9))
  const lib = data?.library
  const now = Math.floor(Date.now() / 1000)
  const totalEta = Math.max(0, ...roles.map(r => r.eta_seconds ?? 0))
  const activeWorkers = workers.filter(w => (w.idle_s ?? 999) < 30).length

  const libCards = lib ? [
    { icon: ImageIcon, label: 'Fotos', val: lib.images },
    { icon: Film, label: 'Videos', val: lib.videos },
    { icon: FileText, label: 'Beschrieben', val: lib.described },
    { icon: Users, label: 'Mit Gesichtern', val: lib.with_faces },
    { icon: Users, label: 'Benannte Personen', val: lib.named_persons },
    { icon: Sparkles, label: 'Embeddings', val: lib.embeddings },
    { icon: Layers, label: 'Thumbnails', val: lib.thumbnails },
  ] : []

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-6">
      <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {([['overview', 'Übersicht'], ['pipeline', 'Pipeline (Jobs)']] as const).map(([k, lbl]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 ${tab === k
              ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400'
              : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'}`}>
            {lbl}
          </button>
        ))}
      </div>
      {tab === 'pipeline' ? <PipelinePage /> : (<>
      {/* Header + Gesamt-ETA */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-zinc-900 dark:text-white">Leitstand</h1>
          <p className="text-xs text-zinc-400">
            Live-Status aller Worker & Pipelines · aktualisiert alle 3 s
            {dataUpdatedAt ? ` · zuletzt ${new Date(dataUpdatedAt).toLocaleTimeString('de')}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 dark:border-zinc-700 px-4 py-2">
          <Clock className="w-4 h-4 text-zinc-400" />
          <div className="text-right">
            <div className="text-[11px] text-zinc-400 leading-none">geschätzt fertig in</div>
            <div className="text-lg font-bold tabular-nums text-zinc-900 dark:text-white">{fmtEta(totalEta)}</div>
          </div>
        </div>
      </div>

      {/* Panel 0: Metadaten & GPS — Indikator + manueller Scan-Button */}
      {stats && (
        <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <MapPin className="w-5 h-5 text-emerald-500 shrink-0" />
              <div>
                <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Metadaten &amp; GPS</h2>
                {(stats.metadata_pending ?? 0) > 0 ? (
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    {de(stats.metadata_pending)} Foto(s) werden noch verarbeitet (Datum/GPS/Orte) — der Ordner-Scan ist fertig, die Verarbeitung läuft noch.
                  </p>
                ) : (
                  <p className="text-xs text-emerald-600 dark:text-emerald-400">
                    Alle Metadaten verarbeitet · {de(stats.with_gps)} Foto(s) mit GPS
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => scanMeta.mutate()}
              disabled={scanMeta.isPending}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors">
              <RefreshCw size={16} className={scanMeta.isPending ? 'animate-spin' : ''} />
              {scanMeta.isPending ? 'Wird gestartet…' : 'GPS/Metadaten jetzt scannen'}
            </button>
          </div>
          {(stats.metadata_pending ?? 0) > 0 && (stats.total_indexed ?? 0) > 0 && (
            <div className="mt-3 h-2 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
              <div className="h-full bg-emerald-500 transition-all"
                style={{ width: `${Math.max(2, Math.round(100 * (1 - stats.metadata_pending / stats.total_indexed)))}%` }} />
            </div>
          )}
        </section>
      )}

      {/* Panel 1: Pipeline-Kette */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Verarbeitungs-Kette</h2>
        <div className="space-y-3">
          {roles.map(r => {
            const done = r.done ?? 0, pend = r.pending ?? 0, tot = done + pend
            const pct = tot > 0 ? Math.round((done / tot) * 100) : 100
            const jpm = r.workers && r.avg_dur ? Math.round((r.workers * 60) / r.avg_dur) : null
            return (
              <div key={r.role}>
                <div className="flex items-center justify-between text-sm mb-1 flex-wrap gap-x-3">
                  <span className="font-medium text-zinc-800 dark:text-zinc-200">{r.label}</span>
                  <div className="flex gap-3 text-xs text-zinc-500 tabular-nums">
                    <span><b className="text-zinc-700 dark:text-zinc-300">{de(pend)}</b> offen</span>
                    <span>{de(done)} fertig</span>
                    <span>{r.workers} Worker</span>
                    {jpm != null && <span>{jpm}/min</span>}
                    {r.avg_dur != null && <span>Ø {r.avg_dur.toFixed(1)}s</span>}
                    <span>Rest <b className="text-zinc-700 dark:text-zinc-300">{fmtEta(r.eta_seconds)}</b></span>
                  </div>
                </div>
                <div className="h-2.5 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                  <div className={`h-full ${BAR[r.role] ?? 'bg-zinc-500'} transition-all`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
          {roles.length === 0 && <p className="text-sm text-zinc-400">Keine aktiven Pipelines.</p>}
        </div>
      </section>

      {/* Panel 2: Worker-Flotte */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">Worker-Flotte</h2>
          <span className="text-xs text-zinc-400">{activeWorkers} aktiv · {workers.length} verbunden</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {workers.map(w => {
            const idle = w.idle_s ?? Math.max(0, now - w.last_seen)
            const live = idle < 30
            return (
              <div key={w.name} className="rounded-xl border border-zinc-200 dark:border-zinc-700 p-3">
                <div className="flex items-center gap-2">
                  <span className={live ? 'text-emerald-500' : 'text-zinc-400'}>●</span>
                  <b className="text-sm text-zinc-800 dark:text-zinc-200 truncate">{w.name}</b>
                </div>
                <div className="mt-1.5 text-[11px] text-zinc-500 space-y-0.5 tabular-nums">
                  <div>{w.role} · <b className="text-zinc-700 dark:text-zinc-300">{de(w.jobs)}</b> Jobs</div>
                  <div>Ø {w.avg_dur != null ? `${w.avg_dur.toFixed(1)}s` : '—'}{w.last_dur != null ? ` · zuletzt ${w.last_dur.toFixed(1)}s` : ''}</div>
                  <div className="text-zinc-400">{live ? 'arbeitet gerade' : `idle · vor ${idle}s`}</div>
                </div>
              </div>
            )
          })}
          {workers.length === 0 && <p className="text-sm text-zinc-400 col-span-full">Kein Worker verbunden.</p>}
        </div>
      </section>

      {/* Panel 3: Bibliothek-Kennzahlen */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">Bibliothek</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {libCards.map(({ icon: Icon, label, val }) => (
            <div key={label} className="rounded-xl bg-zinc-50 dark:bg-zinc-800/50 p-3 text-center">
              <Icon className="w-4 h-4 mx-auto text-zinc-400" />
              <div className="mt-1 text-xl font-bold tabular-nums text-zinc-900 dark:text-white">{de(val)}</div>
              <div className="text-[11px] text-zinc-400 leading-tight">{label}</div>
            </div>
          ))}
          {!lib && <p className="text-sm text-zinc-400 col-span-full">Lade Kennzahlen…</p>}
        </div>
      </section>
      </>)}
    </div>
  )
}

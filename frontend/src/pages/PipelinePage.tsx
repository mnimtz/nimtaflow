import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { RefreshCw, CheckCircle, XCircle, SkipForward, Users, Sparkles, Brain, DollarSign, AlertTriangle } from 'lucide-react'
import { api, Job } from '../lib/api'

type Stats = { total?: number; by_status?: Record<string, number>; coverage?: Record<string, number> }

export default function PipelinePage() {
  const { data: jobs = [], refetch } = useQuery<Job[]>({
    queryKey: ['jobs'],
    queryFn: () => api.get('/jobs').then((r) => r.data),
    refetchInterval: 3000,
  })

  const { data: stats, refetch: refetchStats } = useQuery<Stats>({
    queryKey: ['photo-stats'],
    queryFn: () => api.get('/photos/stats').then((r) => r.data),
    refetchInterval: 3000,
  })
  const st = stats?.by_status ?? {}
  const cov = stats?.coverage ?? {}
  const total = stats?.total ?? 0
  const [busy, setBusy] = useState('')

  const act = useMutation({
    mutationFn: ({ url }: { url: string }) => api.post(url).then(r => r.data),
    onSuccess: (d: any) => { setBusy(''); refetch(); refetchStats(); alert(`${d?.reprocessing ?? d?.new_persons ?? d?.clustered ?? 'OK'} — Aktion gestartet.`) },
    onError: () => setBusy(''),
  })
  const doAct = (key: string, url: string) => { setBusy(key); act.mutate({ url }) }

  const activeJob = jobs.find((j) => j.status === 'running' || j.status === 'queued')
  const recentJobs = jobs.filter((j) => j.status !== 'running' && j.status !== 'queued').slice(0, 10)

  return (
    <div className="p-4 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Verarbeitungs-Pipeline</h1>
        <button
          onClick={() => api.post('/sources/scan-all').then(() => refetch())}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <RefreshCw size={16} />
          Alle Ordner scannen
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {([
          { k: 'pending', label: 'Wartend', cls: 'text-amber-500' },
          { k: 'processing', label: 'In Arbeit', cls: 'text-indigo-500' },
          { k: 'done', label: 'Fertig', cls: 'text-emerald-500' },
          { k: 'error', label: 'Fehler', cls: 'text-red-500' },
        ] as const).map(s => (
          <div key={s.k} className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-4">
            <p className={`text-2xl font-bold tabular-nums ${s.cls}`}>{st[s.k] ?? 0}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Stage coverage */}
      <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">Verarbeitungs-Abdeckung <span className="text-gray-400 font-normal">({total.toLocaleString('de')} Fotos)</span></h2>
        <div className="space-y-3">
          {([
            { k: 'thumbnailed', label: 'Thumbnails', icon: CheckCircle, cls: 'bg-emerald-500' },
            { k: 'described', label: 'KI-Beschreibung', icon: Brain, cls: 'bg-violet-500' },
            { k: 'embedded', label: 'Suchindex (Embedding)', icon: Sparkles, cls: 'bg-indigo-500' },
            { k: 'with_faces', label: 'Gesichter erkannt', icon: Users, cls: 'bg-sky-500' },
          ] as const).map(r => {
            const v = cov[r.k] ?? 0
            const pct = total ? Math.round((v / total) * 100) : 0
            return (
              <div key={r.k} className="flex items-center gap-3">
                <r.icon size={15} className="text-gray-400 shrink-0" />
                <span className="text-sm text-gray-600 dark:text-gray-300 w-44 shrink-0">{r.label}</span>
                <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div className={`h-full ${r.cls} rounded-full transition-all`} style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs tabular-nums text-gray-500 w-24 text-right shrink-0">{v.toLocaleString('de')} · {pct}%</span>
              </div>
            )
          })}
          {(cov.ai_error ?? 0) > 0 && (
            <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 pt-1"><AlertTriangle size={13} /> {cov.ai_error} Fotos mit KI-Fehler (z. B. Provider überlastet) — „KI nachholen" oder „Fehler erneut".</p>
          )}
        </div>
        {/* Actions */}
        <div className="flex flex-wrap gap-2 mt-5 pt-4 border-t border-gray-200 dark:border-gray-800">
          <ActBtn label="Fehler erneut" busy={busy === 'failed'} onClick={() => doAct('failed', '/photos/reprocess-failed')} />
          <ActBtn label="KI nachholen" busy={busy === 'ai'} onClick={() => doAct('ai', '/photos/reprocess-missing-ai')} />
          <ActBtn label="Gesichter clustern" busy={busy === 'cluster'} onClick={() => doAct('cluster', '/people/cluster')} />
        </div>
      </div>

      {activeJob ? <ActiveJobCard job={activeJob} /> : (
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-6 text-center text-gray-500 dark:text-gray-400 text-sm">
          Keine aktive Verarbeitung — starte die Pipeline um Fotos zu verarbeiten.
        </div>
      )}

      {recentJobs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Letzte Läufe</h2>
          <div className="space-y-2">
            {recentJobs.map((j) => <JobRow key={j.id} job={j} />)}
          </div>
        </div>
      )}

      <LiveLog />
    </div>
  )
}

function ActBtn({ label, busy, onClick }: { label: string; busy: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} disabled={busy}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50">
      <RefreshCw size={13} className={busy ? 'animate-spin' : ''} /> {label}
    </button>
  )
}

function ActiveJobCard({ job }: { job: Job }) {
  const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0

  return (
    <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold text-gray-900 dark:text-white">{job.name}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {job.processed.toLocaleString('de')} / {job.total.toLocaleString('de')} Fotos
            {job.speed_per_min ? ` · ${Math.round(job.speed_per_min)} Fotos/min` : ''}
          </p>
        </div>
        <StatusBadge status={job.status} />
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-indigo-600 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-sm text-right text-gray-500 dark:text-gray-400">{pct}%</p>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatChip icon={<CheckCircle size={14} className="text-green-500" />} label="Verarbeitet" value={job.processed} />
        <StatChip icon={<XCircle size={14} className="text-red-500" />} label="Fehler" value={job.errors} />
        <StatChip icon={<SkipForward size={14} className="text-yellow-500" />} label="Übersprungen" value={job.skipped} />
        <StatChip icon={<DollarSign size={14} className="text-blue-500" />} label="Kosten" value={`$${job.api_cost_usd.toFixed(2)}`} />
      </div>
    </div>
  )
}

function StatChip({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return (
    <div className="flex items-center gap-2 p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
      {icon}
      <div>
        <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
        <p className="text-sm font-semibold text-gray-900 dark:text-white">{typeof value === 'number' ? value.toLocaleString('de') : value}</p>
      </div>
    </div>
  )
}

function JobRow({ job }: { job: Job }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm">
      <div>
        <span className="font-medium text-gray-900 dark:text-white">{job.name}</span>
        <span className="text-gray-400 ml-2">{job.processed.toLocaleString('de')} Fotos</span>
      </div>
      <StatusBadge status={job.status} />
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    running: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
    queued: 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300',
    done: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
    error: 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300',
    cancelled: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
  }
  const labels: Record<string, string> = {
    running: 'Läuft', queued: 'Warteschlange', done: 'Fertig', error: 'Fehler', cancelled: 'Abgebrochen',
  }
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${map[status] ?? map.cancelled}`}>
      {labels[status] ?? status}
    </span>
  )
}

function LiveLog() {
  const [logs, setLogs] = useState<string[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.host}/api/jobs/ws`)
    wsRef.current = ws
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.message) {
        setLogs((prev) => [...prev.slice(-200), `${new Date().toLocaleTimeString('de')}  ${data.message}`])
      }
    }
    return () => ws.close()
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs])

  if (logs.length === 0) return null

  return (
    <div>
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">Live-Log</h2>
      <div className="rounded-xl bg-gray-950 text-gray-300 font-mono text-xs p-4 h-64 overflow-y-auto space-y-0.5">
        {logs.map((l, i) => <div key={i}>{l}</div>)}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

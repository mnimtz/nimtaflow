import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { RefreshCw, CheckCircle, XCircle, SkipForward, Users, Sparkles, Brain, DollarSign, AlertTriangle } from 'lucide-react'
import { api, Job } from '../lib/api'
import { useT } from '../i18n'

type Stats = { total?: number; total_indexed?: number; by_status?: Record<string, number>; coverage?: Record<string, number> }

export default function PipelinePage() {
  const { t } = useT()
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
  // coverage % is against ALL indexed photos (thumbnails run before "done", so
  // using the done-count as denominator over-counts during a scan).
  const total = stats?.total_indexed ?? stats?.total ?? 0
  const [busy, setBusy] = useState('')

  const act = useMutation({
    mutationFn: ({ url }: { url: string }) => api.post(url).then(r => r.data),
    onSuccess: (d: any) => { setBusy(''); refetch(); refetchStats(); alert(t('pipeline.actionStarted', { result: d?.reprocessing ?? d?.new_persons ?? d?.clustered ?? 'OK' })) },
    onError: () => setBusy(''),
  })
  const doAct = (key: string, url: string) => { setBusy(key); act.mutate({ url }) }

  const activeJob = jobs.find((j) => j.status === 'running' || j.status === 'queued')
  const recentJobs = jobs.filter((j) => j.status !== 'running' && j.status !== 'queued').slice(0, 10)

  return (
    <div className="p-4 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">{t('pipeline.title')}</h1>
        <button
          onClick={() => api.post('/sources/scan-all').then(() => refetch())}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <RefreshCw size={16} />
          {t('pipeline.scanAll')}
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {([
          { k: 'pending', label: t('pipeline.statPending'), cls: 'text-amber-500' },
          { k: 'processing', label: t('pipeline.statProcessing'), cls: 'text-indigo-500' },
          { k: 'done', label: t('pipeline.statDone'), cls: 'text-emerald-500' },
          { k: 'error', label: t('pipeline.statError'), cls: 'text-red-500' },
        ] as const).map(s => (
          <div key={s.k} className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-4">
            <p className={`text-2xl font-bold tabular-nums ${s.cls}`}>{st[s.k] ?? 0}</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Stage coverage */}
      <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
        <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">{t('pipeline.coverage')} <span className="text-gray-400 font-normal">{t('pipeline.coverageCount', { n: total.toLocaleString('de') })}</span></h2>
        <div className="space-y-3">
          {([
            { k: 'thumbnailed', label: t('pipeline.covThumbnails'), icon: CheckCircle, cls: 'bg-emerald-500' },
            { k: 'described', label: t('pipeline.covDescribed'), icon: Brain, cls: 'bg-violet-500' },
            { k: 'embedded', label: t('pipeline.covEmbedded'), icon: Sparkles, cls: 'bg-indigo-500' },
            { k: 'with_faces', label: t('pipeline.covFaces'), icon: Users, cls: 'bg-sky-500' },
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
            <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400 pt-1"><AlertTriangle size={13} /> {t('pipeline.aiError', { n: cov.ai_error })}</p>
          )}
        </div>
        {/* Actions */}
        <div className="flex flex-wrap gap-2 mt-5 pt-4 border-t border-gray-200 dark:border-gray-800">
          <ActBtn label={t('pipeline.retryErrors')} busy={busy === 'failed'} onClick={() => doAct('failed', '/photos/reprocess-failed')} />
          <ActBtn label={t('pipeline.catchupAi')} busy={busy === 'ai'} onClick={() => doAct('ai', '/photos/reprocess-missing-ai')} />
          <ActBtn label={t('pipeline.clusterFaces')} busy={busy === 'cluster'} onClick={() => doAct('cluster', '/people/cluster')} />
        </div>
      </div>

      {activeJob ? <ActiveJobCard job={activeJob} /> : (
        <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-6 text-center text-gray-500 dark:text-gray-400 text-sm">
          {t('pipeline.noActive')}
        </div>
      )}

      {recentJobs.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{t('pipeline.recentRuns')}</h2>
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
  const { t } = useT()
  const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0

  return (
    <div className="rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-semibold text-gray-900 dark:text-white">{job.name}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {t('pipeline.jobPhotos', { processed: job.processed.toLocaleString('de'), total: job.total.toLocaleString('de') })}
            {job.speed_per_min ? t('pipeline.jobPerMin', { n: Math.round(job.speed_per_min) }) : ''}
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
        <StatChip icon={<CheckCircle size={14} className="text-green-500" />} label={t('pipeline.statProcessed')} value={job.processed} />
        <StatChip icon={<XCircle size={14} className="text-red-500" />} label={t('pipeline.statErrors')} value={job.errors} />
        <StatChip icon={<SkipForward size={14} className="text-yellow-500" />} label={t('pipeline.statSkipped')} value={job.skipped} />
        <StatChip icon={<DollarSign size={14} className="text-blue-500" />} label={t('pipeline.statCost')} value={`$${job.api_cost_usd.toFixed(2)}`} />
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
  const { t } = useT()
  return (
    <div className="flex items-center justify-between px-4 py-3 rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm">
      <div>
        <span className="font-medium text-gray-900 dark:text-white">{job.name}</span>
        <span className="text-gray-400 ml-2">{t('pipeline.rowPhotos', { n: job.processed.toLocaleString('de') })}</span>
      </div>
      <StatusBadge status={job.status} />
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useT()
  const map: Record<string, string> = {
    running: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
    queued: 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-300',
    done: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
    error: 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300',
    cancelled: 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400',
  }
  const labels: Record<string, string> = {
    running: t('pipeline.badgeRunning'), queued: t('pipeline.badgeQueued'), done: t('pipeline.badgeDone'), error: t('pipeline.badgeError'), cancelled: t('pipeline.badgeCancelled'),
  }
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${map[status] ?? map.cancelled}`}>
      {labels[status] ?? status}
    </span>
  )
}

function LiveLog() {
  const { t } = useT()
  const [logs, setLogs] = useState<string[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Derive ws/wss from the page scheme — a hardcoded ws:// throws a mixed-content
    // SecurityError on an HTTPS deployment, which (without an ErrorBoundary) blanked
    // the whole Pipeline page.
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/api/jobs/ws`)
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
      <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{t('pipeline.liveLog')}</h2>
      <div className="rounded-xl bg-gray-950 text-gray-300 font-mono text-xs p-4 h-64 overflow-y-auto space-y-0.5">
        {logs.map((l, i) => <div key={i}>{l}</div>)}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

import { useQuery, useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../lib/api'
import { useT } from '../i18n'
import { Image as ImageIcon, FileText, Film, Layers, Users, Sparkles, Clock, MapPin, RefreshCw, FileCode } from 'lucide-react'
import PipelinePage from './PipelinePage'

type Role = {
  role: string; label: string; pending: number; done?: number
  workers: number; avg_dur: number | null; eta_seconds: number | null
}
type Worker = {
  name: string; role: string; last_seen: number; idle_s: number | null
  jobs: number; last_dur: number | null; avg_dur: number | null
}
type LocalTask = {
  worker: string; worker_label: string; queue: string
  task: string; task_label: string; photo_id: number | null; started_at: number | null
}
type Lib = {
  photos: number; videos: number; images: number; described: number
  with_faces: number; named_persons: number; embeddings: number; thumbnails: number
  faces_total?: number; faces_assigned?: number; faces_unassigned?: number
}
type Status = { enabled: boolean; roles: Role[]; workers: Worker[]; local_active?: LocalTask[]; library?: Lib }

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
  const { t } = useT()
  const [tab, setTab] = useState<'overview' | 'pipeline'>('overview')
  const { data, dataUpdatedAt } = useQuery<Status>({
    queryKey: ['leitstand'],
    queryFn: () => api.get('/remote/status').then(r => r.data),
    refetchInterval: 3000,
  })
  const { data: backfill } = useQuery<any>({
    queryKey: ['backfill-progress'],
    queryFn: () => api.get('/remote/backfill-progress').then(r => r.data),
    refetchInterval: (q) => (q.state.data?.running ? 4000 : 15000),
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
      alert(t('leitstand.scanStarted', { n: de(d?.candidates ?? 0) }))
    },
    onError: () => alert(t('leitstand.scanFailed')),
  })
  const roles = [...(data?.roles ?? [])].sort(
    (a, b) => CHAIN.indexOf(a.role) - CHAIN.indexOf(b.role))
  const workers = [...(data?.workers ?? [])].sort((a, b) => (a.idle_s ?? 1e9) - (b.idle_s ?? 1e9))
  const localActive = data?.local_active ?? []
  // Group local tasks by worker_label → virtual "server worker" cards
  const localByWorker = localActive.reduce<Record<string, LocalTask[]>>((acc, t) => {
    ;(acc[t.worker_label] ??= []).push(t); return acc
  }, {})
  // Order local workers: GPU first, then Video, then CPU, then rest
  const LOCAL_ORDER = ['GPU (Server)', 'Video (Server)', 'CPU (Server)', 'Scan (Server)']
  const localWorkerCards = Object.entries(localByWorker).sort(
    ([a], [b]) => (LOCAL_ORDER.indexOf(a) ?? 99) - (LOCAL_ORDER.indexOf(b) ?? 99))
  const lib = data?.library
  const now = Math.floor(Date.now() / 1000)
  const totalEta = Math.max(0, ...roles.map(r => r.eta_seconds ?? 0))
  const activeWorkers = workers.filter(w => (w.idle_s ?? 999) < 30).length + localWorkerCards.length

  const facesPct = lib?.faces_total ? Math.round(100 * (lib.faces_assigned ?? 0) / lib.faces_total) : 0
  const libCards: { icon: any; label: string; val: number; sub?: string }[] = lib ? [
    { icon: ImageIcon, label: t('leitstand.libPhotos'), val: lib.images },
    { icon: Film, label: t('leitstand.libVideos'), val: lib.videos },
    { icon: FileText, label: t('leitstand.libDescribed'), val: lib.described },
    { icon: Users, label: t('leitstand.libWithFaces'), val: lib.with_faces },
    { icon: Users, label: t('leitstand.libFacesAssigned'), val: lib.faces_assigned ?? 0, sub: `${facesPct}% · ${de(lib.faces_total ?? 0)}` },
    { icon: Users, label: t('leitstand.libFacesFree'), val: lib.faces_unassigned ?? 0 },
    { icon: Users, label: t('leitstand.libNamedPersons'), val: lib.named_persons },
    { icon: Sparkles, label: t('leitstand.libEmbeddings'), val: lib.embeddings },
    { icon: Layers, label: t('leitstand.libThumbnails'), val: lib.thumbnails },
  ] : []

  return (
    <div className="p-4 max-w-6xl mx-auto space-y-6">
      <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {([['overview', t('leitstand.tabOverview')], ['pipeline', t('leitstand.tabPipeline')]] as const).map(([k, lbl]) => (
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
          <h1 className="text-xl font-bold text-zinc-900 dark:text-white">{t('leitstand.title')}</h1>
          <p className="text-xs text-zinc-400">
            {t('leitstand.headerInfo')}
            {dataUpdatedAt ? t('leitstand.lastUpdate', { time: new Date(dataUpdatedAt).toLocaleTimeString('de') }) : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-zinc-200 dark:border-zinc-700 px-4 py-2">
          <Clock className="w-4 h-4 text-zinc-400" />
          <div className="text-right">
            <div className="text-[11px] text-zinc-400 leading-none">{t('leitstand.etaLabel')}</div>
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
                <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{t('leitstand.metadataGps')}</h2>
                {(stats.metadata_pending ?? 0) > 0 ? (
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    {t('leitstand.metadataPending', { n: de(stats.metadata_pending) })}
                  </p>
                ) : (
                  <p className="text-xs text-emerald-600 dark:text-emerald-400">
                    {t('leitstand.metadataDone', { n: de(stats.with_gps) })}
                  </p>
                )}
              </div>
            </div>
            <button
              onClick={() => scanMeta.mutate()}
              disabled={scanMeta.isPending}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors">
              <RefreshCw size={16} className={scanMeta.isPending ? 'animate-spin' : ''} />
              {scanMeta.isPending ? t('leitstand.scanning') : t('leitstand.scanNow')}
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

      {/* Panel 0b: EXIF/Sidecar Backfill-Fortschritt */}
      {backfill && (backfill.running || backfill.finished || backfill.total > 0) && (
        <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
          <div className="flex items-center gap-3 mb-3">
            <FileCode className={`w-5 h-5 shrink-0 ${backfill.running ? 'text-violet-500 animate-pulse' : backfill.finished ? 'text-emerald-500' : 'text-zinc-400'}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">
                  {t('leitstand.backfillTitle')}
                  <span className="ml-2 text-xs font-normal text-zinc-400">
                    {backfill.full ? t('leitstand.backfillFull') : t('leitstand.backfillIncr')}
                  </span>
                </h2>
                <div className="flex items-center gap-3 text-xs text-zinc-500 tabular-nums">
                  <span><b className="text-zinc-700 dark:text-zinc-300">{(backfill.done ?? 0).toLocaleString('de')}</b> / {(backfill.total ?? 0).toLocaleString('de')}</span>
                  {backfill.failed > 0 && <span className="text-amber-500">{t('leitstand.backfillFailed', { n: backfill.failed })}</span>}
                  {backfill.running && backfill.eta_s != null && <span className="text-violet-500">{t('leitstand.backfillEta', { eta: fmtEta(backfill.eta_s) })}</span>}
                  {backfill.running && backfill.elapsed_s != null && <span className="text-zinc-400">{t('leitstand.backfillElapsed', { t: fmtEta(backfill.elapsed_s) })}</span>}
                </div>
              </div>
              <p className="text-xs mt-0.5 text-zinc-500">
                {backfill.running ? t('leitstand.backfillRunning') : backfill.finished ? t('leitstand.backfillDone') : t('leitstand.backfillIdle')}
              </p>
            </div>
          </div>
          <div className="h-2.5 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
            <div
              className={`h-full transition-all ${backfill.finished ? 'bg-emerald-500' : 'bg-violet-500'}`}
              style={{ width: `${Math.max(backfill.total > 0 ? 1 : 0, backfill.pct ?? 0)}%` }}
            />
          </div>
        </section>
      )}

      {/* Panel 1: Pipeline-Kette */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">{t('leitstand.processingChain')}</h2>
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
                    <span><b className="text-zinc-700 dark:text-zinc-300">{de(pend)}</b> {t('leitstand.open')}</span>
                    <span>{de(done)} {t('leitstand.done')}</span>
                    <span>{r.workers} {t('leitstand.workers')}</span>
                    {jpm != null && <span>{t('leitstand.perMin', { n: jpm })}</span>}
                    {r.avg_dur != null && <span>{t('leitstand.avg', { n: r.avg_dur.toFixed(1) })}</span>}
                    <span>{t('leitstand.remaining')} <b className="text-zinc-700 dark:text-zinc-300">{fmtEta(r.eta_seconds)}</b></span>
                  </div>
                </div>
                <div className="h-2.5 rounded-full bg-zinc-200 dark:bg-zinc-800 overflow-hidden">
                  <div className={`h-full ${BAR[r.role] ?? 'bg-zinc-500'} transition-all`} style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
          {roles.length === 0 && <p className="text-sm text-zinc-400">{t('leitstand.noPipelines')}</p>}
        </div>
      </section>

      {/* Panel 2: Worker-Flotte — Server (lokal) + Remote (Mac, etc.) */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">{t('leitstand.workerFleet')}</h2>
          <span className="text-xs text-zinc-400">{t('leitstand.workersStatus', { active: activeWorkers, total: localWorkerCards.length + workers.length })}</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {/* Server-Worker (aus Celery inspect active) */}
          {localWorkerCards.map(([label, tasks]) => (
            <div key={label} className="rounded-xl border border-indigo-200 dark:border-indigo-800 p-3">
              <div className="flex items-center gap-2">
                <span className="text-emerald-500 text-xs">●</span>
                <b className="text-sm text-zinc-800 dark:text-zinc-200 truncate">{label}</b>
                <span className="ml-auto text-[10px] text-indigo-400 font-medium">Server</span>
              </div>
              <div className="mt-1.5 space-y-1">
                {tasks.slice(0, 3).map((task, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px] text-zinc-500 tabular-nums">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 shrink-0" />
                    <span className="font-medium text-zinc-700 dark:text-zinc-300 truncate">{task.task_label}</span>
                    {task.photo_id && <span className="text-zinc-400">#{task.photo_id}</span>}
                    {task.started_at && <span className="ml-auto text-zinc-400">{Math.round(now - task.started_at)}s</span>}
                  </div>
                ))}
                {tasks.length > 3 && (
                  <div className="text-[10px] text-zinc-400">+{tasks.length - 3} weitere</div>
                )}
              </div>
            </div>
          ))}
          {/* Remote-Worker (Mac, externe Maschinen via Redis-Heartbeat) */}
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
                  <div>{w.role} · <b className="text-zinc-700 dark:text-zinc-300">{de(w.jobs)}</b> {t('leitstand.jobs')}</div>
                  <div>Ø {w.avg_dur != null ? `${w.avg_dur.toFixed(1)}s` : '—'}{w.last_dur != null ? t('leitstand.lastDur', { n: w.last_dur.toFixed(1) }) : ''}</div>
                  <div className="text-zinc-400">{live ? t('leitstand.working') : t('leitstand.idle', { n: idle })}</div>
                </div>
              </div>
            )
          })}
          {localWorkerCards.length === 0 && workers.length === 0 && (
            <p className="text-sm text-zinc-400 col-span-full">{t('leitstand.noWorker')}</p>
          )}
        </div>
      </section>

      {/* Panel 3: Bibliothek-Kennzahlen */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-4">
        <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide mb-3">{t('leitstand.library')}</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {libCards.map(({ icon: Icon, label, val, sub }) => (
            <div key={label} className="rounded-xl bg-zinc-50 dark:bg-zinc-800/50 p-3 text-center">
              <Icon className="w-4 h-4 mx-auto text-zinc-400" />
              <div className="mt-1 text-xl font-bold tabular-nums text-zinc-900 dark:text-white">{de(val)}</div>
              <div className="text-[11px] text-zinc-400 leading-tight">{label}</div>
              {sub && <div className="text-[10px] text-indigo-500 dark:text-indigo-400 leading-tight mt-0.5">{sub}</div>}
            </div>
          ))}
          {!lib && <p className="text-sm text-zinc-400 col-span-full">{t('leitstand.loadingMetrics')}</p>}
        </div>
      </section>
      </>)}
    </div>
  )
}

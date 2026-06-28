import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UserPlus, Users, GitMerge, Trash2, Pencil, ArrowLeft, X, Eye, EyeOff,
  Check, Search, Star, Sparkles, Image as ImageIcon, Save, Mail, Phone, MapPin,
  Share2,
} from 'lucide-react'
import { api, thumbUrl } from '../lib/api'
import { differenceInYears } from 'date-fns'
import PhotoLightbox from '../components/gallery/PhotoLightbox'
import QuickNameOverlay from '../components/people/QuickNameOverlay'
import { Modal, useToast, useConfirm } from '../components/ui/dialogs'
import { useT } from '../i18n'

interface Person {
  id: number
  name: string
  alias?: string
  birthdate?: string
  relationship_type?: string
  profile_face_id?: number
  notes?: string
  email?: string
  phone?: string
  address?: string
  face_count: number
  photo_count?: number
  is_hidden?: boolean
  created_at: string
}
interface Photo { id: number; filename: string; taken_at?: string }
interface FaceRef { id: number; photo_id: number; confidence?: number }

const GRID = 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 xl:grid-cols-7 gap-x-4 gap-y-6'

// Shared, theme-aware control styles (chic + light/dark + touch-friendly)
const BTN_PRIMARY = 'flex items-center gap-2 px-3.5 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 active:scale-[0.98] transition shadow-sm'
const BTN_GHOST = 'flex items-center gap-2 px-3.5 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-300 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800 active:scale-[0.98] transition'
const BTN_GHOST_ACTIVE = 'flex items-center gap-2 px-3.5 py-2 rounded-xl border border-indigo-500 text-indigo-600 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950/30 text-sm hover:bg-indigo-100 dark:hover:bg-indigo-950/50 active:scale-[0.98] transition'
const INPUT = 'w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-indigo-500'

export default function PeoplePage() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showHidden, setShowHidden] = useState(false)
  const [sort, setSort] = useState('photos')
  const [selectMode, setSelectMode] = useState(false)
  const [selection, setSelection] = useState<Set<number>>(new Set())
  const [showAdd, setShowAdd] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [assignIds, setAssignIds] = useState<number[] | null>(null)
  const [showIgnored, setShowIgnored] = useState(false)
  const [quickName, setQuickName] = useState(false)
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { t } = useT()

  const { data: people = [], isLoading } = useQuery<Person[]>({
    queryKey: ['people', showHidden, sort],
    queryFn: () => api.get('/people', { params: { include_hidden: showHidden, sort } }).then(r => r.data),
  })
  const [loosePage, setLoosePage] = useState(1)
  const [loosePageSize, setLoosePageSize] = useState(50)
  const { data: looseData } = useQuery<{ total: number; items: FaceRef[] }>({
    queryKey: ['unassigned-faces', loosePage, loosePageSize],
    queryFn: () => api.get('/people/faces/unassigned', { params: { page: loosePage, limit: loosePageSize } }).then(r => r.data),
  })
  const looseFaces = looseData?.items ?? []
  const looseTotal = looseData?.total ?? 0
  const { data: ignoredFaces = [] } = useQuery<FaceRef[]>({
    queryKey: ['ignored-faces'],
    queryFn: () => api.get('/people/faces/ignored').then(r => r.data),
    enabled: showIgnored,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['people'] })
    qc.invalidateQueries({ queryKey: ['unassigned-faces'] })
    qc.invalidateQueries({ queryKey: ['ignored-faces'] })
  }

  const [faceSel, setFaceSel] = useState<Set<number>>(new Set())
  // Click a suggestion/face → see the FULL photo big (verify even when the face crop
  // is a low-quality video frame). Holds {face_id, photo_id, name, score}.
  const [bigFace, setBigFace] = useState<{ id: number; photo_id: number; name?: string; score?: number } | null>(null)
  const [pview, setPview] = useState<'personen' | 'vorschlaege' | 'gesichter' | 'verborgen'>('personen')
  const toggleFace = (id: number) =>
    setFaceSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const ignoreFaces = useMutation({
    mutationFn: ({ ids, ignored }: { ids: number[]; ignored: boolean }) =>
      api.post('/people/faces/ignore', { face_ids: ids }, { params: { ignored } }),
    onSuccess: (_d, v) => {
      refresh(); setFaceSel(new Set())
      toast(v.ignored ? t('people.toastFacesHidden', { count: v.ids.length }) : t('people.toastFacesShown', { count: v.ids.length }), 'success')
    },
  })

  const hideMutation = useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) =>
      api.post(`/people/${id}/hide`, null, { params: { hidden } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['people'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/people/${id}`),
    onSuccess: () => { refresh(); toast(t('people.toastPersonDeleted'), 'success') },
  })
  const clusterMutation = useMutation({
    // Endpoint dispatcht jetzt einen Celery-Task (cpu-Queue) und kehrt sofort mit
    // {status:"queued"} zurück — kein synchrones Ergebnis mehr (heavy DBSCAN raus
    // aus dem API-Prozess). Ergebnis erscheint nach dem Lauf in der Personenliste.
    mutationFn: () => api.post('/people/cluster').then(r => r.data),
    onSuccess: () => {
      toast(t('people.toastClusterStarted'), 'success')
    },
    onError: () => toast(t('people.toastClusterFailed'), 'error'),
  })

  // Button-driven: persist every detected face as an MWG region (box + name
  // where known) into the files. Done explicitly once clustering/naming has
  // settled — unknown faces keep their coordinates so a future tool never has
  // to re-run face detection.
  const writeNamesMutation = useMutation({
    mutationFn: () => api.post('/people/write-faces').then(r => r.data),
    onSuccess: (d: { queued_photos: number }) =>
      toast(t('people.toastWriteFacesQueued', { count: d.queued_photos }), 'success'),
    onError: () => toast(t('people.toastWriteFacesFailed'), 'error'),
  })

  // Server-side parallel face detection (insightface, CPU) — decoupled from the
  // slow descriptions so faces finish in hours, independent of the AI backlog.
  const detectFacesMutation = useMutation({
    mutationFn: () => api.post('/people/detect-faces-local').then(r => r.data),
    onSuccess: (d: { queued_photos: number }) => {
      refresh()
      toast(t('people.toastDetectStarted', { count: d.queued_photos }), 'success')
    },
    onError: () => toast(t('people.toastDetectFailed'), 'error'),
  })

  // Pre-generate the face-crop cache so opening a person (esp. with video faces,
  // which otherwise ffmpeg a frame per crop on first view) is instant.
  const { data: cropStatus } = useQuery<{ total_faces: number; cached: number }>({
    queryKey: ['crops-status'],
    queryFn: () => api.get('/people/crops-status').then(r => r.data),
    refetchInterval: 6000,
  })
  // Borderline ArcFace matches the user confirms with one tap ("Ist das Marcus?").
  const { data: suggestData } = useQuery<{ groups: { person_id: number; name: string; count: number; avg_score: number; faces: { id: number; photo_id: number; score: number }[] }[] }>({
    queryKey: ['face-suggestions'],
    queryFn: () => api.get('/people/faces/suggestions').then(r => r.data),
    refetchInterval: 20000,
  })
  const sugGroups = suggestData?.groups ?? []
  const refreshSug = () => {
    qc.invalidateQueries({ queryKey: ['face-suggestions'] })
    qc.invalidateQueries({ queryKey: ['people'] })
    qc.invalidateQueries({ queryKey: ['unassigned-faces'] })
  }
  const confirmGroup = useMutation({
    mutationFn: (pid: number) => api.post(`/people/suggestions/confirm/${pid}`).then(r => r.data),
    onSuccess: (d: { confirmed: number }) => { toast(t('people.toastConfirmed', { count: d.confirmed }), 'success'); refreshSug() },
  })
  const rejectGroup = useMutation({
    mutationFn: (pid: number) => api.post(`/people/suggestions/reject/${pid}`).then(r => r.data),
    onSuccess: (d: { rejected: number }) => { toast(t('people.toastRejected', { count: d.rejected }), 'success'); refreshSug() },
  })
  const confirmFace = useMutation({
    mutationFn: (id: number) => api.post(`/people/faces/${id}/confirm-suggestion`).then(r => r.data),
    onSuccess: refreshSug,
  })
  const rejectFace = useMutation({
    mutationFn: (id: number) => api.post(`/people/faces/${id}/reject-suggestion`).then(r => r.data),
    onSuccess: refreshSug,
  })
  const suggestMutation = useMutation({
    mutationFn: () => api.post('/people/suggest').then(r => r.data),
    onSuccess: () => toast(t('people.toastSuggestQueued'), 'success'),
  })
  const warmCropsMutation = useMutation({
    mutationFn: () => api.post('/people/warm-crops').then(r => r.data),
    onSuccess: (d: { queued_faces: number }) =>
      toast(t('people.toastWarmCropsQueued', { count: d.queued_faces }), 'success'),
    onError: () => toast(t('people.toastWarmCropsFailed'), 'error'),
  })

  const known = useMemo(() => people.filter(p => (p.name || '').trim()), [people])
  const unknown = useMemo(() => people.filter(p => !(p.name || '').trim()), [people])
  const selectedPeople = people.filter(p => selection.has(p.id))

  const toggleSelect = (id: number) =>
    setSelection(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const clearSelection = () => { setSelection(new Set()); setSelectMode(false) }

  const bulkHide = async (hidden: boolean) => {
    await Promise.all([...selection].map(id => api.post(`/people/${id}/hide`, null, { params: { hidden } })))
    qc.invalidateQueries({ queryKey: ['people'] })
    toast(hidden ? t('people.toastPersonsHidden', { count: selection.size }) : t('people.toastPersonsShown', { count: selection.size }), 'success')
    clearSelection()
  }

  if (selectedId !== null) {
    return (
      <PersonDetailView
        personId={selectedId}
        onBack={() => setSelectedId(null)}
        onDeleted={() => { setSelectedId(null); refresh() }}
        onOpenPerson={(id) => setSelectedId(id)}
      />
    )
  }

  const renderCard = (p: Person) => (
    <PersonCard
      key={p.id}
      person={p}
      knownPeople={known}
      selected={selection.has(p.id)}
      selectMode={selectMode}
      onOpen={() => { if (selectMode) toggleSelect(p.id); else setSelectedId(p.id) }}
      onToggleSelect={() => toggleSelect(p.id)}
      onToggleHidden={() => hideMutation.mutate({ id: p.id, hidden: !p.is_hidden })}
      onRenamed={() => qc.invalidateQueries({ queryKey: ['people'] })}
      onDelete={async () => {
        if (await confirm({ title: t('people.deleteConfirmTitle', { name: p.name || t('people.unknown') }), message: t('people.deleteConfirmMessage'), danger: true, confirmLabel: t('people.deleteLabel') }))
          deleteMutation.mutate(p.id)
      }}
    />
  )

  return (
    <div className="p-4 max-w-7xl mx-auto pb-24">
      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">{t('people.title')}</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('people.subtitleNamedUnknown', { named: known.length, unknown: unknown.length })}
            {cropStatus && cropStatus.total_faces > 0 && cropStatus.cached < cropStatus.total_faces && (
              <span>{t('people.cropsProgress', { cached: cropStatus.cached.toLocaleString(), total: cropStatus.total_faces.toLocaleString() })}</span>
            )}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <select value={sort} onChange={e => setSort(e.target.value)}
            title={t('people.sortTitle')}
            className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-zinc-700 dark:text-zinc-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="photos">{t('people.sortMostPhotos')}</option>
            <option value="photos_asc">{t('people.sortLeastPhotos')}</option>
            <option value="faces">{t('people.sortMostFaces')}</option>
            <option value="name">{t('people.sortName')}</option>
            <option value="recent">{t('people.sortRecent')}</option>
          </select>
          <button onClick={() => setQuickName(true)} title={t('people.quickNameTitle')}
            className="px-3 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
            {t('people.quickName')}
          </button>
          {selectMode ? (
            <button onClick={clearSelection} className={`${BTN_PRIMARY}`}>
              <X size={15} /> {t('people.done')}
            </button>
          ) : (
            <button onClick={() => setSelectMode(true)} className={BTN_GHOST}
              title={t('people.selectMergeTitle')}>
              <GitMerge size={15} /><span className="hidden sm:inline">{t('people.selectMerge')}</span><span className="sm:hidden">{t('people.select')}</span>
            </button>
          )}
          <button onClick={() => setShowHidden(v => !v)}
            className={showHidden ? BTN_GHOST_ACTIVE : BTN_GHOST}
            title={showHidden ? t('people.hideHiddenTitle') : t('people.showHiddenTitle')}>
            {showHidden ? <EyeOff size={15} /> : <Eye size={15} />}<span className="hidden sm:inline">{t('people.hidden')}</span>
          </button>
          <button onClick={() => clusterMutation.mutate()} disabled={clusterMutation.isPending}
            className={`${BTN_GHOST} disabled:opacity-50`}
            title={t('people.clusterTitle')}>
            <Sparkles size={15} /><span className="hidden sm:inline">{clusterMutation.isPending ? t('people.clustering') : t('people.cluster')}</span>
          </button>
          <button onClick={() => detectFacesMutation.mutate()} disabled={detectFacesMutation.isPending}
            className={`${BTN_GHOST} disabled:opacity-50`}
            title={t('people.detectFacesTitle')}>
            <Sparkles size={15} /><span className="hidden sm:inline">{detectFacesMutation.isPending ? t('people.starting') : t('people.detectFaces')}</span>
          </button>
          <button onClick={() => warmCropsMutation.mutate()} disabled={warmCropsMutation.isPending}
            className={`${BTN_GHOST} disabled:opacity-50`}
            title={t('people.warmCropsTitle')}>
            <ImageIcon size={15} /><span className="hidden sm:inline">{warmCropsMutation.isPending ? t('people.starting') : t('people.warmCrops')}</span>
          </button>
          <button onClick={() => writeNamesMutation.mutate()} disabled={writeNamesMutation.isPending}
            className={`${BTN_GHOST} disabled:opacity-50`}
            title={t('people.writeFacesTitle')}>
            <Save size={15} /><span className="hidden sm:inline">{writeNamesMutation.isPending ? t('people.writing') : t('people.writeFaces')}</span>
          </button>
          <button onClick={() => setShowAdd(true)} className={BTN_PRIMARY}>
            <UserPlus size={15} /><span className="hidden sm:inline">{t('people.add')}</span>
          </button>
        </div>
      </div>

      {selectMode && (
        <div className="mb-4 px-3.5 py-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 text-sm text-indigo-700 dark:text-indigo-300">
          {t('people.selectBanner')}
        </div>
      )}

      <details className="mb-4 text-sm rounded-xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 px-3.5 py-2.5">
        <summary className="cursor-pointer text-zinc-600 dark:text-zinc-300 select-none">{t('people.helpSummary')} <span className="text-zinc-400">{t('people.helpSummaryNote')}</span></summary>
        <ul className="mt-2 space-y-1 text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
          <li>• {t('people.helpDetect')}</li>
          <li>• {t('people.helpQuickName')}</li>
          <li>• {t('people.helpWarmCrops')}</li>
          <li>• {t('people.helpWriteFaces')}</li>
        </ul>
      </details>

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">{t('people.loading')}</div>
      ) : (people.length === 0 && looseTotal === 0) ? (
        <EmptyPeople />
      ) : (
        <div className="space-y-10">
          <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800 -mt-2 overflow-x-auto">
            {([
              ['personen', t('people.tabPeople', { count: known.length + unknown.length })],
              ['vorschlaege', sugGroups.reduce((a, g) => a + g.count, 0) ? t('people.tabSuggestionsCount', { count: sugGroups.reduce((a, g) => a + g.count, 0) }) : t('people.tabSuggestions')],
              ['gesichter', looseTotal ? t('people.tabUnknownFacesCount', { count: looseTotal }) : t('people.tabUnknownFaces')],
              ['verborgen', t('people.tabHidden')],
            ] as const).map(([k, lbl]) => (
              <button key={k} onClick={() => { setPview(k); if (k === 'verborgen') setShowIgnored(true) }}
                className={`px-3 py-2 text-sm font-medium -mb-px border-b-2 whitespace-nowrap ${pview === k ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'}`}>
                {lbl}
              </button>
            ))}
          </div>
          {pview === 'vorschlaege' && sugGroups.length === 0 && (
            <p className="text-sm text-zinc-400 py-8 text-center">{t('people.noOpenSuggestions')}</p>
          )}
          {pview === 'vorschlaege' && sugGroups.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-indigo-600 dark:text-indigo-400">{t('people.suggestionsHeading')}</h2>
                  <p className="text-xs text-zinc-500 mt-0.5">{t('people.suggestionsHint')}</p>
                </div>
                <button onClick={() => suggestMutation.mutate()} disabled={suggestMutation.isPending}
                  className="text-xs px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50">
                  {suggestMutation.isPending ? t('people.recalculating') : t('people.recalculate')}
                </button>
              </div>
              <div className="space-y-6">
                {sugGroups.map(g => (
                  <div key={g.person_id} className="rounded-2xl border border-zinc-200 dark:border-zinc-700 p-3">
                    <div className="flex items-center justify-between mb-2 gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <img src={`/api/people/${g.person_id}/avatar`} className="w-8 h-8 rounded-full object-cover ring-1 ring-zinc-300 dark:ring-zinc-700"
                          onError={e => { (e.target as HTMLImageElement).style.visibility = 'hidden' }} />
                        <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200 truncate">{g.name}</span>
                        <span className="text-xs text-zinc-500 shrink-0">{g.count}×</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button onClick={() => confirmGroup.mutate(g.person_id)} disabled={confirmGroup.isPending || rejectGroup.isPending}
                          className="text-xs px-3 py-1.5 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50">
                          {t('people.confirmAll')}
                        </button>
                        <button onClick={async () => { if (await confirm({ title: t('people.rejectGroupConfirmTitle', { count: g.count, name: g.name }), message: t('people.rejectGroupConfirmMessage'), confirmLabel: t('people.rejectAll'), danger: true })) rejectGroup.mutate(g.person_id) }}
                          disabled={confirmGroup.isPending || rejectGroup.isPending}
                          className="text-xs px-3 py-1.5 rounded-lg bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50">
                          {t('people.rejectAll')}
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-5 sm:grid-cols-7 md:grid-cols-9 lg:grid-cols-12 gap-2">
                      {g.faces.map(f => (
                        <div key={f.id} className="relative aspect-square rounded-xl overflow-hidden ring-1 ring-zinc-300 dark:ring-zinc-700 group">
                          <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover cursor-zoom-in" loading="lazy"
                            onClick={() => setBigFace({ id: f.id, photo_id: f.photo_id, name: g.name, score: f.score })}
                            onError={e => { (e.target as HTMLImageElement).style.opacity = '0.15' }} />
                          <div className="absolute inset-x-0 bottom-0 flex opacity-90 group-hover:opacity-100">
                            <button onClick={() => confirmFace.mutate(f.id)} title={t('people.adopt')}
                              className="flex-1 bg-emerald-600/90 hover:bg-emerald-600 text-white text-xs py-0.5">✓</button>
                            <button onClick={() => rejectFace.mutate(f.id)} title={t('people.discard')}
                              className="flex-1 bg-rose-600/90 hover:bg-rose-600 text-white text-xs py-0.5">✗</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
          {pview === 'personen' && known.length > 0 && (
            <section>
              <SectionHeader title={t('people.namedPeople')} count={known.length} />
              <div className={GRID}>{known.map(renderCard)}</div>
            </section>
          )}
          {pview === 'personen' && unknown.length > 0 && (
            <section>
              <SectionHeader title={t('people.unknownPeople')} count={unknown.length}
                hint={t('people.unknownPeopleHint')} />
              <div className={GRID}>{unknown.map(renderCard)}</div>
            </section>
          )}
          {pview === 'gesichter' && looseTotal > 0 && (
            <section>
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{t('people.singleFaces')} <span className="text-zinc-500 font-normal">({looseTotal})</span></h2>
                  <p className="text-xs text-zinc-500 mt-0.5">{t('people.singleFacesHint')}</p>
                </div>
                <div className="flex gap-2 text-xs">
                  <button onClick={() => setFaceSel(new Set(looseFaces.map(f => f.id)))}
                    className="px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                    {t('people.selectPage')}
                  </button>
                  {ignoredFaces.length > 0 || showIgnored ? (
                    <button onClick={() => setShowIgnored(v => !v)}
                      className={`px-2.5 py-1 rounded-lg border ${showIgnored ? 'border-indigo-500 text-indigo-500' : 'border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300'} hover:bg-zinc-100 dark:hover:bg-zinc-800`}>
                      {t('people.showHiddenFaces')}
                    </button>
                  ) : null}
                </div>
              </div>
              <div className="grid grid-cols-5 sm:grid-cols-7 md:grid-cols-9 lg:grid-cols-12 gap-3">
                {looseFaces.map(f => (
                  <FaceTile key={f.id} face={f} selected={faceSel.has(f.id)}
                    onToggle={() => toggleFace(f.id)} onAssign={() => setAssignIds([f.id])} />
                ))}
              </div>
              <Pager page={loosePage} pageSize={loosePageSize} total={looseTotal}
                onPage={setLoosePage} onSize={(n) => { setLoosePageSize(n); setLoosePage(1) }} />
            </section>
          )}

          {pview === 'verborgen' && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{t('people.hiddenFaces')} <span className="text-zinc-500 font-normal">({ignoredFaces.length})</span></h2>
                {ignoredFaces.length > 0 && (
                  <button onClick={() => ignoreFaces.mutate({ ids: ignoredFaces.map(f => f.id), ignored: false })}
                    className="text-xs px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                    {t('people.unhideAll')}
                  </button>
                )}
              </div>
              <div className="grid grid-cols-5 sm:grid-cols-7 md:grid-cols-9 lg:grid-cols-12 gap-3">
                {ignoredFaces.map(f => (
                  <button key={f.id} onClick={() => ignoreFaces.mutate({ ids: [f.id], ignored: false })}
                    title={t('people.unhide')}
                    className="relative aspect-square rounded-xl overflow-hidden bg-zinc-800 ring-1 ring-zinc-700 opacity-50 hover:opacity-100 hover:ring-emerald-500 transition-all">
                    <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover" loading="lazy"
                      onError={e => { (e.target as HTMLImageElement).style.opacity = '0.15' }} />
                  </button>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* Selection action bar */}
      {selection.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-wrap items-center justify-center gap-2 px-3 py-2.5 rounded-2xl bg-zinc-900/95 border border-zinc-700 shadow-2xl backdrop-blur max-w-[calc(100vw-1.5rem)]">
          <span className="text-sm text-zinc-300 px-2">{t('people.selectedCount', { count: selection.size })}</span>
          <button onClick={() => setMergeOpen(true)} disabled={selection.size < 2}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed">
            <GitMerge size={14} /> {t('people.merge')}
          </button>
          <button onClick={() => bulkHide(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800">
            <EyeOff size={14} /> {t('people.hide')}
          </button>
          <button onClick={clearSelection} className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-800" title={t('people.clearSelection')}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Face selection action bar */}
      {faceSel.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-wrap items-center justify-center gap-2 px-3 py-2.5 rounded-2xl bg-zinc-900/95 border border-zinc-700 shadow-2xl backdrop-blur max-w-[calc(100vw-1.5rem)]">
          <span className="text-sm text-zinc-300 px-2">{t('people.facesCount', { count: faceSel.size })}</span>
          <button onClick={() => ignoreFaces.mutate({ ids: [...faceSel], ignored: true })} disabled={ignoreFaces.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
            <EyeOff size={14} /> {t('people.hideFaces')}
          </button>
          <button onClick={() => setAssignIds([...faceSel])}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800">
            <UserPlus size={14} /> {t('people.toPerson')}
          </button>
          <button onClick={() => setFaceSel(new Set())} className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-800" title={t('people.clearSelection')}>
            <X size={16} />
          </button>
        </div>
      )}

      {showAdd && <AddPersonModal onClose={() => setShowAdd(false)} onCreated={() => { qc.invalidateQueries({ queryKey: ['people'] }); toast(t('people.toastPersonCreated'), 'success') }} />}
      {quickName && <QuickNameOverlay onClose={() => setQuickName(false)} />}
      {bigFace && (
        <div className="fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-center p-4" onClick={() => setBigFace(null)}>
          <div className="absolute top-4 right-4 flex gap-2">
            <button onClick={(e) => { e.stopPropagation(); confirmFace.mutate(bigFace.id); setBigFace(null) }}
              className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-500">✓ {bigFace.name || t('people.adoptFallback')}</button>
            <button onClick={(e) => { e.stopPropagation(); rejectFace.mutate(bigFace.id); setBigFace(null) }}
              className="px-4 py-2 rounded-lg bg-rose-600 text-white text-sm hover:bg-rose-500">✗ {t('people.discard')}</button>
            <button onClick={() => setBigFace(null)} className="px-3 py-2 rounded-lg bg-zinc-700 text-white text-sm"><X size={16} /></button>
          </div>
          <img src={thumbUrl({ id: bigFace.photo_id } as any, 'large')} onClick={e => e.stopPropagation()}
            className="max-h-[80vh] max-w-[92vw] object-contain rounded-lg shadow-2xl"
            onError={e => { (e.target as HTMLImageElement).src = `/api/people/faces/${bigFace.id}/crop` }} />
          {bigFace.score != null && (
            <p className="mt-3 text-zinc-300 text-sm">{t('people.suggestionLine', { name: bigFace.name || '', percent: Math.round((bigFace.score || 0) * 100) })}</p>
          )}
        </div>
      )}
      {mergeOpen && (
        <MergeModal
          people={selectedPeople}
          onClose={() => setMergeOpen(false)}
          onMerged={(n) => { refresh(); clearSelection(); setMergeOpen(false); toast(t('people.toastPeopleMerged', { count: n }), 'success') }}
        />
      )}
      {assignIds && assignIds.length > 0 && (
        <FaceAssignModal
          faceIds={assignIds}
          people={known}
          onClose={() => setAssignIds(null)}
          onDone={() => { refresh(); setAssignIds(null); setFaceSel(new Set()) }}
        />
      )}
    </div>
  )
}

function SectionHeader({ title, count, hint }: { title: string; count: number; hint?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{title} <span className="text-zinc-500 font-normal">({count})</span></h2>
      {hint && <p className="text-xs text-zinc-500 mt-0.5">{hint}</p>}
    </div>
  )
}

function Pager({ page, pageSize, total, onPage, onSize }: {
  page: number; pageSize: number; total: number;
  onPage: (p: number) => void; onSize: (n: number) => void;
}) {
  const { t } = useT()
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= 25) return null
  const from = (page - 1) * pageSize + 1
  const to = Math.min(total, page * pageSize)
  return (
    <div className="flex items-center gap-3 mt-4 text-xs flex-wrap">
      <div className="flex items-center gap-1">
        <span className="text-zinc-500 mr-1">{t('people.perPage')}</span>
        {[25, 50, 100].map(n => (
          <button key={n} onClick={() => onSize(n)}
            className={`px-2.5 py-1 rounded-lg border ${pageSize === n
              ? 'border-indigo-500 bg-indigo-500 text-white'
              : 'border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}>{n}</button>
        ))}
      </div>
      <div className="flex items-center gap-2 ml-auto">
        <span className="text-zinc-500">{t('people.pagerRange', { from, to, total })}</span>
        <button disabled={page <= 1} onClick={() => onPage(page - 1)}
          className="px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-40">{t('people.pagerPrev')}</button>
        <span className="text-zinc-500 tabular-nums">{t('people.pagerPage', { page, pages })}</span>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)}
          className="px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-40">{t('people.pagerNext')}</button>
      </div>
    </div>
  )
}

function FaceTile({ face, selected, onToggle, onAssign }: {
  face: FaceRef; selected: boolean; onToggle: () => void; onAssign: () => void
}) {
  const [showPhoto, setShowPhoto] = useState(false)
  const { t } = useT()
  return (
    <div className={`group relative aspect-square rounded-xl overflow-hidden bg-zinc-800 ring-2 transition-all ${
      selected ? 'ring-indigo-500' : 'ring-zinc-700 hover:ring-indigo-500/60'
    }`}>
      <img src={`/api/people/faces/${face.id}/crop`} onClick={onAssign} loading="lazy"
        className="w-full h-full object-cover cursor-pointer" title={t('people.assignFace')}
        onError={e => { (e.target as HTMLImageElement).style.opacity = '0.15' }} />
      {/* always-visible select checkbox */}
      <button onClick={e => { e.stopPropagation(); onToggle() }} title={selected ? t('people.deselect') : t('people.selectOne')}
        className={`absolute top-1 left-1 w-5 h-5 rounded-md flex items-center justify-center ring-2 ${
          selected ? 'bg-indigo-500 text-white ring-indigo-400' : 'bg-black/60 text-white/50 ring-white/40'
        }`}>
        <Check size={12} />
      </button>
      {/* on-demand: reveal the WHOLE photo (object-contain) to judge who it is */}
      <button onClick={e => { e.stopPropagation(); setShowPhoto(v => !v) }} title={t('people.showWholePhoto')}
        className="absolute top-1 right-1 w-5 h-5 rounded-md flex items-center justify-center bg-black/60 text-white/70 ring-2 ring-white/40 hover:text-white">
        <ImageIcon size={12} />
      </button>
      {showPhoto && (
        <div className="fixed inset-0 z-[200] bg-black/85 backdrop-blur-sm flex items-center justify-center p-6 cursor-zoom-out"
          onClick={e => { e.stopPropagation(); setShowPhoto(false) }}>
          <img src={thumbUrl({ id: face.photo_id } as any, 'large')}
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
            onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  )
}

function PersonCard({ person, knownPeople, selected, selectMode, onOpen, onToggleSelect, onToggleHidden, onDelete, onRenamed }: {
  person: Person
  knownPeople: Person[]
  selected: boolean
  selectMode: boolean
  onOpen: () => void
  onToggleSelect: () => void
  onToggleHidden: () => void
  onDelete: () => void
  onRenamed: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(person.name)
  const age = person.birthdate ? differenceInYears(new Date(), new Date(person.birthdate)) : null
  const toast = useToast()
  const { t } = useT()

  const rename = useMutation({
    mutationFn: (n: string) => {
      // If the typed name matches an EXISTING different person, merge into them
      // instead of creating a second "Lea Marie" etc. (the duplicate-person trap).
      const match = (knownPeople || []).find(
        k => k.id !== person.id && (k.name || '').trim().toLowerCase() === n.trim().toLowerCase())
      if (match) {
        return api.post('/people/merge-multi', { target_id: match.id, source_ids: [person.id] })
          .then(() => ({ merged: match.name }))
      }
      return api.patch(`/people/${person.id}`, { name: n }).then(() => ({ merged: null }))
    },
    onSuccess: (r: any) => { setEditing(false); onRenamed(); toast(r?.merged ? t('people.toastMergedInto', { name: r.merged }) : t('people.toastNameSaved'), 'success') },
    onError: () => toast(t('people.toastSaveFailed'), 'error'),
  })

  return (
    <div className="group relative flex flex-col items-center">
      {/* selection checkbox — always visible in select mode */}
      {selectMode && (
        <button
          onClick={e => { e.stopPropagation(); onToggleSelect() }}
          className={`absolute top-1 left-1 z-10 w-6 h-6 rounded-full flex items-center justify-center ring-2 ${
            selected ? 'bg-indigo-500 text-white ring-indigo-400' : 'bg-black/60 text-white/40 ring-white/40'
          }`}
          title={selected ? t('people.deselect') : t('people.selectOne')}
        >
          <Check size={14} />
        </button>
      )}

      {/* per-card actions — visible (not hover-only) outside select mode */}
      {!selectMode && (
        <div className="absolute top-1 right-1 z-10 flex gap-1 opacity-70 group-hover:opacity-100 transition-opacity">
          <button onClick={e => { e.stopPropagation(); onToggleHidden() }}
            className="w-6 h-6 rounded-full bg-black/60 text-zinc-200 hover:text-indigo-300 flex items-center justify-center"
            title={person.is_hidden ? t('people.toggleHiddenShow') : t('people.toggleHiddenHide')}>
            {person.is_hidden ? <Eye size={12} /> : <EyeOff size={12} />}
          </button>
          <button onClick={e => { e.stopPropagation(); onDelete() }}
            className="w-6 h-6 rounded-full bg-black/60 text-zinc-200 hover:text-red-400 flex items-center justify-center" title={t('people.deleteTitle')}>
            <Trash2 size={12} />
          </button>
        </div>
      )}

      <button onClick={onOpen}
        className={`relative w-full aspect-square rounded-full overflow-hidden bg-zinc-800 mb-2 ring-2 transition-all ${
          selected ? 'ring-indigo-500' : 'ring-zinc-700/60 group-hover:ring-indigo-500/50'
        }`}>
        <span className="absolute inset-0 flex items-center justify-center text-2xl font-bold text-zinc-600">
          {(person.name || '?').charAt(0).toUpperCase()}
        </span>
        <img src={`/api/people/${person.id}/avatar?v=${person.profile_face_id ?? 0}`} className="w-full h-full object-cover relative"
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        {person.is_hidden && (
          <span className="absolute bottom-1 left-1/2 -translate-x-1/2 px-1.5 py-0.5 rounded text-[9px] bg-black/70 text-zinc-200 flex items-center gap-0.5">
            <EyeOff size={9} /> {t('people.hiddenBadge')}
          </span>
        )}
      </button>

      {editing ? (
        <>
        <input
          autoFocus value={name} list={`names-${person.id}`}
          onChange={e => setName(e.target.value)}
          onBlur={() => { if (name.trim() && name !== person.name) rename.mutate(name.trim()); else setEditing(false) }}
          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') { setName(person.name); setEditing(false) } }}
          className="w-full px-2 py-1 text-center text-sm rounded-md bg-zinc-50 dark:bg-zinc-800 border border-indigo-500 text-zinc-900 dark:text-white focus:outline-none"
          placeholder={t('people.namePlaceholderMerge')}
        />
        <datalist id={`names-${person.id}`}>
          {(knownPeople || []).filter(k => k.id !== person.id && k.name).map(k => <option key={k.id} value={k.name} />)}
        </datalist>
        </>
      ) : person.name ? (
        <button onClick={() => setEditing(true)} className="text-sm font-medium text-zinc-900 dark:text-white text-center truncate w-full hover:text-indigo-500 dark:hover:text-indigo-300" title={t('people.rename')}>
          {person.name}
        </button>
      ) : (
        <button onClick={() => setEditing(true)} className="text-sm text-indigo-400 hover:text-indigo-300 text-center w-full">
          {t('people.addName')}
        </button>
      )}
      <p className="text-[11px] text-zinc-500">
        {(() => { const n = person.photo_count ?? person.face_count; return n === 1 ? t('people.photosCountOne', { n }) : t('people.photosCountMany', { n }) })()}{age !== null ? t('people.ageSuffix', { age }) : ''}
      </p>
    </div>
  )
}

function EmptyPeople() {
  const { t } = useT()
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <Users size={48} className="text-zinc-700 mb-4" />
      <h3 className="text-lg font-semibold text-zinc-900 dark:text-white mb-2">{t('people.emptyTitle')}</h3>
      <p className="text-sm text-zinc-500 max-w-xs">
        {t('people.emptyHint')}
      </p>
    </div>
  )
}

/* ─────────────── Person detail ─────────────── */
function PersonDetailView({ personId, onBack, onDeleted, onOpenPerson }: {
  personId: number; onBack: () => void; onDeleted: () => void; onOpenPerson: (id: number) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { t } = useT()
  const [editing, setEditing] = useState(false)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [tab, setTab] = useState<'photos' | 'faces' | 'relations'>('photos')

  const { data: settings } = useQuery<Record<string, string>>({
    queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000,
  })
  const relsOn = (settings?.['features.relationships'] ?? 'false') === 'true'

  const { data: person } = useQuery<Person>({
    queryKey: ['person', personId],
    queryFn: () => api.get(`/people/${personId}`).then(r => r.data),
  })
  const [photoPage, setPhotoPage] = useState(1)
  const [photoPageSize, setPhotoPageSize] = useState(50)
  const [photoSort, setPhotoSort] = useState<'newest' | 'oldest'>('newest')
  const { data: photosData } = useQuery({
    queryKey: ['person-photos', personId, photoPage, photoPageSize, photoSort],
    queryFn: () => api.get(`/people/${personId}/photos`, { params: { page: photoPage, limit: photoPageSize, sort: photoSort } }).then(r => r.data),
  })
  const [facePage, setFacePage] = useState(1)
  const [facePageSize, setFacePageSize] = useState(50)
  const { data: facesData } = useQuery<{ total: number; items: FaceRef[] }>({
    queryKey: ['person-faces', personId, facePage, facePageSize],
    queryFn: () => api.get(`/people/${personId}/faces`, { params: { page: facePage, limit: facePageSize } }).then(r => r.data),
  })
  const faces = facesData?.items ?? []
  const facesTotal = facesData?.total ?? 0

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['person', personId] })
    qc.invalidateQueries({ queryKey: ['person-faces', personId] })
    qc.invalidateQueries({ queryKey: ['person-photos', personId] })
    qc.invalidateQueries({ queryKey: ['people'] })
    qc.invalidateQueries({ queryKey: ['unassigned-faces'] })
  }

  const update = useMutation({
    mutationFn: (body: Record<string, any>) => api.patch(`/people/${personId}`, body),
    onSuccess: () => { invalidate(); setEditing(false); toast(t('people.toastSaved'), 'success') },
  })
  const setCover = useMutation({
    mutationFn: (faceId: number) => api.post(`/people/${personId}/profile-face/${faceId}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['people'] }); qc.invalidateQueries({ queryKey: ['person', personId] }); toast(t('people.toastCoverSet'), 'success') },
  })
  const removeFace = useMutation({
    mutationFn: (faceId: number) => api.delete(`/people/faces/${faceId}/unassign`),
    onSuccess: () => { invalidate(); toast(t('people.toastFaceRemoved'), 'success') },
  })
  const del = useMutation({ mutationFn: () => api.delete(`/people/${personId}`), onSuccess: onDeleted })
  const hide = useMutation({
    mutationFn: (h: boolean) => api.post(`/people/${personId}/hide`, null, { params: { hidden: h } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['person', personId] }); qc.invalidateQueries({ queryKey: ['people'] }) },
  })

  if (!person) return <div className="p-8 text-zinc-500">{t('people.loading')}</div>
  const photos: Photo[] = photosData?.items || []
  const total = photosData?.total ?? person.face_count

  const TABS = [
    { id: 'photos' as const, label: t('people.detailTabPhotos'), count: total, icon: <ImageIcon size={15} /> },
    { id: 'faces' as const, label: t('people.detailTabFaces'), count: facesTotal, icon: <Users size={15} /> },
    ...(relsOn ? [{ id: 'relations' as const, label: t('people.detailTabRelations'), count: -1, icon: <Share2 size={15} /> }] : []),
  ]

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <button onClick={onBack} className="flex items-center gap-1 text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white text-sm mb-6">
        <ArrowLeft size={16} /> {t('people.back')}
      </button>

      {/* Profilkarte */}
      <div className="flex flex-col sm:flex-row gap-6 mb-8 p-5 rounded-2xl bg-white/60 dark:bg-zinc-900/50 border border-zinc-200 dark:border-zinc-800">
        <div className="relative w-36 h-36 sm:w-40 sm:h-40 rounded-2xl overflow-hidden bg-zinc-800 ring-1 ring-zinc-300 dark:ring-zinc-700 flex-shrink-0 flex items-center justify-center mx-auto sm:mx-0">
          <span className="text-5xl font-bold text-zinc-600 absolute">{(person.name || '?').charAt(0).toUpperCase()}</span>
          <img src={`/api/people/${personId}/avatar?v=${person.profile_face_id ?? 0}`} className="w-full h-full object-cover absolute inset-0"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        </div>

        <div className="flex-1 min-w-0">
          {editing ? (
            <EditPersonForm person={person} onCancel={() => setEditing(false)} onSave={b => update.mutate(b)} saving={update.isPending} />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <h1 className={`text-3xl font-bold truncate ${person.name ? 'text-zinc-900 dark:text-white' : 'text-zinc-500 italic'}`}>{person.name || t('people.unnamedPerson')}</h1>
                <button onClick={() => setEditing(true)} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 shrink-0" title={t('people.edit')}><Pencil size={17} /></button>
              </div>
              {!person.name && <button onClick={() => setEditing(true)} className="mt-1 text-sm text-indigo-400 hover:text-indigo-300">{t('people.addNameLink')}</button>}
              {person.alias && <p className="text-zinc-400 text-sm mt-0.5">„{person.alias}“</p>}
              <div className="flex items-center gap-3 text-zinc-500 text-sm mt-1.5">
                <span>{t('people.photos', { count: total })}</span>
                {person.birthdate && <span>{t('people.born', { date: new Date(person.birthdate).toLocaleDateString('de'), age: differenceInYears(new Date(), new Date(person.birthdate)) })}</span>}
              </div>
              {person.notes && <p className="text-zinc-400 text-sm mt-2 italic">{person.notes}</p>}
              {/* Kontakt prominent: klickbare Chips */}
              {(person.email || person.phone || person.address) && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {person.email && <a href={`mailto:${person.email}`} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 hover:text-indigo-600 dark:hover:text-indigo-300 transition max-w-full"><Mail size={14} className="shrink-0" /><span className="truncate">{person.email}</span></a>}
                  {person.phone && <a href={`tel:${person.phone}`} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 hover:text-indigo-600 dark:hover:text-indigo-300 transition"><Phone size={14} className="shrink-0" />{person.phone}</a>}
                  {person.address && <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-sm text-zinc-700 dark:text-zinc-300 max-w-full"><MapPin size={14} className="shrink-0" /><span className="truncate">{person.address}</span></span>}
                </div>
              )}
              <div className="mt-4 flex items-center gap-4">
                <button onClick={() => hide.mutate(!person.is_hidden)} disabled={hide.isPending}
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-indigo-300 disabled:opacity-50">
                  {person.is_hidden ? <Eye size={12} /> : <EyeOff size={12} />} {person.is_hidden ? t('people.showAgain') : t('people.hideOne')}
                </button>
                <button onClick={async () => { if (await confirm({ title: t('people.deleteConfirmTitle', { name: person.name || t('people.unknown') }), danger: true, confirmLabel: t('people.deleteLabel') })) del.mutate() }}
                  className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300">
                  <Trash2 size={12} /> {t('people.deletePerson')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Unter-Tabs */}
      <div className="flex gap-1 mb-5 border-b border-zinc-200 dark:border-zinc-800">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition ${tab === t.id ? 'border-indigo-500 text-indigo-600 dark:text-indigo-300' : 'border-transparent text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200'}`}>
            {t.icon}{t.label}{t.count >= 0 && <span className="text-xs opacity-60">({t.count})</span>}
          </button>
        ))}
      </div>

      {/* Tab: Fotos */}
      {tab === 'photos' && (
        <>
          <div className="flex items-center gap-3 mb-3">
            <div className="ml-auto flex rounded-lg overflow-hidden border border-zinc-200 dark:border-zinc-700 text-xs">
              {([['newest', t('people.photoSortNewest')], ['oldest', t('people.photoSortOldest')]] as const).map(([v, l]) => (
                <button key={v} onClick={() => { setPhotoSort(v); setPhotoPage(1) }}
                  className={`px-2.5 py-1 ${photoSort === v ? 'bg-indigo-600 text-white' : 'text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}>{l}</button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8 gap-1.5">
            {photos.map((photo, i) => (
              <div key={photo.id} className="group relative aspect-square rounded-lg overflow-hidden bg-zinc-800 cursor-pointer" onClick={() => setLightboxIndex(i)}>
                <img src={thumbUrl(photo as any, 'small')} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" loading="lazy" />
                {(photo as any).is_video && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="bg-black/50 rounded-full p-1.5"><svg width="12" height="12" viewBox="0 0 24 24" fill="white"><path d="M8 5v14l11-7z" /></svg></div>
                  </div>
                )}
              </div>
            ))}
          </div>
          <Pager page={photoPage} pageSize={photoPageSize} total={total}
            onPage={setPhotoPage} onSize={(n) => { setPhotoPageSize(n); setPhotoPage(1) }} />
          {photos.length === 0 && <p className="text-sm text-zinc-500">{t('people.noPhotosYet')}</p>}
        </>
      )}

      {/* Tab: Gesichter (größer) */}
      {tab === 'faces' && (
        <div>
          {facesTotal === 0 ? (
            <p className="text-sm text-zinc-500">{t('people.noFacesAssigned')}</p>
          ) : (
            <>
              <p className="text-xs text-zinc-500 mb-3">{t('people.facesTabHint')}</p>
              <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-7 gap-3">
                {faces.map(f => (
                  <div key={f.id} className={`group relative aspect-square rounded-xl overflow-hidden bg-zinc-800 ring-2 ${person.profile_face_id === f.id ? 'ring-indigo-500' : 'ring-zinc-200 dark:ring-zinc-700'}`}>
                    <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover" loading="lazy"
                      onError={e => { (e.target as HTMLImageElement).style.opacity = '0.2' }} />
                    {person.profile_face_id === f.id && (
                      <div className="absolute top-1 left-1 bg-indigo-500 rounded-full p-1"><Star size={11} className="text-white" fill="white" /></div>
                    )}
                    <div className="absolute inset-x-0 bottom-0 h-9 bg-black/55 flex items-center justify-center gap-4 opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100 transition">
                      <button onClick={() => setCover.mutate(f.id)} title={t('people.setAsProfile')}
                        className="text-white/90 hover:text-yellow-300"><Star size={17} fill={person.profile_face_id === f.id ? 'currentColor' : 'none'} /></button>
                      <button onClick={async () => { if (await confirm({ title: t('people.removeFaceConfirmTitle'), message: t('people.removeFaceConfirmMessage') })) removeFace.mutate(f.id) }}
                        title={t('people.notThisPerson')} className="text-white/90 hover:text-red-400"><X size={17} /></button>
                    </div>
                  </div>
                ))}
              </div>
              <Pager page={facePage} pageSize={facePageSize} total={facesTotal}
                onPage={setFacePage} onSize={(n) => { setFacePageSize(n); setFacePage(1) }} />
            </>
          )}
        </div>
      )}

      {/* Tab: Beziehungen (Map + Pflege-Liste) */}
      {tab === 'relations' && relsOn && (
        <div>
          <RelationshipsMap personId={personId} profileFaceId={person.profile_face_id ?? 0} onOpenPerson={onOpenPerson} />
          <RelationshipsPanel personId={personId} personName={person.name || t('people.unknown')} />
        </div>
      )}

      {lightboxIndex !== null && <PhotoLightbox photos={photos as any} initialIndex={lightboxIndex} onClose={() => setLightboxIndex(null)} />}
    </div>
  )
}

// value → i18n key suffix (label translated at render via t('people.<key>'))
const REL_TYPES: [string, string][] = [
  ['parent', 'relParent'], ['grandparent', 'relGrandparent'],
  ['partner', 'relPartner'], ['sibling', 'relSibling'], ['relative', 'relRelative'],
  ['friend', 'relFriend'], ['colleague', 'relColleague'], ['other', 'relOther'],
]
const REL_DOT: Record<string, string> = { family: 'bg-emerald-500', social: 'bg-sky-500', other: 'bg-zinc-400' }
const REL_STROKE: Record<string, string> = { family: '#10b981', social: '#0ea5e9', other: '#a1a1aa' }

// Radialer Beziehungs-Graph (SVG, kein externes Paket). Person mittig, Verbundene im Kreis.
function RelationshipsMap({ personId, profileFaceId, onOpenPerson }: {
  personId: number; profileFaceId: number; onOpenPerson: (id: number) => void
}) {
  const { t } = useT()
  const { data: rels = [] } = useQuery<any[]>({
    queryKey: ['rels', personId], queryFn: () => api.get(`/relationships/person/${personId}`).then(r => r.data),
  })
  if (rels.length === 0) return null

  const shown = rels.slice(0, 14)
  const size = 380, cx = size / 2, cy = size / 2, R = 132, rCenter = 40, rNode = 28
  const nodes = shown.map((r, i) => {
    const ang = (i / shown.length) * 2 * Math.PI - Math.PI / 2
    return { ...r, x: cx + R * Math.cos(ang), y: cy + R * Math.sin(ang) }
  })
  const avatar = (id: number, v?: number) => `/api/people/${id}/avatar${v != null ? `?v=${v}` : ''}`
  const short = (s: string) => (s && s.length > 14 ? s.slice(0, 13) + '…' : s || '?')

  return (
    <div className="mb-6">
      <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-2">{t('people.relMapHeading')}</h2>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-md mx-auto select-none">
        <defs>
          <clipPath id={`relclip-center`}><circle cx={cx} cy={cy} r={rCenter} /></clipPath>
          {nodes.map(n => <clipPath key={n.id} id={`relclip-${n.id}`}><circle cx={n.x} cy={n.y} r={rNode} /></clipPath>)}
        </defs>

        {/* Verbindungslinien */}
        {nodes.map(n => (
          <line key={`l-${n.id}`} x1={cx} y1={cy} x2={n.x} y2={n.y}
            stroke={REL_STROKE[n.category] ?? REL_STROKE.other} strokeWidth={2} strokeOpacity={0.5} />
        ))}

        {/* Außenknoten (klickbar) */}
        {nodes.map(n => (
          <g key={`n-${n.id}`} className="cursor-pointer" onClick={() => onOpenPerson(n.other_id)}>
            <circle cx={n.x} cy={n.y} r={rNode + 2} className="fill-zinc-200 dark:fill-zinc-800" />
            <image href={avatar(n.other_id)} x={n.x - rNode} y={n.y - rNode} width={rNode * 2} height={rNode * 2}
              clipPath={`url(#relclip-${n.id})`} preserveAspectRatio="xMidYMid slice" />
            <circle cx={n.x} cy={n.y} r={rNode} fill="none" stroke={REL_STROKE[n.category] ?? REL_STROKE.other} strokeWidth={2.5} />
            <text x={n.x} y={n.y + rNode + 14} textAnchor="middle" fontSize={11} className="fill-zinc-700 dark:fill-zinc-200">{short(n.other_name)}</text>
            <text x={n.x} y={n.y + rNode + 26} textAnchor="middle" fontSize={9} className="fill-zinc-400">{n.label}</text>
          </g>
        ))}

        {/* Mittelknoten (aktuelle Person) */}
        <circle cx={cx} cy={cy} r={rCenter + 2} className="fill-zinc-200 dark:fill-zinc-800" />
        <image href={avatar(personId, profileFaceId)} x={cx - rCenter} y={cy - rCenter} width={rCenter * 2} height={rCenter * 2}
          clipPath="url(#relclip-center)" preserveAspectRatio="xMidYMid slice" />
        <circle cx={cx} cy={cy} r={rCenter} fill="none" className="stroke-indigo-500" strokeWidth={3} />
      </svg>
      {rels.length > shown.length && (
        <p className="text-center text-xs text-zinc-400 mt-1">{t('people.relMore', { count: rels.length - shown.length })}</p>
      )}
    </div>
  )
}

function RelationshipsPanel({ personId, personName }: { personId: number; personName: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { t } = useT()
  const [adding, setAdding] = useState(false)
  const [type, setType] = useState('parent')
  const [otherId, setOtherId] = useState<number | ''>('')
  const [q, setQ] = useState('')   // searchable person picker

  const { data: settings } = useQuery<Record<string, string>>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000 })
  const on = (settings?.['features.relationships'] ?? 'false') === 'true'
  const { data: rels = [] } = useQuery<any[]>({ queryKey: ['rels', personId], queryFn: () => api.get(`/relationships/person/${personId}`).then(r => r.data), enabled: on })
  const { data: people = [] } = useQuery<Person[]>({ queryKey: ['people'], queryFn: () => api.get('/people').then(r => r.data), enabled: on })

  const inval = () => { qc.invalidateQueries({ queryKey: ['rels', personId] }); qc.invalidateQueries({ queryKey: ['rel-graph'] }) }
  const add = useMutation({
    mutationFn: () => api.post('/relationships', { from_person_id: personId, to_person_id: otherId, rel_type: type }),
    onSuccess: () => { inval(); setAdding(false); setOtherId(''); toast(t('people.toastConnectionAdded'), 'success') },
  })
  const del = useMutation({ mutationFn: (id: number) => api.delete(`/relationships/${id}`), onSuccess: inval })
  const makeAlbum = useMutation({
    mutationFn: () => {
      const ids = Array.from(new Set([personId, ...rels.map(r => r.other_id)]))
      return api.post('/albums', { name: t('people.familyAlbumName', { name: personName }), album_type: 'smart', smart_criteria: { person_ids: ids, person_match: 'any' } })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast(t('people.toastFamilyAlbumCreated'), 'success') },
  })

  if (!on) return null
  const sel = 'px-2.5 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">{t('people.relationships', { count: rels.length })}</h2>
        <button onClick={() => setAdding(v => !v)} className="text-xs text-indigo-500 hover:text-indigo-400 font-medium">{t('people.addConnection')}</button>
        {rels.length > 0 && (
          <button onClick={() => makeAlbum.mutate()} className="ml-auto text-xs text-zinc-500 hover:text-indigo-400">{t('people.createFamilyAlbum')}</button>
        )}
      </div>

      {adding && (
        <div className="flex flex-wrap items-center gap-2 mb-3 p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <span className="text-sm text-zinc-500">{t('people.relPersonIs', { name: personName })}</span>
          <select value={type} onChange={e => setType(e.target.value)} className={sel}>
            {REL_TYPES.map(([v, l]) => <option key={v} value={v}>{t(`people.${l}`)}</option>)}
          </select>
          {(() => {
            const named = people.filter(p => p.id !== personId && (p.name || '').trim())
              .sort((a, b) => a.name.localeCompare(b.name))
            const picked = otherId ? named.find(p => p.id === otherId) : undefined
            const matches = named.filter(p => p.name.toLowerCase().includes(q.toLowerCase()))
            return (
              <div className="relative">
                <input
                  value={picked ? picked.name : q}
                  onChange={e => { setQ(e.target.value); setOtherId('') }}
                  placeholder={t('people.searchPersonCount', { count: named.length })}
                  className={`${sel} min-w-[12rem]`} />
                {!otherId && q.trim() && (
                  <div className="absolute z-20 mt-1 w-60 max-h-56 overflow-auto rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg">
                    {matches.length === 0
                      ? <div className="px-3 py-1.5 text-sm text-zinc-500">{t('people.noMatches')}</div>
                      : matches.slice(0, 80).map(p => (
                        <button key={p.id} onClick={() => { setOtherId(p.id); setQ('') }}
                          className="block w-full text-left px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800">{p.name}</button>
                      ))}
                  </div>
                )}
              </div>
            )
          })()}
          <button onClick={() => add.mutate()} disabled={!otherId || add.isPending}
            className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">{t('people.addConnectionBtn')}</button>
        </div>
      )}

      {rels.length === 0 ? (
        <p className="text-sm text-zinc-500">{t('people.noConnections')}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {rels.map(r => (
            <div key={r.id} className="group flex items-center gap-2 pl-1 pr-2 py-1 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900">
              <span className="relative w-7 h-7 rounded-full overflow-hidden bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center shrink-0">
                <img src={`/api/people/${r.other_id}/avatar`} className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              </span>
              <span className="text-sm text-zinc-800 dark:text-zinc-200">{r.other_name}</span>
              <span className="flex items-center gap-1 text-xs text-zinc-400"><span className={`w-1.5 h-1.5 rounded-full ${REL_DOT[r.category]}`} />{r.label}</span>
              <button onClick={async () => { if (await confirm({ title: t('people.removeConnectionConfirm'), danger: true, confirmLabel: t('people.removeLabel') })) del.mutate(r.id) }}
                className="text-zinc-300 hover:text-red-500 ml-0.5"><X size={13} /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function EditPersonForm({ person, onCancel, onSave, saving }: {
  person: Person; onCancel: () => void; onSave: (b: Record<string, any>) => void; saving: boolean
}) {
  const [name, setName] = useState(person.name)
  const [alias, setAlias] = useState(person.alias || '')
  const [notes, setNotes] = useState(person.notes || '')
  const [birthdate, setBirthdate] = useState(person.birthdate ? String(person.birthdate).slice(0, 10) : '')
  const [email, setEmail] = useState(person.email || '')
  const [phone, setPhone] = useState(person.phone || '')
  const [address, setAddress] = useState(person.address || '')
  const input = INPUT
  const { t } = useT()
  return (
    <div className="space-y-2">
      <input value={name} onChange={e => setName(e.target.value)} className={input} placeholder={t('people.namePlaceholder')} />
      <div className="flex gap-2">
        <input value={alias} onChange={e => setAlias(e.target.value)} className={`${input} flex-1`} placeholder={t('people.nicknamePlaceholder')} />
        <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} className={input + ' w-auto'} title={t('people.birthdateTitle')} />
      </div>
      <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className={`${input} resize-none`} placeholder={t('people.notesPlaceholder')} />
      <div className="flex gap-2">
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} className={`${input} flex-1`} placeholder={t('people.emailPlaceholder')} />
        <input type="tel" value={phone} onChange={e => setPhone(e.target.value)} className={`${input} flex-1`} placeholder={t('people.phonePlaceholder')} />
      </div>
      <input value={address} onChange={e => setAddress(e.target.value)} className={input} placeholder={t('people.addressPlaceholder')} />
      <div className="flex gap-2">
        <button onClick={onCancel} className="px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('people.cancel')}</button>
        <button onClick={() => onSave({ name, alias, notes, birthdate: birthdate || null, email: email || null, phone: phone || null, address: address || null })} disabled={saving || !name.trim()}
          className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50">{t('people.save')}</button>
      </div>
    </div>
  )
}

/* ─────────────── Merge modal ─────────────── */
function MergeModal({ people, onClose, onMerged }: {
  people: Person[]; onClose: () => void; onMerged: (n: number) => void
}) {
  const named = people.find(p => p.name) || people[0]
  const [targetId, setTargetId] = useState<number>(named?.id ?? people[0]?.id ?? 0)
  const [name, setName] = useState(named?.name || '')
  const toast = useToast()
  const { t } = useT()

  const merge = useMutation({
    mutationFn: () => api.post('/people/merge-multi', {
      target_id: targetId,
      source_ids: people.map(p => p.id).filter(id => id !== targetId),
      keep_name: name.trim() || undefined,
    }),
    onSuccess: () => onMerged(people.length - 1),
    onError: () => toast(t('people.toastMergeFailed'), 'error'),
  })

  return (
    <Modal open onClose={onClose} title={t('people.mergeModalTitle', { count: people.length })}>
      <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-3">{t('people.mergeModalIntro')}</p>
      <div className="space-y-1.5 max-h-64 overflow-y-auto mb-4">
        {people.map(p => (
          <button key={p.id} onClick={() => { setTargetId(p.id); if (p.name) setName(p.name) }}
            className={`w-full flex items-center gap-3 p-2 rounded-lg border text-left transition-colors ${targetId === p.id ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20' : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800/50'}`}>
            <div className="relative w-10 h-10 rounded-full overflow-hidden bg-zinc-800 flex-shrink-0 flex items-center justify-center">
              <span className="absolute text-sm text-zinc-600">{(p.name || '?').charAt(0).toUpperCase()}</span>
              <img src={`/api/people/${p.id}/avatar?v=${p.profile_face_id ?? 0}`} className="w-full h-full object-cover relative" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm truncate ${p.name ? 'text-zinc-900 dark:text-white' : 'text-zinc-500 italic'}`}>{p.name || t('people.unknown')}</p>
              <p className="text-xs text-zinc-500">{t('people.photosShort', { count: p.face_count })}</p>
            </div>
            {targetId === p.id && <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500 text-white font-medium">{t('people.keepBadge')}</span>}
          </button>
        ))}
      </div>
      <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">{t('people.mergeNameLabel')}</label>
      <input value={name} onChange={e => setName(e.target.value)} placeholder={t('people.nameOptional')}
        className="w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
      <div className="flex gap-2 justify-end">
        <button onClick={onClose} className="px-3.5 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('people.cancel')}</button>
        <button onClick={() => merge.mutate()} disabled={merge.isPending}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          <GitMerge size={14} /> {t('people.merge')}
        </button>
      </div>
    </Modal>
  )
}

/* ─────────────── Face assign modal ─────────────── */
function FaceAssignModal({ faceIds, people, onClose, onDone }: {
  faceIds: number[]; people: Person[]; onClose: () => void; onDone: () => void
}) {
  const [search, setSearch] = useState('')
  const [newName, setNewName] = useState('')
  const toast = useToast()
  const { t } = useT()
  const filtered = people.filter(p => p.name.toLowerCase().includes(search.toLowerCase()))
  const n = faceIds.length

  const assign = useMutation({
    mutationFn: (personId: number) => api.post('/people/faces/assign-many', { face_ids: faceIds, person_id: personId }),
    onSuccess: () => { toast(t('people.toastFacesAssigned', { count: n }), 'success'); onDone() },
    onError: () => toast(t('people.toastAssignFailed'), 'error'),
  })
  const createNew = useMutation({
    mutationFn: () => api.post('/people/faces/new-person-many', { face_ids: faceIds, name: newName.trim() || undefined }),
    onSuccess: () => { toast(t('people.toastNewPersonCreated'), 'success'); onDone() },
    onError: () => toast(t('people.toastCreateFailed'), 'error'),
  })

  return (
    <Modal open onClose={onClose} maxWidth="max-w-lg" title={n === 1 ? t('people.assignOneFace') : t('people.assignManyFaces', { count: n })}>
      <div className="flex gap-4 mb-4">
        <div className="flex -space-x-3 flex-shrink-0">
          {faceIds.slice(0, 4).map((id, i) => (
            <img key={id} src={`/api/people/faces/${id}/crop`}
              className="w-16 h-16 rounded-xl object-cover bg-zinc-200 dark:bg-zinc-800 ring-2 ring-white dark:ring-zinc-900"
              style={{ zIndex: 4 - i }} />
          ))}
          {n > 4 && <div className="w-16 h-16 rounded-xl bg-zinc-200 dark:bg-zinc-800 ring-2 ring-white dark:ring-zinc-900 flex items-center justify-center text-xs font-semibold text-zinc-600 dark:text-zinc-300">+{n - 4}</div>}
        </div>
        <div className="flex-1">
          <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">{n === 1 ? t('people.newPersonFromFace') : t('people.newPersonFromFaces', { count: n })}</label>
          <div className="flex gap-2">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder={t('people.nameOptional')}
              onKeyDown={e => { if (e.key === 'Enter') createNew.mutate() }}
              className="flex-1 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={() => createNew.mutate()} disabled={createNew.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
              <UserPlus size={14} /> {t('people.new')}
            </button>
          </div>
        </div>
      </div>

      <div className="border-t border-zinc-200 dark:border-zinc-800 pt-4">
        <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">{t('people.orToExisting')}</label>
        <div className="relative mb-2">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder={t('people.searchPerson')}
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div className="max-h-52 overflow-y-auto space-y-1">
          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 py-2 text-center">{t('people.noNamedPeople')}</p>
          ) : filtered.map(p => (
            <button key={p.id} onClick={() => assign.mutate(p.id)} disabled={assign.isPending}
              className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-left disabled:opacity-50">
              <div className="relative w-9 h-9 rounded-full overflow-hidden bg-zinc-800 flex-shrink-0 flex items-center justify-center">
                <span className="absolute text-xs text-zinc-600">{p.name.charAt(0).toUpperCase()}</span>
                <img src={`/api/people/${p.id}/avatar?v=${p.profile_face_id ?? 0}`} className="w-full h-full object-cover relative" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              </div>
              <span className="text-sm text-zinc-900 dark:text-white flex-1 truncate">{p.name}</span>
              <span className="text-xs text-zinc-500">{p.face_count}</span>
            </button>
          ))}
        </div>
      </div>
    </Modal>
  )
}

/* ─────────────── Add person modal ─────────────── */
function AddPersonModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState('')
  const [alias, setAlias] = useState('')
  const [birthdate, setBirthdate] = useState('')
  const input = INPUT
  const { t } = useT()
  const mutation = useMutation({
    mutationFn: () => api.post('/people', { name, alias: alias || undefined, birthdate: birthdate || undefined }),
    onSuccess: () => { onCreated(); onClose() },
  })
  return (
    <Modal open onClose={onClose} title={t('people.addPersonTitle')}>
      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-3">
        <input required placeholder={t('people.nameRequired')} value={name} onChange={e => setName(e.target.value)} className={input} />
        <input placeholder={t('people.aliasNickname')} value={alias} onChange={e => setAlias(e.target.value)} className={input} />
        <div>
          <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">{t('people.birthdateOptional')}</label>
          <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} className={input} />
        </div>
        <p className="text-xs text-zinc-500">{t('people.addPersonTip')}</p>
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">{t('people.cancel')}</button>
          <button type="submit" disabled={mutation.isPending || !name.trim()}
            className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
            {mutation.isPending ? t('people.creating') : t('people.add')}
          </button>
        </div>
      </form>
    </Modal>
  )
}

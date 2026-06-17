import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UserPlus, Users, GitMerge, Trash2, Pencil, ArrowLeft, X, Eye, EyeOff,
  Check, Search, Star, Sparkles, Image as ImageIcon, Save,
} from 'lucide-react'
import { api, thumbUrl } from '../lib/api'
import { differenceInYears } from 'date-fns'
import PhotoLightbox from '../components/gallery/PhotoLightbox'
import { Modal, useToast, useConfirm } from '../components/ui/dialogs'

interface Person {
  id: number
  name: string
  alias?: string
  birthdate?: string
  relationship_type?: string
  profile_face_id?: number
  notes?: string
  face_count: number
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
  const [selectMode, setSelectMode] = useState(false)
  const [selection, setSelection] = useState<Set<number>>(new Set())
  const [showAdd, setShowAdd] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [assignIds, setAssignIds] = useState<number[] | null>(null)
  const [showIgnored, setShowIgnored] = useState(false)
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()

  const { data: people = [], isLoading } = useQuery<Person[]>({
    queryKey: ['people', showHidden],
    queryFn: () => api.get('/people', { params: { include_hidden: showHidden } }).then(r => r.data),
  })
  const { data: looseFaces = [] } = useQuery<FaceRef[]>({
    queryKey: ['unassigned-faces'],
    queryFn: () => api.get('/people/faces/unassigned', { params: { limit: 500 } }).then(r => r.data),
  })
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
  const toggleFace = (id: number) =>
    setFaceSel(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const ignoreFaces = useMutation({
    mutationFn: ({ ids, ignored }: { ids: number[]; ignored: boolean }) =>
      api.post('/people/faces/ignore', { face_ids: ids }, { params: { ignored } }),
    onSuccess: (_d, v) => {
      refresh(); setFaceSel(new Set())
      toast(`${v.ids.length} Gesicht(er) ${v.ignored ? 'ausgeblendet' : 'wieder eingeblendet'}`, 'success')
    },
  })

  const hideMutation = useMutation({
    mutationFn: ({ id, hidden }: { id: number; hidden: boolean }) =>
      api.post(`/people/${id}/hide`, null, { params: { hidden } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['people'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/people/${id}`),
    onSuccess: () => { refresh(); toast('Person gelöscht', 'success') },
  })
  const clusterMutation = useMutation({
    mutationFn: () => api.post('/people/cluster').then(r => r.data),
    onSuccess: (d: { new_persons: number; clustered: number; assigned_to_existing: number; merged_clusters?: number }) => {
      refresh()
      toast(`Clustering: ${d.new_persons} neue Gruppe(n), ${d.assigned_to_existing} zugeordnet, ${d.merged_clusters ?? 0} zusammengeführt`, 'success')
    },
    onError: () => toast('Clustering fehlgeschlagen', 'error'),
  })

  // Button-driven: persist every detected face as an MWG region (box + name
  // where known) into the files. Done explicitly once clustering/naming has
  // settled — unknown faces keep their coordinates so a future tool never has
  // to re-run face detection.
  const writeNamesMutation = useMutation({
    mutationFn: () => api.post('/people/write-faces').then(r => r.data),
    onSuccess: (d: { queued_photos: number }) =>
      toast(`Gesichts-Regionen werden in ${d.queued_photos} Foto(s) geschrieben`, 'success'),
    onError: () => toast('Gesichter-Schreiben fehlgeschlagen', 'error'),
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
    toast(`${selection.size} Person(en) ${hidden ? 'verborgen' : 'eingeblendet'}`, 'success')
    clearSelection()
  }

  if (selectedId !== null) {
    return (
      <PersonDetailView
        personId={selectedId}
        onBack={() => setSelectedId(null)}
        onDeleted={() => { setSelectedId(null); refresh() }}
      />
    )
  }

  const renderCard = (p: Person) => (
    <PersonCard
      key={p.id}
      person={p}
      selected={selection.has(p.id)}
      selectMode={selectMode}
      onOpen={() => { if (selectMode) toggleSelect(p.id); else setSelectedId(p.id) }}
      onToggleSelect={() => toggleSelect(p.id)}
      onToggleHidden={() => hideMutation.mutate({ id: p.id, hidden: !p.is_hidden })}
      onRenamed={() => qc.invalidateQueries({ queryKey: ['people'] })}
      onDelete={async () => {
        if (await confirm({ title: `"${p.name || 'Unbekannt'}" löschen?`, message: 'Die Gesichter werden wieder freigegeben.', danger: true, confirmLabel: 'Löschen' }))
          deleteMutation.mutate(p.id)
      }}
    />
  )

  return (
    <div className="p-4 max-w-7xl mx-auto pb-24">
      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white">Personen</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">{known.length} benannt · {unknown.length} unbekannt</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {selectMode ? (
            <button onClick={clearSelection} className={`${BTN_PRIMARY}`}>
              <X size={15} /> Fertig
            </button>
          ) : (
            <button onClick={() => setSelectMode(true)} className={BTN_GHOST}
              title="Mehrere Personen auswählen, um sie zusammenzuführen oder zu verbergen">
              <GitMerge size={15} /><span className="hidden sm:inline">Auswählen / Zusammenführen</span><span className="sm:hidden">Auswählen</span>
            </button>
          )}
          <button onClick={() => setShowHidden(v => !v)}
            className={showHidden ? BTN_GHOST_ACTIVE : BTN_GHOST}
            title={showHidden ? 'Verborgene ausblenden' : 'Verborgene anzeigen'}>
            {showHidden ? <EyeOff size={15} /> : <Eye size={15} />}<span className="hidden sm:inline">Verborgene</span>
          </button>
          <button onClick={() => clusterMutation.mutate()} disabled={clusterMutation.isPending}
            className={`${BTN_GHOST} disabled:opacity-50`}
            title="Unzugeordnete Gesichter automatisch gruppieren">
            <Sparkles size={15} /><span className="hidden sm:inline">{clusterMutation.isPending ? 'Clustere…' : 'Clustern'}</span>
          </button>
          <button onClick={() => writeNamesMutation.mutate()} disabled={writeNamesMutation.isPending}
            className={`${BTN_GHOST} disabled:opacity-50`}
            title="Alle erkannten Gesichter (Koordinaten + Namen) dauerhaft in die Bilddateien schreiben (MWG-Regionen) — erspart später erneute Gesichtserkennung">
            <Save size={15} /><span className="hidden sm:inline">{writeNamesMutation.isPending ? 'Schreibe…' : 'Gesichter schreiben'}</span>
          </button>
          <button onClick={() => setShowAdd(true)} className={BTN_PRIMARY}>
            <UserPlus size={15} /><span className="hidden sm:inline">Hinzufügen</span>
          </button>
        </div>
      </div>

      {selectMode && (
        <div className="mb-4 px-3.5 py-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800 text-sm text-indigo-700 dark:text-indigo-300">
          Wähle Personen aus (antippen). Mit <strong>2 oder mehr</strong> kannst du sie unten <strong>zusammenführen</strong> oder verbergen.
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">Lade…</div>
      ) : (people.length === 0 && looseFaces.length === 0) ? (
        <EmptyPeople />
      ) : (
        <div className="space-y-10">
          {known.length > 0 && (
            <section>
              <SectionHeader title="Benannte Personen" count={known.length} />
              <div className={GRID}>{known.map(renderCard)}</div>
            </section>
          )}
          {unknown.length > 0 && (
            <section>
              <SectionHeader title="Unbekannte Personen" count={unknown.length}
                hint="Klicke eine Person an, um sie zu benennen — oder wähle mehrere aus und führe sie zusammen." />
              <div className={GRID}>{unknown.map(renderCard)}</div>
            </section>
          )}
          {looseFaces.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Einzelne Gesichter <span className="text-zinc-500 font-normal">({looseFaces.length})</span></h2>
                  <p className="text-xs text-zinc-500 mt-0.5">Häkchen zum Auswählen, Bild antippen zum Zuordnen. Unbekannte einfach auswählen und ausblenden.</p>
                </div>
                <div className="flex gap-2 text-xs">
                  <button onClick={() => setFaceSel(new Set(looseFaces.map(f => f.id)))}
                    className="px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                    Alle auswählen
                  </button>
                  {ignoredFaces.length > 0 || showIgnored ? (
                    <button onClick={() => setShowIgnored(v => !v)}
                      className={`px-2.5 py-1 rounded-lg border ${showIgnored ? 'border-indigo-500 text-indigo-500' : 'border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300'} hover:bg-zinc-100 dark:hover:bg-zinc-800`}>
                      Ausgeblendete
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
            </section>
          )}

          {showIgnored && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-semibold text-zinc-800 dark:text-zinc-200">Ausgeblendete Gesichter <span className="text-zinc-500 font-normal">({ignoredFaces.length})</span></h2>
                {ignoredFaces.length > 0 && (
                  <button onClick={() => ignoreFaces.mutate({ ids: ignoredFaces.map(f => f.id), ignored: false })}
                    className="text-xs px-2.5 py-1 rounded-lg border border-zinc-300 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">
                    Alle wieder einblenden
                  </button>
                )}
              </div>
              <div className="grid grid-cols-5 sm:grid-cols-7 md:grid-cols-9 lg:grid-cols-12 gap-3">
                {ignoredFaces.map(f => (
                  <button key={f.id} onClick={() => ignoreFaces.mutate({ ids: [f.id], ignored: false })}
                    title="Wieder einblenden"
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
          <span className="text-sm text-zinc-300 px-2">{selection.size} ausgewählt</span>
          <button onClick={() => setMergeOpen(true)} disabled={selection.size < 2}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed">
            <GitMerge size={14} /> Zusammenführen
          </button>
          <button onClick={() => bulkHide(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800">
            <EyeOff size={14} /> Verbergen
          </button>
          <button onClick={clearSelection} className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-800" title="Auswahl aufheben">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Face selection action bar */}
      {faceSel.size > 0 && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex flex-wrap items-center justify-center gap-2 px-3 py-2.5 rounded-2xl bg-zinc-900/95 border border-zinc-700 shadow-2xl backdrop-blur max-w-[calc(100vw-1.5rem)]">
          <span className="text-sm text-zinc-300 px-2">{faceSel.size} Gesicht(er)</span>
          <button onClick={() => ignoreFaces.mutate({ ids: [...faceSel], ignored: true })} disabled={ignoreFaces.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
            <EyeOff size={14} /> Ausblenden
          </button>
          <button onClick={() => setAssignIds([...faceSel])}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 text-sm hover:bg-zinc-800">
            <UserPlus size={14} /> Zu Person…
          </button>
          <button onClick={() => setFaceSel(new Set())} className="p-1.5 rounded-lg text-zinc-400 hover:bg-zinc-800" title="Auswahl aufheben">
            <X size={16} />
          </button>
        </div>
      )}

      {showAdd && <AddPersonModal onClose={() => setShowAdd(false)} onCreated={() => { qc.invalidateQueries({ queryKey: ['people'] }); toast('Person erstellt', 'success') }} />}
      {mergeOpen && (
        <MergeModal
          people={selectedPeople}
          onClose={() => setMergeOpen(false)}
          onMerged={(n) => { refresh(); clearSelection(); setMergeOpen(false); toast(`${n} Person(en) zusammengeführt`, 'success') }}
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

function FaceTile({ face, selected, onToggle, onAssign }: {
  face: FaceRef; selected: boolean; onToggle: () => void; onAssign: () => void
}) {
  const [showPhoto, setShowPhoto] = useState(false)
  return (
    <div className={`group relative aspect-square rounded-xl overflow-hidden bg-zinc-800 ring-2 transition-all ${
      selected ? 'ring-indigo-500' : 'ring-zinc-700 hover:ring-indigo-500/60'
    }`}>
      <img src={`/api/people/faces/${face.id}/crop`} onClick={onAssign} loading="lazy"
        className="w-full h-full object-cover cursor-pointer" title="Gesicht zuordnen"
        onError={e => { (e.target as HTMLImageElement).style.opacity = '0.15' }} />
      {/* always-visible select checkbox */}
      <button onClick={e => { e.stopPropagation(); onToggle() }} title={selected ? 'Abwählen' : 'Auswählen'}
        className={`absolute top-1 left-1 w-5 h-5 rounded-md flex items-center justify-center ring-2 ${
          selected ? 'bg-indigo-500 text-white ring-indigo-400' : 'bg-black/60 text-white/50 ring-white/40'
        }`}>
        <Check size={12} />
      </button>
      {/* on-demand: reveal the WHOLE photo (object-contain) to judge who it is */}
      <button onClick={e => { e.stopPropagation(); setShowPhoto(v => !v) }} title="Ganzes Foto anzeigen"
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

function PersonCard({ person, selected, selectMode, onOpen, onToggleSelect, onToggleHidden, onDelete, onRenamed }: {
  person: Person
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

  const rename = useMutation({
    mutationFn: (n: string) => api.patch(`/people/${person.id}`, { name: n }),
    onSuccess: () => { setEditing(false); onRenamed(); toast('Name gespeichert', 'success') },
    onError: () => toast('Speichern fehlgeschlagen', 'error'),
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
          title={selected ? 'Abwählen' : 'Auswählen'}
        >
          <Check size={14} />
        </button>
      )}

      {/* per-card actions — visible (not hover-only) outside select mode */}
      {!selectMode && (
        <div className="absolute top-1 right-1 z-10 flex gap-1 opacity-70 group-hover:opacity-100 transition-opacity">
          <button onClick={e => { e.stopPropagation(); onToggleHidden() }}
            className="w-6 h-6 rounded-full bg-black/60 text-zinc-200 hover:text-indigo-300 flex items-center justify-center"
            title={person.is_hidden ? 'Wieder einblenden' : 'Verbergen / Ignorieren'}>
            {person.is_hidden ? <Eye size={12} /> : <EyeOff size={12} />}
          </button>
          <button onClick={e => { e.stopPropagation(); onDelete() }}
            className="w-6 h-6 rounded-full bg-black/60 text-zinc-200 hover:text-red-400 flex items-center justify-center" title="Löschen">
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
        <img src={`/api/people/${person.id}/avatar`} className="w-full h-full object-cover relative"
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        {person.is_hidden && (
          <span className="absolute bottom-1 left-1/2 -translate-x-1/2 px-1.5 py-0.5 rounded text-[9px] bg-black/70 text-zinc-200 flex items-center gap-0.5">
            <EyeOff size={9} /> verborgen
          </span>
        )}
      </button>

      {editing ? (
        <input
          autoFocus value={name}
          onChange={e => setName(e.target.value)}
          onBlur={() => { if (name.trim() && name !== person.name) rename.mutate(name.trim()); else setEditing(false) }}
          onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') { setName(person.name); setEditing(false) } }}
          className="w-full px-2 py-1 text-center text-sm rounded-md bg-zinc-50 dark:bg-zinc-800 border border-indigo-500 text-zinc-900 dark:text-white focus:outline-none"
          placeholder="Name…"
        />
      ) : person.name ? (
        <button onClick={() => setEditing(true)} className="text-sm font-medium text-zinc-900 dark:text-white text-center truncate w-full hover:text-indigo-500 dark:hover:text-indigo-300" title="Umbenennen">
          {person.name}
        </button>
      ) : (
        <button onClick={() => setEditing(true)} className="text-sm text-indigo-400 hover:text-indigo-300 text-center w-full">
          + Name hinzufügen
        </button>
      )}
      <p className="text-[11px] text-zinc-500">
        {person.face_count} Foto{person.face_count === 1 ? '' : 's'}{age !== null ? ` · ${age} J.` : ''}
      </p>
    </div>
  )
}

function EmptyPeople() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <Users size={48} className="text-zinc-700 mb-4" />
      <h3 className="text-lg font-semibold text-zinc-900 dark:text-white mb-2">Noch keine Personen</h3>
      <p className="text-sm text-zinc-500 max-w-xs">
        Starte die KI-Pipeline für automatische Gesichtserkennung oder füge Personen manuell hinzu.
      </p>
    </div>
  )
}

/* ─────────────── Person detail ─────────────── */
function PersonDetailView({ personId, onBack, onDeleted }: {
  personId: number; onBack: () => void; onDeleted: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const [editing, setEditing] = useState(false)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  const { data: person } = useQuery<Person>({
    queryKey: ['person', personId],
    queryFn: () => api.get(`/people/${personId}`).then(r => r.data),
  })
  const { data: photosData } = useQuery({
    queryKey: ['person-photos', personId],
    queryFn: () => api.get(`/people/${personId}/photos?limit=200`).then(r => r.data),
  })
  const { data: faces = [] } = useQuery<FaceRef[]>({
    queryKey: ['person-faces', personId],
    queryFn: () => api.get(`/people/${personId}/faces`).then(r => r.data),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['person', personId] })
    qc.invalidateQueries({ queryKey: ['person-faces', personId] })
    qc.invalidateQueries({ queryKey: ['person-photos', personId] })
    qc.invalidateQueries({ queryKey: ['people'] })
    qc.invalidateQueries({ queryKey: ['unassigned-faces'] })
  }

  const update = useMutation({
    mutationFn: (body: Record<string, any>) => api.patch(`/people/${personId}`, body),
    onSuccess: () => { invalidate(); setEditing(false); toast('Gespeichert', 'success') },
  })
  const setCover = useMutation({
    mutationFn: (faceId: number) => api.post(`/people/${personId}/profile-face/${faceId}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['people'] }); qc.invalidateQueries({ queryKey: ['person', personId] }); toast('Titelbild gesetzt', 'success') },
  })
  const removeFace = useMutation({
    mutationFn: (faceId: number) => api.delete(`/people/faces/${faceId}/unassign`),
    onSuccess: () => { invalidate(); toast('Gesicht entfernt', 'success') },
  })
  const del = useMutation({ mutationFn: () => api.delete(`/people/${personId}`), onSuccess: onDeleted })
  const hide = useMutation({
    mutationFn: (h: boolean) => api.post(`/people/${personId}/hide`, null, { params: { hidden: h } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['person', personId] }); qc.invalidateQueries({ queryKey: ['people'] }) },
  })

  if (!person) return <div className="p-8 text-zinc-500">Lade…</div>
  const photos: Photo[] = photosData?.items || []
  const total = photosData?.total ?? person.face_count

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <button onClick={onBack} className="flex items-center gap-1 text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white text-sm mb-6">
        <ArrowLeft size={16} /> Zurück
      </button>

      <div className="flex gap-6 mb-8">
        <div className="relative w-28 h-28 rounded-full overflow-hidden bg-zinc-800 ring-2 ring-zinc-700 flex-shrink-0 flex items-center justify-center">
          <span className="text-4xl font-bold text-zinc-600 absolute">{(person.name || '?').charAt(0).toUpperCase()}</span>
          <img src={`/api/people/${personId}/avatar`} className="w-full h-full object-cover absolute inset-0"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
        </div>

        <div className="flex-1 min-w-0">
          {editing ? (
            <EditPersonForm person={person} onCancel={() => setEditing(false)} onSave={b => update.mutate(b)} saving={update.isPending} />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <h1 className={`text-2xl font-bold truncate ${person.name ? 'text-zinc-900 dark:text-white' : 'text-zinc-500 italic'}`}>{person.name || 'Unbenannte Person'}</h1>
                <button onClick={() => setEditing(true)} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200" title="Bearbeiten"><Pencil size={16} /></button>
              </div>
              {!person.name && <button onClick={() => setEditing(true)} className="mt-1 text-sm text-indigo-400 hover:text-indigo-300">+ Namen vergeben</button>}
              {person.alias && <p className="text-zinc-400 text-sm mt-0.5">„{person.alias}“</p>}
              <div className="flex items-center gap-3 text-zinc-500 text-sm mt-1">
                <span>{total} Fotos</span>
                {person.birthdate && <span>· geb. {new Date(person.birthdate).toLocaleDateString('de')} ({differenceInYears(new Date(), new Date(person.birthdate))} J.)</span>}
              </div>
              {person.notes && <p className="text-zinc-400 text-sm mt-2 italic">{person.notes}</p>}
              <div className="mt-3 flex items-center gap-4">
                <button onClick={() => hide.mutate(!person.is_hidden)} disabled={hide.isPending}
                  className="flex items-center gap-1 text-xs text-zinc-400 hover:text-indigo-300 disabled:opacity-50">
                  {person.is_hidden ? <Eye size={12} /> : <EyeOff size={12} />} {person.is_hidden ? 'Wieder anzeigen' : 'Verbergen'}
                </button>
                <button onClick={async () => { if (await confirm({ title: `"${person.name || 'Unbekannt'}" löschen?`, danger: true, confirmLabel: 'Löschen' })) del.mutate() }}
                  className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300">
                  <Trash2 size={12} /> Person löschen
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <RelationshipsPanel personId={personId} personName={person.name || 'Unbekannt'} />

      {faces.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-1">Gesichter ({faces.length})</h2>
          <p className="text-xs text-zinc-500 mb-3">Tippe ein Gesicht ★ um es als <strong>Profilbild</strong> zu setzen · ✕ entfernt es von dieser Person.</p>
          <div className="flex gap-2 flex-wrap">
            {faces.map(f => (
              <div key={f.id} className={`group relative w-16 h-16 rounded-lg overflow-hidden bg-zinc-800 ring-2 ${person.profile_face_id === f.id ? 'ring-indigo-500' : 'ring-zinc-700'}`}>
                <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover" loading="lazy"
                  onError={e => { (e.target as HTMLImageElement).style.opacity = '0.2' }} />
                {person.profile_face_id === f.id && (
                  <div className="absolute top-0.5 left-0.5 bg-indigo-500 rounded-full p-0.5"><Star size={9} className="text-white" fill="white" /></div>
                )}
                {/* always-visible action bar (works on touch too) */}
                <div className="absolute inset-x-0 bottom-0 h-7 bg-black/55 flex items-center justify-center gap-2">
                  <button onClick={() => setCover.mutate(f.id)} title="Als Profilbild"
                    className="text-white/90 hover:text-yellow-300"><Star size={13} fill={person.profile_face_id === f.id ? 'currentColor' : 'none'} /></button>
                  <button onClick={async () => { if (await confirm({ title: 'Gehört nicht zu dieser Person?', message: 'Das Gesicht wird wieder freigegeben.' })) removeFace.mutate(f.id) }}
                    title="Ist nicht diese Person" className="text-white/90 hover:text-red-400"><X size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider mb-3">Fotos ({total})</h2>
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
      {photos.length === 0 && <p className="text-sm text-zinc-500">Noch keine Fotos — Gesichtserkennung läuft beim Verarbeiten.</p>}

      {lightboxIndex !== null && <PhotoLightbox photos={photos as any} initialIndex={lightboxIndex} onClose={() => setLightboxIndex(null)} />}
    </div>
  )
}

const REL_TYPES: [string, string][] = [
  ['parent', 'Elternteil von'], ['grandparent', 'Großelternteil von'],
  ['partner', 'Partner'], ['sibling', 'Geschwister'], ['relative', 'Verwandt'],
  ['friend', 'Freund/in'], ['colleague', 'Kollege/in'], ['other', 'Verbindung'],
]
const REL_DOT: Record<string, string> = { family: 'bg-emerald-500', social: 'bg-sky-500', other: 'bg-zinc-400' }

function RelationshipsPanel({ personId, personName }: { personId: number; personName: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const [adding, setAdding] = useState(false)
  const [type, setType] = useState('parent')
  const [otherId, setOtherId] = useState<number | ''>('')

  const { data: settings } = useQuery<Record<string, string>>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000 })
  const on = (settings?.['features.relationships'] ?? 'false') === 'true'
  const { data: rels = [] } = useQuery<any[]>({ queryKey: ['rels', personId], queryFn: () => api.get(`/relationships/person/${personId}`).then(r => r.data), enabled: on })
  const { data: people = [] } = useQuery<Person[]>({ queryKey: ['people'], queryFn: () => api.get('/people').then(r => r.data), enabled: on })

  const inval = () => { qc.invalidateQueries({ queryKey: ['rels', personId] }); qc.invalidateQueries({ queryKey: ['rel-graph'] }) }
  const add = useMutation({
    mutationFn: () => api.post('/relationships', { from_person_id: personId, to_person_id: otherId, rel_type: type }),
    onSuccess: () => { inval(); setAdding(false); setOtherId(''); toast('Verbindung hinzugefügt', 'success') },
  })
  const del = useMutation({ mutationFn: (id: number) => api.delete(`/relationships/${id}`), onSuccess: inval })
  const makeAlbum = useMutation({
    mutationFn: () => {
      const ids = Array.from(new Set([personId, ...rels.map(r => r.other_id)]))
      return api.post('/albums', { name: `Familie ${personName}`, album_type: 'smart', smart_criteria: { person_ids: ids, person_match: 'any' } })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['albums'] }); toast('Smart-Album „Familie …" erstellt', 'success') },
  })

  if (!on) return null
  const sel = 'px-2.5 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div className="mb-8">
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-sm font-semibold text-zinc-500 dark:text-zinc-400 uppercase tracking-wider">Beziehungen ({rels.length})</h2>
        <button onClick={() => setAdding(v => !v)} className="text-xs text-indigo-500 hover:text-indigo-400 font-medium">+ Verbindung</button>
        {rels.length > 0 && (
          <button onClick={() => makeAlbum.mutate()} className="ml-auto text-xs text-zinc-500 hover:text-indigo-400">Familien-Album erstellen</button>
        )}
      </div>

      {adding && (
        <div className="flex flex-wrap items-center gap-2 mb-3 p-3 rounded-xl border border-zinc-200 dark:border-zinc-700">
          <span className="text-sm text-zinc-500">{personName} ist</span>
          <select value={type} onChange={e => setType(e.target.value)} className={sel}>
            {REL_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={otherId} onChange={e => setOtherId(Number(e.target.value))} className={`${sel} min-w-[10rem]`}>
            <option value="">— Person —</option>
            {people.filter(p => p.id !== personId && (p.name || '').trim()).sort((a, b) => a.name.localeCompare(b.name)).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button onClick={() => add.mutate()} disabled={!otherId || add.isPending}
            className="px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">Hinzufügen</button>
        </div>
      )}

      {rels.length === 0 ? (
        <p className="text-sm text-zinc-500">Noch keine Verbindungen. Lege über „+ Verbindung“ Familie, Freunde oder Kollegen an.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {rels.map(r => (
            <div key={r.id} className="group flex items-center gap-2 pl-1 pr-2 py-1 rounded-full border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900">
              <span className="relative w-7 h-7 rounded-full overflow-hidden bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center shrink-0">
                <img src={`/api/people/${r.other_id}/avatar`} className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              </span>
              <span className="text-sm text-zinc-800 dark:text-zinc-200">{r.other_name}</span>
              <span className="flex items-center gap-1 text-xs text-zinc-400"><span className={`w-1.5 h-1.5 rounded-full ${REL_DOT[r.category]}`} />{r.label}</span>
              <button onClick={async () => { if (await confirm({ title: 'Verbindung entfernen?', danger: true, confirmLabel: 'Entfernen' })) del.mutate(r.id) }}
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
  const input = INPUT
  return (
    <div className="space-y-2">
      <input value={name} onChange={e => setName(e.target.value)} className={input} placeholder="Name" />
      <div className="flex gap-2">
        <input value={alias} onChange={e => setAlias(e.target.value)} className={`${input} flex-1`} placeholder="Spitzname" />
        <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} className={input + ' w-auto'} title="Geburtsdatum" />
      </div>
      <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className={`${input} resize-none`} placeholder="Notizen" />
      <div className="flex gap-2">
        <button onClick={onCancel} className="px-3 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Abbrechen</button>
        <button onClick={() => onSave({ name, alias, notes, birthdate: birthdate || null })} disabled={saving || !name.trim()}
          className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50">Speichern</button>
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

  const merge = useMutation({
    mutationFn: () => api.post('/people/merge-multi', {
      target_id: targetId,
      source_ids: people.map(p => p.id).filter(id => id !== targetId),
      keep_name: name.trim() || undefined,
    }),
    onSuccess: () => onMerged(people.length - 1),
    onError: () => toast('Zusammenführen fehlgeschlagen', 'error'),
  })

  return (
    <Modal open onClose={onClose} title={`${people.length} Personen zusammenführen`}>
      <p className="text-sm text-zinc-600 dark:text-zinc-400 mb-3">Wähle die Person, die <strong className="text-zinc-700 dark:text-zinc-200">behalten</strong> wird. Alle Gesichter der anderen werden zu ihr verschoben.</p>
      <div className="space-y-1.5 max-h-64 overflow-y-auto mb-4">
        {people.map(p => (
          <button key={p.id} onClick={() => { setTargetId(p.id); if (p.name) setName(p.name) }}
            className={`w-full flex items-center gap-3 p-2 rounded-lg border text-left transition-colors ${targetId === p.id ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20' : 'border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800/50'}`}>
            <div className="relative w-10 h-10 rounded-full overflow-hidden bg-zinc-800 flex-shrink-0 flex items-center justify-center">
              <span className="absolute text-sm text-zinc-600">{(p.name || '?').charAt(0).toUpperCase()}</span>
              <img src={`/api/people/${p.id}/avatar`} className="w-full h-full object-cover relative" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm truncate ${p.name ? 'text-zinc-900 dark:text-white' : 'text-zinc-500 italic'}`}>{p.name || 'Unbekannt'}</p>
              <p className="text-xs text-zinc-500">{p.face_count} Fotos</p>
            </div>
            {targetId === p.id && <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500 text-white font-medium">behalten</span>}
          </button>
        ))}
      </div>
      <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">Name nach dem Zusammenführen</label>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="Name (optional)"
        className="w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
      <div className="flex gap-2 justify-end">
        <button onClick={onClose} className="px-3.5 py-1.5 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Abbrechen</button>
        <button onClick={() => merge.mutate()} disabled={merge.isPending}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          <GitMerge size={14} /> Zusammenführen
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
  const filtered = people.filter(p => p.name.toLowerCase().includes(search.toLowerCase()))
  const n = faceIds.length

  const assign = useMutation({
    mutationFn: (personId: number) => api.post('/people/faces/assign-many', { face_ids: faceIds, person_id: personId }),
    onSuccess: () => { toast(`${n} Gesicht(er) zugeordnet`, 'success'); onDone() },
    onError: () => toast('Zuordnen fehlgeschlagen', 'error'),
  })
  const createNew = useMutation({
    mutationFn: () => api.post('/people/faces/new-person-many', { face_ids: faceIds, name: newName.trim() || undefined }),
    onSuccess: () => { toast('Neue Person erstellt', 'success'); onDone() },
    onError: () => toast('Erstellen fehlgeschlagen', 'error'),
  })

  return (
    <Modal open onClose={onClose} maxWidth="max-w-lg" title={n === 1 ? 'Gesicht zuordnen' : `${n} Gesichter zuordnen`}>
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
          <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">{n === 1 ? 'Neue Person aus diesem Gesicht' : `Neue Person aus ${n} Gesichtern`}</label>
          <div className="flex gap-2">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Name (optional)"
              onKeyDown={e => { if (e.key === 'Enter') createNew.mutate() }}
              className="flex-1 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={() => createNew.mutate()} disabled={createNew.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
              <UserPlus size={14} /> Neu
            </button>
          </div>
        </div>
      </div>

      <div className="border-t border-zinc-200 dark:border-zinc-800 pt-4">
        <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">…oder zu vorhandener Person</label>
        <div className="relative mb-2">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Person suchen…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div className="max-h-52 overflow-y-auto space-y-1">
          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 py-2 text-center">Keine benannten Personen.</p>
          ) : filtered.map(p => (
            <button key={p.id} onClick={() => assign.mutate(p.id)} disabled={assign.isPending}
              className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 text-left disabled:opacity-50">
              <div className="relative w-9 h-9 rounded-full overflow-hidden bg-zinc-800 flex-shrink-0 flex items-center justify-center">
                <span className="absolute text-xs text-zinc-600">{p.name.charAt(0).toUpperCase()}</span>
                <img src={`/api/people/${p.id}/avatar`} className="w-full h-full object-cover relative" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
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
  const mutation = useMutation({
    mutationFn: () => api.post('/people', { name, alias: alias || undefined, birthdate: birthdate || undefined }),
    onSuccess: () => { onCreated(); onClose() },
  })
  return (
    <Modal open onClose={onClose} title="Person hinzufügen">
      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }} className="space-y-3">
        <input required placeholder="Name *" value={name} onChange={e => setName(e.target.value)} className={input} />
        <input placeholder="Alias / Spitzname" value={alias} onChange={e => setAlias(e.target.value)} className={input} />
        <div>
          <label className="block text-xs text-zinc-600 dark:text-zinc-400 mb-1">Geburtsdatum (optional)</label>
          <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} className={input} />
        </div>
        <p className="text-xs text-zinc-500">Tipp: Personen entstehen normalerweise automatisch aus erkannten Gesichtern. Manuell angelegte Personen haben zunächst keine Fotos.</p>
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800">Abbrechen</button>
          <button type="submit" disabled={mutation.isPending || !name.trim()}
            className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
            {mutation.isPending ? 'Erstelle…' : 'Hinzufügen'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  UserPlus, Users, GitMerge, Trash2, Pencil, ArrowLeft, X, Eye, EyeOff,
  Check, Search, Star, Sparkles,
} from 'lucide-react'
import { api } from '../lib/api'
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

export default function PeoplePage() {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showHidden, setShowHidden] = useState(false)
  const [selection, setSelection] = useState<Set<number>>(new Set())
  const [showAdd, setShowAdd] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [assignFace, setAssignFace] = useState<FaceRef | null>(null)
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()

  const { data: people = [], isLoading } = useQuery<Person[]>({
    queryKey: ['people', showHidden],
    queryFn: () => api.get('/people', { params: { include_hidden: showHidden } }).then(r => r.data),
  })
  const { data: looseFaces = [] } = useQuery<FaceRef[]>({
    queryKey: ['unassigned-faces'],
    queryFn: () => api.get('/people/faces/unassigned', { params: { limit: 200 } }).then(r => r.data),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['people'] })
    qc.invalidateQueries({ queryKey: ['unassigned-faces'] })
  }

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
    onSuccess: (d: { new_persons: number; clustered: number; assigned_to_existing: number }) => {
      refresh()
      toast(`Clustering fertig: ${d.new_persons} neue Gruppe(n), ${d.assigned_to_existing} zugeordnet`, 'success')
    },
    onError: () => toast('Clustering fehlgeschlagen', 'error'),
  })

  const known = useMemo(() => people.filter(p => (p.name || '').trim()), [people])
  const unknown = useMemo(() => people.filter(p => !(p.name || '').trim()), [people])
  const selectedPeople = people.filter(p => selection.has(p.id))

  const toggleSelect = (id: number) =>
    setSelection(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const clearSelection = () => setSelection(new Set())

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
      selectionActive={selection.size > 0}
      onOpen={() => setSelectedId(p.id)}
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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">Personen</h1>
          <p className="text-sm text-zinc-400">{known.length} benannt · {unknown.length} unbekannt</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowHidden(v => !v)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm hover:bg-zinc-800 ${showHidden ? 'border-indigo-500 text-indigo-300' : 'border-zinc-700 text-zinc-400'}`}
            title={showHidden ? 'Verborgene ausblenden' : 'Verborgene anzeigen'}>
            {showHidden ? <EyeOff size={15} /> : <Eye size={15} />}<span className="hidden sm:inline">Verborgene</span>
          </button>
          <button onClick={() => clusterMutation.mutate()} disabled={clusterMutation.isPending}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 text-zinc-400 text-sm hover:bg-zinc-800 disabled:opacity-50"
            title="Unzugeordnete Gesichter automatisch gruppieren">
            <Sparkles size={15} />{clusterMutation.isPending ? 'Clustere…' : 'Clustern'}
          </button>
          <button onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
            <UserPlus size={15} /><span className="hidden sm:inline">Hinzufügen</span>
          </button>
        </div>
      </div>

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
              <SectionHeader title="Einzelne Gesichter" count={looseFaces.length}
                hint="Noch nicht gruppiert. Klicke ein Gesicht, um es einer Person zuzuordnen — oder nutze „Clustern“." />
              <div className="grid grid-cols-5 sm:grid-cols-7 md:grid-cols-9 lg:grid-cols-12 gap-3">
                {looseFaces.map(f => (
                  <button key={f.id} onClick={() => setAssignFace(f)} title="Gesicht zuordnen"
                    className="aspect-square rounded-xl overflow-hidden bg-zinc-800 ring-1 ring-zinc-700 hover:ring-indigo-500 hover:scale-105 transition-all">
                    <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover"
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
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-3 py-2.5 rounded-2xl bg-zinc-900/95 border border-zinc-700 shadow-2xl backdrop-blur">
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

      {showAdd && <AddPersonModal onClose={() => setShowAdd(false)} onCreated={() => { qc.invalidateQueries({ queryKey: ['people'] }); toast('Person erstellt', 'success') }} />}
      {mergeOpen && (
        <MergeModal
          people={selectedPeople}
          onClose={() => setMergeOpen(false)}
          onMerged={(n) => { refresh(); clearSelection(); setMergeOpen(false); toast(`${n} Person(en) zusammengeführt`, 'success') }}
        />
      )}
      {assignFace && (
        <FaceAssignModal
          face={assignFace}
          people={known}
          onClose={() => setAssignFace(null)}
          onDone={() => { refresh(); setAssignFace(null) }}
        />
      )}
    </div>
  )
}

function SectionHeader({ title, count, hint }: { title: string; count: number; hint?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-sm font-semibold text-zinc-200">{title} <span className="text-zinc-500 font-normal">({count})</span></h2>
      {hint && <p className="text-xs text-zinc-500 mt-0.5">{hint}</p>}
    </div>
  )
}

function PersonCard({ person, selected, selectionActive, onOpen, onToggleSelect, onToggleHidden, onDelete, onRenamed }: {
  person: Person
  selected: boolean
  selectionActive: boolean
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
      {/* selection checkbox */}
      <button
        onClick={e => { e.stopPropagation(); onToggleSelect() }}
        className={`absolute top-1 left-1 z-10 w-6 h-6 rounded-full flex items-center justify-center transition-all ${
          selected ? 'bg-indigo-500 text-white' : 'bg-black/50 text-transparent opacity-0 group-hover:opacity-100 hover:text-white'
        }`}
        title={selected ? 'Abwählen' : 'Auswählen'}
      >
        <Check size={14} />
      </button>

      {/* actions */}
      {!selectionActive && (
        <div className="absolute top-1 right-1 z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={e => { e.stopPropagation(); onToggleHidden() }}
            className="w-6 h-6 rounded-full bg-black/50 text-zinc-300 hover:text-indigo-300 flex items-center justify-center"
            title={person.is_hidden ? 'Wieder anzeigen' : 'Verbergen'}>
            {person.is_hidden ? <Eye size={12} /> : <EyeOff size={12} />}
          </button>
          <button onClick={e => { e.stopPropagation(); onDelete() }}
            className="w-6 h-6 rounded-full bg-black/50 text-zinc-300 hover:text-red-400 flex items-center justify-center" title="Löschen">
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
          className="w-full px-2 py-1 text-center text-sm rounded-md bg-zinc-800 border border-indigo-500 text-white focus:outline-none"
          placeholder="Name…"
        />
      ) : person.name ? (
        <button onClick={() => setEditing(true)} className="text-sm font-medium text-white text-center truncate w-full hover:text-indigo-300" title="Umbenennen">
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
      <h3 className="text-lg font-semibold text-white mb-2">Noch keine Personen</h3>
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
      <button onClick={onBack} className="flex items-center gap-1 text-zinc-400 hover:text-white text-sm mb-6">
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
                <h1 className={`text-2xl font-bold truncate ${person.name ? 'text-white' : 'text-zinc-500 italic'}`}>{person.name || 'Unbenannte Person'}</h1>
                <button onClick={() => setEditing(true)} className="text-zinc-500 hover:text-zinc-200" title="Bearbeiten"><Pencil size={16} /></button>
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

      {faces.length > 0 && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">Gesichter ({faces.length})</h2>
          <div className="flex gap-2 flex-wrap">
            {faces.map(f => (
              <div key={f.id} className={`group relative w-16 h-16 rounded-lg overflow-hidden bg-zinc-800 ring-1 ${person.profile_face_id === f.id ? 'ring-indigo-500' : 'ring-zinc-700'}`}>
                <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover"
                  onError={e => { (e.target as HTMLImageElement).style.opacity = '0.2' }} />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1.5">
                  <button onClick={() => setCover.mutate(f.id)} title="Als Titelbild"
                    className="w-6 h-6 rounded-full bg-white/90 text-zinc-900 flex items-center justify-center hover:bg-white"><Star size={12} /></button>
                  <button onClick={async () => { if (await confirm({ title: 'Gehört nicht zu dieser Person?', message: 'Das Gesicht wird wieder freigegeben.' })) removeFace.mutate(f.id) }}
                    title="Ist nicht diese Person"
                    className="w-6 h-6 rounded-full bg-red-500/90 text-white flex items-center justify-center hover:bg-red-500"><X size={13} /></button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">Fotos ({total})</h2>
      <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8 gap-1.5">
        {photos.map((photo, i) => (
          <div key={photo.id} className="group relative aspect-square rounded-lg overflow-hidden bg-zinc-800 cursor-pointer" onClick={() => setLightboxIndex(i)}>
            <img src={`/api/photos/${photo.id}/thumbnail?size=small`} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" loading="lazy" />
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

function EditPersonForm({ person, onCancel, onSave, saving }: {
  person: Person; onCancel: () => void; onSave: (b: Record<string, any>) => void; saving: boolean
}) {
  const [name, setName] = useState(person.name)
  const [alias, setAlias] = useState(person.alias || '')
  const [notes, setNotes] = useState(person.notes || '')
  const [birthdate, setBirthdate] = useState(person.birthdate ? String(person.birthdate).slice(0, 10) : '')
  const input = 'w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'
  return (
    <div className="space-y-2">
      <input value={name} onChange={e => setName(e.target.value)} className={input} placeholder="Name" />
      <div className="flex gap-2">
        <input value={alias} onChange={e => setAlias(e.target.value)} className={`${input} flex-1`} placeholder="Spitzname" />
        <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} className={input + ' w-auto'} title="Geburtsdatum" />
      </div>
      <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} className={`${input} resize-none`} placeholder="Notizen" />
      <div className="flex gap-2">
        <button onClick={onCancel} className="px-3 py-1.5 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800">Abbrechen</button>
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
      <p className="text-sm text-zinc-400 mb-3">Wähle die Person, die <strong className="text-zinc-200">behalten</strong> wird. Alle Gesichter der anderen werden zu ihr verschoben.</p>
      <div className="space-y-1.5 max-h-64 overflow-y-auto mb-4">
        {people.map(p => (
          <button key={p.id} onClick={() => { setTargetId(p.id); if (p.name) setName(p.name) }}
            className={`w-full flex items-center gap-3 p-2 rounded-lg border text-left transition-colors ${targetId === p.id ? 'border-indigo-500 bg-indigo-900/20' : 'border-zinc-800 hover:bg-zinc-800/50'}`}>
            <div className="relative w-10 h-10 rounded-full overflow-hidden bg-zinc-800 flex-shrink-0 flex items-center justify-center">
              <span className="absolute text-sm text-zinc-600">{(p.name || '?').charAt(0).toUpperCase()}</span>
              <img src={`/api/people/${p.id}/avatar`} className="w-full h-full object-cover relative" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-sm truncate ${p.name ? 'text-white' : 'text-zinc-500 italic'}`}>{p.name || 'Unbekannt'}</p>
              <p className="text-xs text-zinc-500">{p.face_count} Fotos</p>
            </div>
            {targetId === p.id && <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500 text-white font-medium">behalten</span>}
          </button>
        ))}
      </div>
      <label className="block text-xs text-zinc-400 mb-1">Name nach dem Zusammenführen</label>
      <input value={name} onChange={e => setName(e.target.value)} placeholder="Name (optional)"
        className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
      <div className="flex gap-2 justify-end">
        <button onClick={onClose} className="px-3.5 py-1.5 rounded-lg border border-zinc-700 text-sm text-zinc-300 hover:bg-zinc-800">Abbrechen</button>
        <button onClick={() => merge.mutate()} disabled={merge.isPending}
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          <GitMerge size={14} /> Zusammenführen
        </button>
      </div>
    </Modal>
  )
}

/* ─────────────── Face assign modal ─────────────── */
function FaceAssignModal({ face, people, onClose, onDone }: {
  face: FaceRef; people: Person[]; onClose: () => void; onDone: () => void
}) {
  const [search, setSearch] = useState('')
  const [newName, setNewName] = useState('')
  const toast = useToast()
  const filtered = people.filter(p => p.name.toLowerCase().includes(search.toLowerCase()))

  const assign = useMutation({
    mutationFn: (personId: number) => api.post(`/people/faces/${face.id}/assign/${personId}`),
    onSuccess: () => { toast('Gesicht zugeordnet', 'success'); onDone() },
    onError: () => toast('Zuordnen fehlgeschlagen', 'error'),
  })
  const createNew = useMutation({
    mutationFn: async () => {
      const res = await api.post(`/people/faces/${face.id}/new-person`)
      const pid = res.data?.person_id
      if (newName.trim() && pid) await api.patch(`/people/${pid}`, { name: newName.trim() })
      return pid
    },
    onSuccess: () => { toast('Neue Person erstellt', 'success'); onDone() },
    onError: () => toast('Erstellen fehlgeschlagen', 'error'),
  })

  return (
    <Modal open onClose={onClose} title="Gesicht zuordnen">
      <div className="flex gap-4 mb-4">
        <img src={`/api/people/faces/${face.id}/crop`} className="w-24 h-24 rounded-xl object-cover bg-zinc-800 ring-1 ring-zinc-700 flex-shrink-0" />
        <div className="flex-1">
          <label className="block text-xs text-zinc-400 mb-1">Neue Person aus diesem Gesicht</label>
          <div className="flex gap-2">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Name (optional)"
              onKeyDown={e => { if (e.key === 'Enter') createNew.mutate() }}
              className="flex-1 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
            <button onClick={() => createNew.mutate()} disabled={createNew.isPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
              <UserPlus size={14} /> Neu
            </button>
          </div>
        </div>
      </div>

      <div className="border-t border-zinc-800 pt-4">
        <label className="block text-xs text-zinc-400 mb-1">…oder zu vorhandener Person</label>
        <div className="relative mb-2">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Person suchen…"
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
        </div>
        <div className="max-h-52 overflow-y-auto space-y-1">
          {filtered.length === 0 ? (
            <p className="text-sm text-zinc-500 py-2 text-center">Keine benannten Personen.</p>
          ) : filtered.map(p => (
            <button key={p.id} onClick={() => assign.mutate(p.id)} disabled={assign.isPending}
              className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-zinc-800 text-left disabled:opacity-50">
              <div className="relative w-9 h-9 rounded-full overflow-hidden bg-zinc-800 flex-shrink-0 flex items-center justify-center">
                <span className="absolute text-xs text-zinc-600">{p.name.charAt(0).toUpperCase()}</span>
                <img src={`/api/people/${p.id}/avatar`} className="w-full h-full object-cover relative" onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
              </div>
              <span className="text-sm text-white flex-1 truncate">{p.name}</span>
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
  const input = 'w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500'
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
          <label className="block text-xs text-zinc-400 mb-1">Geburtsdatum (optional)</label>
          <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} className={input} />
        </div>
        <p className="text-xs text-zinc-500">Tipp: Personen entstehen normalerweise automatisch aus erkannten Gesichtern. Manuell angelegte Personen haben zunächst keine Fotos.</p>
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800">Abbrechen</button>
          <button type="submit" disabled={mutation.isPending || !name.trim()}
            className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
            {mutation.isPending ? 'Erstelle…' : 'Hinzufügen'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

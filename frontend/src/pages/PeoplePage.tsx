import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UserPlus, Users, GitMerge, Trash2, Pencil, ArrowLeft, X } from 'lucide-react'
import { api } from '../lib/api'
import { differenceInYears } from 'date-fns'
import PhotoLightbox from '../components/gallery/PhotoLightbox'

interface Person {
  id: number
  name: string
  alias?: string
  birthdate?: string
  relationship_type?: string
  profile_face_id?: number
  notes?: string
  face_count: number
  created_at: string
}

interface Photo {
  id: number
  filename: string
  taken_at?: string
}

export default function PeoplePage() {
  const [showAdd, setShowAdd] = useState(false)
  const [selectedPerson, setSelectedPerson] = useState<Person | null>(null)
  const [mergeMode, setMergeMode] = useState(false)
  const [mergeSource, setMergeSource] = useState<Person | null>(null)
  const qc = useQueryClient()

  const { data: people = [], isLoading } = useQuery<Person[]>({
    queryKey: ['people'],
    queryFn: () => api.get('/people').then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/people/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['people'] }),
  })

  const mergeMutation = useMutation({
    mutationFn: (body: { source_id: number; target_id: number }) =>
      api.post('/people/merge', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['people'] })
      setMergeMode(false)
      setMergeSource(null)
    },
  })

  const clusterMutation = useMutation({
    mutationFn: () => api.post('/people/cluster').then(r => r.data),
    onSuccess: (d: { new_persons: number; clustered: number }) => {
      qc.invalidateQueries({ queryKey: ['people'] })
      alert(`Clustering fertig: ${d.new_persons} neue Gruppe(n) aus ${d.clustered} Gesichtern.`)
    },
  })

  const known = people.filter(p => (p.name || '').trim())
  const unknown = people.filter(p => !(p.name || '').trim())

  const { data: looseFaces = [] } = useQuery<{ id: number; photo_id: number }[]>({
    queryKey: ['unassigned-faces'],
    queryFn: () => api.get('/people/faces/unassigned', { params: { limit: 200 } }).then(r => r.data),
  })
  const newPersonFromFace = useMutation({
    mutationFn: async (faceId: number) => {
      const name = window.prompt('Name für diese Person (leer lassen = später benennen):', '')
      const res = await api.post(`/people/faces/${faceId}/new-person`)
      const pid = res.data?.person_id
      if (name && name.trim() && pid) {
        await api.patch(`/people/${pid}`, { name: name.trim() })  // also writes name into the photos
      }
      return res.data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['people'] })
      qc.invalidateQueries({ queryKey: ['unassigned-faces'] })
    },
  })

  if (selectedPerson) {
    return (
      <PersonDetail
        person={selectedPerson}
        onBack={() => setSelectedPerson(null)}
        onDeleted={() => {
          setSelectedPerson(null)
          qc.invalidateQueries({ queryKey: ['people'] })
        }}
      />
    )
  }

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">Personen</h1>
          <p className="text-sm text-zinc-400">{people.length} Personen</p>
        </div>
        <div className="flex gap-2">
          {mergeMode ? (
            <button
              onClick={() => { setMergeMode(false); setMergeSource(null) }}
              className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 text-zinc-400 text-sm hover:bg-zinc-800"
            >
              <X size={15} /> Abbrechen
            </button>
          ) : (
            <>
              <button
                onClick={() => clusterMutation.mutate()}
                disabled={clusterMutation.isPending}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 text-zinc-400 text-sm hover:bg-zinc-800 disabled:opacity-50"
                title="Unzugeordnete Gesichter zu Personen gruppieren"
              >
                <Users size={15} /> {clusterMutation.isPending ? 'Clustere…' : 'Clustern'}
              </button>
              <button
                onClick={() => setMergeMode(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-700 text-zinc-400 text-sm hover:bg-zinc-800"
              >
                <GitMerge size={15} /> Zusammenführen
              </button>
              <button
                onClick={() => setShowAdd(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
              >
                <UserPlus size={15} /> Hinzufügen
              </button>
            </>
          )}
        </div>
      </div>

      {mergeMode && (
        <div className="mb-4 p-3 rounded-lg bg-amber-900/20 border border-amber-700/40 text-sm text-amber-300">
          {mergeSource
            ? <>Wähle jetzt die Person, in die <strong className="text-amber-200">{mergeSource.name}</strong> zusammengeführt werden soll.</>
            : 'Wähle zuerst die Person, die zusammengeführt (und gelöscht) werden soll.'}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">Lade…</div>
      ) : (people.length === 0 && looseFaces.length === 0) ? (
        <EmptyPeople />
      ) : (
        (() => {
          const renderCard = (p: Person) => (
            <PersonCard
              key={p.id}
              person={p}
              mergeMode={mergeMode}
              mergeSource={mergeSource}
              onClick={() => {
                if (!mergeMode) { setSelectedPerson(p); return }
                if (!mergeSource) { setMergeSource(p); return }
                if (mergeSource.id === p.id) { setMergeSource(null); return }
                if (window.confirm(`"${mergeSource.name || 'Unbekannt'}" in "${p.name || 'Unbekannt'}" zusammenführen?`)) {
                  mergeMutation.mutate({ source_id: mergeSource.id, target_id: p.id })
                }
              }}
              onDelete={() => {
                if (window.confirm(`"${p.name || 'Unbekannt'}" wirklich löschen?`)) deleteMutation.mutate(p.id)
              }}
            />
          )
          const gridCls = "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4"
          return (
            <div className="space-y-8">
              <div>
                <h2 className="text-sm font-semibold text-zinc-300 mb-3">Bekannte Personen <span className="text-zinc-500">({known.length})</span></h2>
                {known.length ? <div className={gridCls}>{known.map(renderCard)}</div>
                  : <p className="text-sm text-zinc-500">Noch keine benannt. Klicke eine unbekannte Person an und gib ihr einen Namen.</p>}
              </div>
              {unknown.length > 0 && (
                <div>
                  <h2 className="text-sm font-semibold text-zinc-300 mb-3">Unbekannte Personen <span className="text-zinc-500">({unknown.length})</span></h2>
                  <div className={gridCls}>{unknown.map(renderCard)}</div>
                </div>
              )}
              {looseFaces.length > 0 && (
                <div>
                  <h2 className="text-sm font-semibold text-zinc-300 mb-1">Gesichter <span className="text-zinc-500">({looseFaces.length})</span></h2>
                  <p className="text-xs text-zinc-500 mb-3">Einzelne, noch nicht gruppierte Gesichter. „Clustern" gruppiert sie automatisch; oder klicke ein Gesicht, um daraus eine Person zu machen.</p>
                  <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-3">
                    {looseFaces.map(f => (
                      <button key={f.id} onClick={() => newPersonFromFace.mutate(f.id)} title="Neue Person aus diesem Gesicht"
                        className="aspect-square rounded-lg overflow-hidden bg-zinc-800 ring-1 ring-zinc-700 hover:ring-indigo-500 transition-all">
                        <img src={`/api/people/faces/${f.id}/crop`} className="w-full h-full object-cover"
                          onError={e => { (e.target as HTMLImageElement).style.opacity = '0.15' }} />
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })()
      )}

      {showAdd && <AddPersonModal onClose={() => setShowAdd(false)} />}
    </div>
  )
}

function PersonCard({ person, mergeMode, mergeSource, onClick, onDelete }: {
  person: Person
  mergeMode: boolean
  mergeSource: Person | null
  onClick: () => void
  onDelete: () => void
}) {
  const age = person.birthdate ? differenceInYears(new Date(), new Date(person.birthdate)) : null
  const isSource = mergeSource?.id === person.id
  const isTarget = mergeMode && mergeSource && mergeSource.id !== person.id

  return (
    <div
      onClick={onClick}
      className={`group relative flex flex-col items-center p-4 rounded-xl border cursor-pointer transition-all ${
        isSource
          ? 'border-amber-500 bg-amber-900/20'
          : isTarget
          ? 'border-indigo-500/50 hover:border-indigo-400 bg-zinc-900 hover:bg-indigo-900/10'
          : 'border-zinc-800 bg-zinc-900 hover:border-zinc-600 hover:shadow-lg'
      }`}
    >
      <div className="relative w-16 h-16 rounded-full overflow-hidden bg-zinc-800 mb-3 ring-2 ring-zinc-700 group-hover:ring-indigo-500/40 transition-all flex items-center justify-center">
        <span className="text-xl font-bold text-zinc-500 absolute">
          {(person.name || '?').charAt(0).toUpperCase()}
        </span>
        <img
          src={`/api/people/${person.id}/avatar`}
          className="w-full h-full object-cover absolute inset-0"
          onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      </div>

      <p className={`text-sm font-semibold text-center truncate w-full ${person.name ? 'text-white' : 'text-zinc-500 italic'}`}>{person.name || 'Unbekannt'}</p>
      <p className="text-[11px] text-zinc-500">{person.face_count} Foto{person.face_count === 1 ? '' : 's'}</p>
      {person.alias && <p className="text-xs text-zinc-500 truncate w-full text-center">{person.alias}</p>}
      {age !== null && <p className="text-xs text-zinc-500 mt-0.5">{age} J.</p>}
      <p className="text-xs text-zinc-600 mt-1">{person.face_count} Fotos</p>

      {!mergeMode && (
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity text-zinc-500 hover:text-red-400"
        >
          <Trash2 size={13} />
        </button>
      )}
      {isSource && (
        <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded text-xs bg-amber-500 text-amber-950 font-bold">
          Quelle
        </div>
      )}
    </div>
  )
}

function EmptyPeople() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Users size={48} className="text-zinc-700 mb-4" />
      <h3 className="text-lg font-semibold text-white mb-2">Noch keine Personen</h3>
      <p className="text-sm text-zinc-500 max-w-xs">
        Starte die KI-Pipeline für automatische Gesichtserkennung oder füge Personen manuell hinzu.
      </p>
    </div>
  )
}

function PersonDetail({ person, onBack, onDeleted }: {
  person: Person
  onBack: () => void
  onDeleted: () => void
}) {
  const [editing, setEditing] = useState(!(person.name || '').trim())
  const [name, setName] = useState(person.name)
  const [alias, setAlias] = useState(person.alias || '')
  const [notes, setNotes] = useState(person.notes || '')
  const [birthdate, setBirthdate] = useState(person.birthdate || '')
  const qc = useQueryClient()

  const { data: photosData } = useQuery({
    queryKey: ['person-photos', person.id],
    queryFn: () => api.get(`/people/${person.id}/photos?limit=100`).then(r => r.data),
  })

  const updateMutation = useMutation({
    mutationFn: (body: Record<string, string>) => api.patch(`/people/${person.id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['people'] }); setEditing(false) },
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/people/${person.id}`),
    onSuccess: onDeleted,
  })

  const photos: Photo[] = photosData?.items || []
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <button onClick={onBack} className="flex items-center gap-1 text-zinc-400 hover:text-white text-sm mb-6">
        <ArrowLeft size={16} /> Zurück
      </button>

      <div className="flex gap-6 mb-8">
        <div className="relative w-24 h-24 rounded-2xl overflow-hidden bg-zinc-800 ring-2 ring-zinc-700 flex-shrink-0 flex items-center justify-center">
          <span className="text-3xl font-bold text-zinc-500 absolute">{person.name.charAt(0)}</span>
          <img
            src={`/api/people/${person.id}/avatar`}
            className="w-full h-full object-cover absolute inset-0"
            onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        </div>

        <div className="flex-1">
          {editing ? (
            <div className="space-y-2">
              <input value={name} onChange={e => setName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Name" />
              <div className="flex gap-2">
                <input value={alias} onChange={e => setAlias(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Spitzname" />
                <input type="date" value={birthdate ? String(birthdate).slice(0,10) : ''} onChange={e => setBirthdate(e.target.value)}
                  className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  title="Geburtsdatum" />
              </div>
              <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
                className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="Notizen" />
              <div className="flex gap-2">
                <button onClick={() => setEditing(false)}
                  className="px-3 py-1.5 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800">
                  Abbrechen
                </button>
                <button
                  onClick={() => updateMutation.mutate({ name, alias, notes, birthdate })}
                  disabled={updateMutation.isPending || !name.trim()}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700 disabled:opacity-50">
                  Speichern
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <h1 className={`text-2xl font-bold ${person.name ? 'text-white' : 'text-zinc-500 italic'}`}>{person.name || 'Unbenannte Person'}</h1>
                <button onClick={() => setEditing(true)} className="text-zinc-500 hover:text-zinc-300" title="Bearbeiten">
                  <Pencil size={15} />
                </button>
              </div>
              {!person.name && (
                <button onClick={() => setEditing(true)} className="mt-1 text-sm text-indigo-400 hover:text-indigo-300">+ Namen vergeben</button>
              )}
              {person.alias && <p className="text-zinc-400 text-sm">„{person.alias}"</p>}
              <div className="flex items-center gap-3 text-zinc-500 text-sm mt-1">
                <span>{photosData?.total ?? person.face_count} Fotos</span>
                {person.birthdate && (
                  <span>· geb. {new Date(person.birthdate).toLocaleDateString('de')}
                    {` (${differenceInYears(new Date(), new Date(person.birthdate))} J.)`}</span>
                )}
              </div>
              {person.notes && <p className="text-zinc-400 text-sm mt-2 italic">{person.notes}</p>}
              <button
                onClick={() => { if (window.confirm(`"${person.name}" wirklich löschen?`)) deleteMutation.mutate() }}
                className="mt-3 flex items-center gap-1 text-xs text-red-400 hover:text-red-300"
              >
                <Trash2 size={12} /> Person löschen
              </button>
            </>
          )}
        </div>
      </div>

      <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wider mb-3">
        Fotos ({photosData?.total ?? photos.length})
      </h2>
      <div className="grid grid-cols-3 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-8 gap-1.5">
        {photos.map((photo, i) => (
          <div key={photo.id} className="group relative aspect-square rounded-lg overflow-hidden bg-zinc-800 cursor-pointer"
            onClick={() => setLightboxIndex(i)}>
            <img
              src={`/api/photos/${photo.id}/thumbnail?size=small`}
              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              loading="lazy"
            />
            {(photo as any).is_video && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="bg-black/50 rounded-full p-1.5"><svg width="12" height="12" viewBox="0 0 24 24" fill="white"><path d="M8 5v14l11-7z"/></svg></div>
              </div>
            )}
          </div>
        ))}
      </div>
      {photos.length === 0 && (
        <p className="text-sm text-zinc-500">Noch keine Fotos — Gesichtserkennung läuft beim Verarbeiten.</p>
      )}

      {lightboxIndex !== null && (
        <PhotoLightbox photos={photos as any} initialIndex={lightboxIndex} onClose={() => setLightboxIndex(null)} />
      )}
    </div>
  )
}

function AddPersonModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [alias, setAlias] = useState('')
  const [birthdate, setBirthdate] = useState('')
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: (data: Record<string, string>) => api.post('/people', data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['people'] }); onClose() },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="bg-zinc-900 rounded-2xl p-6 w-full max-w-sm border border-zinc-800 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-white">Person hinzufügen</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>
        <form
          onSubmit={e => { e.preventDefault(); mutation.mutate({ name, alias, birthdate }) }}
          className="space-y-3"
        >
          <input required placeholder="Name *" value={name} onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <input placeholder="Alias / Spitzname" value={alias} onChange={e => setAlias(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <div>
            <label className="block text-xs text-zinc-400 mb-1">Geburtsdatum (optional)</label>
            <input type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          </div>
          <div className="flex gap-2 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800">
              Abbrechen
            </button>
            <button type="submit" disabled={mutation.isPending}
              className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
              {mutation.isPending ? 'Erstelle…' : 'Hinzufügen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { UserPlus, Users } from 'lucide-react'
import { api, Person } from '../lib/api'
import { format, differenceInYears } from 'date-fns'
import { de } from 'date-fns/locale'

export default function PeoplePage() {
  const [showAdd, setShowAdd] = useState(false)
  const qc = useQueryClient()

  const { data: people = [], isLoading } = useQuery<Person[]>({
    queryKey: ['people'],
    queryFn: () => api.get('/people').then((r) => r.data),
  })

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">Personen</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">{people.length} Personen</p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <UserPlus size={16} />
          <span className="hidden sm:block">Person hinzufügen</span>
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16 text-gray-400">Lade…</div>
      ) : people.length === 0 ? (
        <EmptyPeople />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
          {people.map((p) => <PersonCard key={p.id} person={p} />)}
        </div>
      )}

      {showAdd && <AddPersonModal onClose={() => setShowAdd(false)} />}
    </div>
  )
}

function PersonCard({ person }: { person: Person }) {
  const age = person.birthdate ? differenceInYears(new Date(), new Date(person.birthdate)) : null

  return (
    <div className="flex flex-col items-center p-4 rounded-xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 hover:shadow-md transition-shadow cursor-pointer">
      <div className="w-16 h-16 rounded-full bg-indigo-100 dark:bg-indigo-900/40 flex items-center justify-center mb-3">
        <span className="text-xl font-bold text-indigo-600 dark:text-indigo-400">
          {person.name.charAt(0).toUpperCase()}
        </span>
      </div>
      <p className="text-sm font-semibold text-gray-900 dark:text-white text-center truncate w-full">{person.name}</p>
      {age !== null && <p className="text-xs text-gray-400 mt-0.5">{age} Jahre</p>}
      {person.face_count !== undefined && (
        <p className="text-xs text-gray-400 mt-1">{person.face_count} Fotos</p>
      )}
    </div>
  )
}

function EmptyPeople() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Users size={48} className="text-gray-300 dark:text-gray-700 mb-4" />
      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Noch keine Personen</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xs">
        Starte die AI-Pipeline um Gesichter automatisch zu erkennen, oder füge Personen manuell hinzu.
      </p>
    </div>
  )
}

function AddPersonModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [birthdate, setBirthdate] = useState('')
  const qc = useQueryClient()

  const mutation = useMutation({
    mutationFn: (data: { name: string; birthdate?: string }) => api.post('/people', data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['people'] }); onClose() },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-gray-900 rounded-2xl p-6 w-full max-w-sm shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4">Person hinzufügen</h2>
        <form
          onSubmit={(e) => { e.preventDefault(); mutation.mutate({ name, birthdate: birthdate || undefined }) }}
          className="space-y-3"
        >
          <input
            required
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <input
            type="date"
            placeholder="Geburtsdatum (optional)"
            value={birthdate}
            onChange={(e) => setBirthdate(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800">
              Abbrechen
            </button>
            <button type="submit" disabled={mutation.isPending} className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
              Hinzufügen
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

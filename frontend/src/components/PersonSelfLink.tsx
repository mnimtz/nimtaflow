import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

/** „Das bin ich" — verknüpft das EIGENE (eingeloggte) Konto mit einer erkannten Person.
 *  Pro-User über /auth/me/person; genutzt im Profil UND in den Einstellungen. */
export default function PersonSelfLink() {
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const { data: me } = useQuery<{ person_id: number | null }>({
    queryKey: ['auth-me'], queryFn: () => api.get('/auth/me').then(r => r.data), staleTime: 30_000,
  })
  const { data: people = [] } = useQuery<{ id: number; name: string }[]>({
    queryKey: ['people-min'], queryFn: () => api.get('/people').then(r => r.data), staleTime: 300_000,
  })
  const named = people.filter(p => (p.name || '').trim())
  const linked = me?.person_id ? named.find(p => p.id === me.person_id) : undefined
  const setPerson = useMutation({
    mutationFn: (person_id: number | null) => api.put('/auth/me/person', { person_id }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['auth-me'] }); qc.invalidateQueries({ queryKey: ['me'] }); qc.invalidateQueries({ queryKey: ['profile'] }) },
  })
  const matches = q.trim()
    ? named.filter(p => p.id !== me?.person_id && p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 30)
    : []
  const inp = 'w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500'
  return (
    <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/50 dark:bg-indigo-950/20 p-3">
      <div className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Das bin ich (Profil ↔ Person)</div>
      <div className="text-[11px] text-zinc-500 mb-2">Verknüpfe dein Konto mit deiner erkannten Person — dann versteht der Assistent „meine Frau", „mein Sohn" und „wann habe ich … das erste Mal getroffen".</div>
      {linked ? (
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-indigo-600 text-white text-xs">
            {linked.name}
            <button type="button" onClick={() => setPerson.mutate(null)} className="hover:text-red-200">✕</button>
          </span>
          <span className="text-[11px] text-zinc-400">verknüpft</span>
        </div>
      ) : (
        <div className="relative">
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Person suchen …" className={inp} />
          {q.trim() && matches.length > 0 && (
            <div className="absolute z-20 mt-1 w-full max-h-52 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg">
              {matches.map(p => (
                <button key={p.id} type="button" onClick={() => { setPerson.mutate(p.id); setQ('') }}
                  className="block w-full text-left px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800">{p.name}</button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

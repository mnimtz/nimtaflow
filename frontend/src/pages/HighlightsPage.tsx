import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Sparkles, Film, Trash2, Plus, X, Clock } from 'lucide-react'

type Motto = { key: string; label: string; params: string[] }
type Highlight = {
  id: number; title: string; motto: string; status: string
  duration_sec: number; photo_count: number; cover_photo_id: number | null
  error_message: string | null; created_at: string
}

export default function HighlightsPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [play, setPlay] = useState<Highlight | null>(null)

  const { data: list = [] } = useQuery<Highlight[]>({
    queryKey: ['highlights'],
    queryFn: () => api.get('/highlights').then(r => r.data),
    refetchInterval: q => (Array.isArray(q.state.data) && q.state.data.some((h: Highlight) => h.status === 'pending' || h.status === 'rendering') ? 4000 : false),
  })
  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/highlights/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['highlights'] }),
  })

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
      <div className="flex items-center gap-3 mb-6">
        <Sparkles className="text-indigo-500" />
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">Highlights</h1>
        <button onClick={() => setShowCreate(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
          <Plus size={16} /> Neues Highlight-Video
        </button>
      </div>

      {list.length === 0 && (
        <div className="flex flex-col items-center py-20 text-zinc-500">
          <Film size={40} className="mb-3" />
          <p>Noch keine Highlight-Videos. Erstelle dein erstes oben rechts.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {list.map(h => (
          <div key={h.id} className="rounded-2xl border border-zinc-200 dark:border-zinc-700 overflow-hidden bg-zinc-50 dark:bg-zinc-800/40">
            <button onClick={() => h.status === 'done' && setPlay(h)}
              className="relative block w-full aspect-video bg-zinc-200 dark:bg-zinc-800">
              {h.cover_photo_id && <img src={`/api/photos/${h.cover_photo_id}/thumbnail?size=medium`} className="w-full h-full object-cover" />}
              <span className="absolute inset-0 flex items-center justify-center">
                {h.status === 'done'
                  ? <span className="w-12 h-12 rounded-full bg-black/50 text-white flex items-center justify-center"><Film size={22} /></span>
                  : <span className="px-3 py-1 rounded-full bg-black/60 text-white text-xs flex items-center gap-1.5">
                      <Clock size={12} /> {h.status === 'error' ? 'Fehler' : h.status === 'rendering' ? 'Wird erstellt…' : 'Wartet…'}
                    </span>}
              </span>
            </button>
            <div className="p-3 flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-zinc-900 dark:text-white truncate">{h.title}</p>
                <p className="text-xs text-zinc-500">{h.photo_count} Fotos · {Math.round(h.duration_sec)}s</p>
                {h.error_message && <p className="text-xs text-red-500 mt-0.5 line-clamp-2">{h.error_message}</p>}
              </div>
              <button onClick={() => del.mutate(h.id)} className="text-zinc-400 hover:text-red-500 shrink-0"><Trash2 size={15} /></button>
            </div>
          </div>
        ))}
      </div>

      {showCreate && <CreateHighlight onClose={() => setShowCreate(false)} onCreated={() => { setShowCreate(false); qc.invalidateQueries({ queryKey: ['highlights'] }) }} />}

      {play && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setPlay(null)}>
          <button className="absolute top-4 right-4 text-white/80 hover:text-white"><X size={28} /></button>
          <video src={`/api/highlights/${play.id}/video?access_token=${localStorage.getItem('access_token')}`}
            controls autoPlay className="max-h-[90vh] max-w-[95vw]" onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  )
}

function CreateHighlight({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [motto, setMotto] = useState('')
  const [title, setTitle] = useState('')
  const [duration, setDuration] = useState(60)
  const [personId, setPersonId] = useState<number | ''>('')
  const [personId2, setPersonId2] = useState<number | ''>('')
  const [year, setYear] = useState('')
  const [albumId, setAlbumId] = useState<number | ''>('')
  const [season, setSeason] = useState('weihnachten')

  const { data: mottos = [] } = useQuery<Motto[]>({ queryKey: ['highlight-mottos'], queryFn: () => api.get('/highlights/mottos').then(r => r.data.mottos) })
  const { data: people = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['people-min'], queryFn: () => api.get('/people').then(r => r.data) })
  const { data: albums = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['albums'], queryFn: () => api.get('/albums').then(r => r.data) })
  const named = people.filter(p => (p.name || '').trim())
  const m = mottos.find(x => x.key === motto)
  const needs = (p: string) => m?.params?.includes(p)

  const create = useMutation({
    mutationFn: () => api.post('/highlights', {
      motto, title: title || m?.label, duration_sec: duration,
      ...(needs('person') && personId ? { person_id: personId } : {}),
      ...(needs('person2') && personId2 ? { person_id2: personId2 } : {}),
      ...(needs('year') && year ? { year: Number(year) } : {}),
      ...(needs('album') && albumId ? { album_id: albumId } : {}),
      ...(needs('season') ? { season } : {}),
    }),
    onSuccess: onCreated,
  })

  const sel = 'w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 text-sm'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 rounded-2xl p-6 w-full max-w-md border border-zinc-200 dark:border-zinc-800 space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-zinc-900 dark:text-white">Highlight-Video erstellen</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>

        <div>
          <label className="block text-xs text-zinc-500 mb-1">Motto</label>
          <select value={motto} onChange={e => setMotto(e.target.value)} className={sel}>
            <option value="">— wählen —</option>
            {mottos.map(x => <option key={x.key} value={x.key}>{x.label}</option>)}
          </select>
        </div>

        {needs('person') && (
          <div><label className="block text-xs text-zinc-500 mb-1">Person</label>
            <select value={personId} onChange={e => setPersonId(e.target.value ? Number(e.target.value) : '')} className={sel}>
              <option value="">— wählen —</option>{named.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
        )}
        {needs('person2') && (
          <div><label className="block text-xs text-zinc-500 mb-1">Zweite Person (z. B. das Kind)</label>
            <select value={personId2} onChange={e => setPersonId2(e.target.value ? Number(e.target.value) : '')} className={sel}>
              <option value="">— wählen —</option>{named.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select></div>
        )}
        {needs('year') && (
          <div><label className="block text-xs text-zinc-500 mb-1">Jahr</label>
            <input value={year} onChange={e => setYear(e.target.value)} placeholder="z. B. 2023" className={sel} /></div>
        )}
        {needs('album') && (
          <div><label className="block text-xs text-zinc-500 mb-1">Album / Reise</label>
            <select value={albumId} onChange={e => setAlbumId(e.target.value ? Number(e.target.value) : '')} className={sel}>
              <option value="">— wählen —</option>{albums.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select></div>
        )}
        {needs('season') && (
          <div><label className="block text-xs text-zinc-500 mb-1">Jahreszeit / Anlass</label>
            <select value={season} onChange={e => setSeason(e.target.value)} className={sel}>
              <option value="weihnachten">Weihnachten</option><option value="ostern">Ostern</option>
              <option value="sommer">Sommer</option><option value="winter">Winter</option>
              <option value="herbst">Herbst</option><option value="halloween">Halloween</option>
            </select></div>
        )}

        <div>
          <label className="block text-xs text-zinc-500 mb-1">Titel (optional)</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder={m?.label || 'Mein Highlight'} className={sel} />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Länge: {duration}s</label>
          <input type="range" min={15} max={180} step={15} value={duration} onChange={e => setDuration(Number(e.target.value))} className="w-full" />
        </div>

        <button onClick={() => create.mutate()} disabled={!motto || create.isPending}
          className="w-full py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
          {create.isPending ? 'Wird erstellt…' : 'Video erstellen'}
        </button>
        <p className="text-[11px] text-zinc-400">Das Rendern läuft im Hintergrund (ffmpeg) und erscheint dann in der Liste.</p>
      </div>
    </div>
  )
}

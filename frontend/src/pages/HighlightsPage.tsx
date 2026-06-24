import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useToast } from '../components/ui/dialogs'
import { Sparkles, Film, Trash2, Plus, X, Clock } from 'lucide-react'
import { useT } from '../i18n'

type Motto = { motto: string; label: string; params: string[]; description?: string }
type Highlight = {
  id: number; title: string; motto: string; status: string
  duration_sec: number; photo_count: number; cover_photo_id: number | null
  error_message: string | null; created_at: string
}

export default function HighlightsPage() {
  const { t } = useT()
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
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">{t('highlights.title')}</h1>
        <button onClick={() => setShowCreate(true)}
          className="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500">
          <Plus size={16} /> {t('highlights.newVideo')}
        </button>
      </div>

      {list.length === 0 && (
        <div className="flex flex-col items-center py-20 text-zinc-500">
          <Film size={40} className="mb-3" />
          <p>{t('highlights.empty')}</p>
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
                      <Clock size={12} /> {h.status === 'error' ? t('highlights.statusError') : h.status === 'rendering' ? t('highlights.statusRendering') : t('highlights.statusPending')}
                    </span>}
              </span>
            </button>
            <div className="p-3 flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-zinc-900 dark:text-white truncate">{h.title}</p>
                <p className="text-xs text-zinc-500">{t('highlights.photosDuration', { count: h.photo_count, sec: Math.round(h.duration_sec) })}</p>
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
          <video src={`/api/highlights/${play.id}/video`}
            controls autoPlay playsInline className="max-h-[90vh] max-w-[95vw]" onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  )
}

function CreateHighlight({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const { t } = useT()
  const [motto, setMotto] = useState('')
  const [title, setTitle] = useState('')
  const [duration, setDuration] = useState(60)
  const [personId, setPersonId] = useState<number | ''>('')
  const [personId2, setPersonId2] = useState<number | ''>('')
  const [personIds, setPersonIds] = useState<number[]>([])
  const [year, setYear] = useState('')
  const [albumId, setAlbumId] = useState<number | ''>('')
  const [season, setSeason] = useState('weihnachten')
  const [aiClips, setAiClips] = useState(false)

  const { data: mottos = [] } = useQuery<Motto[]>({ queryKey: ['highlight-mottos'], queryFn: () => api.get('/highlights/mottos').then(r => r.data.mottos) })
  const { data: people = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['people-min'], queryFn: () => api.get('/people').then(r => r.data) })
  const { data: albums = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['albums'], queryFn: () => api.get('/albums').then(r => r.data) })
  const { data: settings = {} } = useQuery<Record<string, string>>({ queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000 })
  const named = people.filter(p => (p.name || '').trim())
  const m = mottos.find(x => x.motto === motto)
  const needs = (p: string) => m?.params?.includes(p)
  // KI-Clips only make sense for recap-style mottos (must match the worker's allow-list).
  const AI_MOTTOS = ['week_review', 'year_review', 'album_highlight', 'season', 'through_the_years', 'newest_50']
  const aiAvailable = AI_MOTTOS.includes(motto)
  const aiEnabled = (settings['highlights.ai_enabled'] ?? 'false') === 'true'

  const toast = useToast()
  const create = useMutation({
    mutationFn: () => api.post('/highlights', {
      motto, title: title || m?.label, duration_sec: duration,
      ...(needs('person') && personId ? { person_id: personId } : {}),
      ...(needs('person2') && personId2 ? { person_id2: personId2 } : {}),
      ...(needs('people') && personIds.length ? { person_ids: personIds } : {}),
      ...(needs('year') && year ? { year: Number(year) } : {}),
      ...(needs('album') && albumId ? { album_id: albumId } : {}),
      ...(needs('season') ? { season } : {}),
      ...(aiAvailable && aiClips && aiEnabled ? { ai_clips: true } : {}),
    }),
    onSuccess: () => { toast(t('highlights.toastCreated'), 'success'); onCreated() },
    onError: (e: any) => toast(e?.response?.data?.detail || t('highlights.toastError'), 'error'),
  })

  const ready = !!motto
    && (!needs('person') || !!personId)
    && (!needs('person2') || !!personId2)
    && (!needs('people') || personIds.length >= 2)
    && (!needs('year') || !!year.trim())
    && (!needs('album') || !!albumId)

  const sel = 'w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 text-sm'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 rounded-2xl p-6 w-full max-w-md border border-zinc-200 dark:border-zinc-800 space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-zinc-900 dark:text-white">{t('highlights.createTitle')}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>

        <div>
          <label className="block text-xs text-zinc-500 mb-1">{t('highlights.motto')}</label>
          <select value={motto} onChange={e => setMotto(e.target.value)} className={sel}>
            <option value="">{t('highlights.choose')}</option>
            {mottos.map(x => <option key={x.motto} value={x.motto}>{x.label}</option>)}
          </select>
          {m?.description && <p className="text-[11px] text-zinc-500 mt-1">{m.description}</p>}
        </div>

        {needs('person') && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('highlights.person')}</label>
            <PersonCombobox people={named} value={personId} onChange={setPersonId} /></div>
        )}
        {needs('person2') && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('highlights.person2')}</label>
            <PersonCombobox people={named} value={personId2} onChange={setPersonId2} exclude={personId ? [personId] : []} /></div>
        )}
        {needs('people') && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('highlights.people')}</label>
            <PersonMultiPicker people={named} value={personIds} onChange={setPersonIds} /></div>
        )}
        {needs('year') && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('highlights.year')}</label>
            <input value={year} onChange={e => setYear(e.target.value)} placeholder={t('highlights.yearPlaceholder')} className={sel} /></div>
        )}
        {needs('album') && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('highlights.albumTrip')}</label>
            <select value={albumId} onChange={e => setAlbumId(e.target.value ? Number(e.target.value) : '')} className={sel}>
              <option value="">{t('highlights.choose')}</option>{albums.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select></div>
        )}
        {needs('season') && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('highlights.season')}</label>
            <select value={season} onChange={e => setSeason(e.target.value)} className={sel}>
              <option value="weihnachten">{t('highlights.seasonChristmas')}</option><option value="ostern">{t('highlights.seasonEaster')}</option>
              <option value="sommer">{t('highlights.seasonSummer')}</option><option value="winter">{t('highlights.seasonWinter')}</option>
              <option value="herbst">{t('highlights.seasonAutumn')}</option><option value="halloween">{t('highlights.seasonHalloween')}</option>
            </select></div>
        )}

        {aiAvailable && (
          <div className="rounded-xl border border-indigo-200 dark:border-indigo-900/60 bg-indigo-50/60 dark:bg-indigo-950/30 p-3">
            <label className={`flex items-start gap-2.5 ${aiEnabled ? 'cursor-pointer' : 'opacity-60'}`}>
              <input type="checkbox" checked={aiClips && aiEnabled} disabled={!aiEnabled}
                onChange={e => setAiClips(e.target.checked)} className="mt-0.5 accent-indigo-600" />
              <span className="text-sm">
                <span className="font-medium text-zinc-800 dark:text-zinc-100">✨ {t('highlights.aiClips')}</span>
                <span className="block text-[11px] text-zinc-500 mt-0.5">{t('highlights.aiClipsDesc')}</span>
                {!aiEnabled && <span className="block text-[11px] text-amber-600 dark:text-amber-400 mt-1">{t('highlights.aiClipsOff')}</span>}
              </span>
            </label>
          </div>
        )}

        <div>
          <label className="block text-xs text-zinc-500 mb-1">{t('highlights.titleOptional')}</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder={m?.label || t('highlights.titlePlaceholder')} className={sel} />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 mb-1">{t('highlights.length', { sec: duration })}</label>
          <input type="range" min={15} max={180} step={15} value={duration} onChange={e => setDuration(Number(e.target.value))} className="w-full" />
        </div>

        <button onClick={() => create.mutate()} disabled={!ready || create.isPending}
          className="w-full py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
          {create.isPending ? t('highlights.btnCreating') : !motto ? t('highlights.btnChooseMotto') : !ready ? t('highlights.btnCompleteSelection') : t('highlights.btnCreateVideo')}
        </button>
        <p className="text-[11px] text-zinc-400">{t('highlights.renderHint')}</p>
      </div>
    </div>
  )
}

type PMin = { id: number; name: string }
const PICKER_INPUT = 'w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

// Single person picker with search-while-typing.
function PersonCombobox({ people, value, onChange, exclude = [] }: {
  people: PMin[]; value: number | ''; onChange: (id: number | '') => void; exclude?: number[]
}) {
  const { t } = useT()
  const [q, setQ] = useState('')
  const picked = value ? people.find(p => p.id === value) : undefined
  const matches = q.trim()
    ? people.filter(p => !exclude.includes(p.id) && p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 30)
    : []
  return (
    <div className="relative">
      <input value={picked ? picked.name : q}
        onChange={e => { setQ(e.target.value); if (value) onChange('') }}
        placeholder={t('highlights.searchPerson', { count: people.length })} className={PICKER_INPUT} />
      {picked && (
        <button onClick={() => { onChange(''); setQ('') }}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-red-500"><X size={14} /></button>
      )}
      {!picked && q.trim() && matches.length > 0 && (
        <div className="absolute z-20 mt-1 w-full max-h-52 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg">
          {matches.map(p => (
            <button key={p.id} onClick={() => { onChange(p.id); setQ('') }}
              className="block w-full text-left px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800">{p.name}</button>
          ))}
        </div>
      )}
    </div>
  )
}

// Multi person picker (chips) with search-while-typing.
function PersonMultiPicker({ people, value, onChange }: {
  people: PMin[]; value: number[]; onChange: (ids: number[]) => void
}) {
  const { t } = useT()
  const [q, setQ] = useState('')
  const selected = people.filter(p => value.includes(p.id))
  const matches = q.trim()
    ? people.filter(p => !value.includes(p.id) && p.name.toLowerCase().includes(q.toLowerCase())).slice(0, 30)
    : []
  return (
    <div>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {selected.map(p => (
            <span key={p.id} className="flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-indigo-600 text-white text-xs">
              {p.name}
              <button onClick={() => onChange(value.filter(x => x !== p.id))} className="hover:text-red-200"><X size={11} /></button>
            </span>
          ))}
        </div>
      )}
      <div className="relative">
        <input value={q} onChange={e => setQ(e.target.value)}
          placeholder={t('highlights.addPerson', { count: people.length })} className={PICKER_INPUT} />
        {q.trim() && matches.length > 0 && (
          <div className="absolute z-20 mt-1 w-full max-h-52 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 shadow-lg">
            {matches.map(p => (
              <button key={p.id} onClick={() => { onChange([...value, p.id]); setQ('') }}
                className="block w-full text-left px-3 py-1.5 text-sm text-zinc-800 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800">{p.name}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, FolderOpen, Sparkles, Brain, Trash2, RefreshCw, ChevronRight, X, Share2, Pencil } from 'lucide-react'
import ShareDialog from '../components/ShareDialog'
import { api, thumbUrl } from '../lib/api'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'

type AlbumType = 'manual' | 'smart' | 'ai'

interface Album {
  id: number
  name: string
  description?: string
  album_type: AlbumType
  cover_photo_id?: number
  smart_criteria?: Record<string, unknown>
  ai_prompt?: string
  ai_last_evaluated?: string
  photo_count: number
  created_at: string
  updated_at: string
}

interface AlbumPhoto {
  id: number
  filename: string
  thumb_medium?: string
}

const TYPE_ICONS: Record<AlbumType, typeof FolderOpen> = {
  manual: FolderOpen,
  smart: Sparkles,
  ai: Brain,
}
const TYPE_LABELS: Record<AlbumType, string> = {
  manual: 'Manuell',
  smart: 'Smart',
  ai: 'KI-Album',
}
const TYPE_COLORS: Record<AlbumType, string> = {
  manual: 'bg-zinc-800 text-zinc-300',
  smart: 'bg-indigo-900/60 text-indigo-300',
  ai: 'bg-violet-900/60 text-violet-300',
}

export default function AlbumsPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [selectedAlbum, setSelectedAlbum] = useState<Album | null>(null)
  const qc = useQueryClient()

  const { data: albums = [], isLoading } = useQuery<Album[]>({
    queryKey: ['albums'],
    queryFn: () => api.get('/albums').then(r => r.data),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.delete(`/albums/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['albums'] }),
  })

  const refreshMutation = useMutation({
    mutationFn: (id: number) => api.post(`/albums/${id}/refresh`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['albums'] }),
  })

  if (selectedAlbum) {
    return <AlbumDetail album={selectedAlbum} onBack={() => setSelectedAlbum(null)} />
  }

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">Alben</h1>
          <p className="text-sm text-zinc-400">{albums.length} Alben</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <Plus size={16} /> Neues Album
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">Lade…</div>
      ) : albums.length === 0 ? (
        <EmptyAlbums onCreateClick={() => setShowCreate(true)} />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
          {albums.map(album => (
            <AlbumCard
              key={album.id}
              album={album}
              onClick={() => setSelectedAlbum(album)}
              onDelete={() => deleteMutation.mutate(album.id)}
              onRefresh={() => refreshMutation.mutate(album.id)}
            />
          ))}
        </div>
      )}

      {showCreate && <CreateAlbumModal onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function AlbumCard({ album, onClick, onDelete, onRefresh }: {
  album: Album
  onClick: () => void
  onDelete: () => void
  onRefresh: () => void
}) {
  const Icon = TYPE_ICONS[album.album_type]
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <div
      className="group relative rounded-xl overflow-hidden bg-zinc-900 border border-zinc-800 cursor-pointer hover:border-zinc-600 transition-all"
      onClick={onClick}
    >
      {/* Cover */}
      <div className="aspect-square bg-zinc-800 flex items-center justify-center">
        {album.cover_photo_id ? (
          <img
            src={thumbUrl({ id: album.cover_photo_id }, 'medium')}
            className="w-full h-full object-cover"
          />
        ) : (
          <Icon size={36} className="text-zinc-600" />
        )}
      </div>

      {/* Info */}
      <div className="p-3">
        <p className="text-sm font-semibold text-white truncate">{album.name}</p>
        <div className="flex items-center justify-between mt-1">
          <span className="text-xs text-zinc-500">{album.photo_count} Fotos</span>
          <span className={`text-xs px-1.5 py-0.5 rounded ${TYPE_COLORS[album.album_type]}`}>
            {TYPE_LABELS[album.album_type]}
          </span>
        </div>
      </div>

      {/* Actions overlay */}
      <div
        className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={e => e.stopPropagation()}
      >
        {album.album_type !== 'manual' && (
          <button
            onClick={onRefresh}
            title="Aktualisieren"
            className="p-1 rounded bg-black/60 text-zinc-300 hover:text-white"
          >
            <RefreshCw size={13} />
          </button>
        )}
        <button
          onClick={onDelete}
          title="Löschen"
          className="p-1 rounded bg-black/60 text-zinc-300 hover:text-red-400"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  )
}

function EmptyAlbums({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <FolderOpen size={48} className="text-zinc-700 mb-4" />
      <h3 className="text-lg font-semibold text-white mb-2">Noch keine Alben</h3>
      <p className="text-sm text-zinc-500 max-w-xs mb-6">
        Erstelle manuelle Alben, regelbasierte Smart-Alben oder lass die KI passende Fotos finden.
      </p>
      <button
        onClick={onCreateClick}
        className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
      >
        Erstes Album erstellen
      </button>
    </div>
  )
}

// ── Create modal ─────────────────────────────────────────────────────────────

function CreateAlbumModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('')
  const [type, setType] = useState<AlbumType>('manual')
  const [aiPrompt, setAiPrompt] = useState('')
  const [smartDate, setSmartDate] = useState({ from: '', to: '' })
  const [smartFavorites, setSmartFavorites] = useState(false)
  const [smartMediaType, setSmartMediaType] = useState('')
  const [smartPersons, setSmartPersons] = useState<number[]>([])
  const [personMatch, setPersonMatch] = useState<'any' | 'all'>('any')
  const qc = useQueryClient()

  const { data: people = [] } = useQuery<{ id: number; name: string; face_count: number }[]>({
    queryKey: ['people-for-album'],
    queryFn: () => api.get('/people').then(r => r.data),
    enabled: type === 'smart',
  })
  const togglePerson = (id: number) =>
    setSmartPersons(ps => ps.includes(id) ? ps.filter(x => x !== id) : [...ps, id])

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post('/albums', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['albums'] }); onClose() },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const body: Record<string, unknown> = { name, album_type: type }
    if (type === 'ai') body.ai_prompt = aiPrompt
    if (type === 'smart') {
      body.smart_criteria = {
        ...(smartDate.from ? { date_from: smartDate.from } : {}),
        ...(smartDate.to ? { date_to: smartDate.to } : {}),
        ...(smartFavorites ? { favorites: true } : {}),
        ...(smartMediaType ? { media_type: smartMediaType } : {}),
        ...(smartPersons.length ? { person_ids: smartPersons, person_match: personMatch } : {}),
      }
    }
    create.mutate(body)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="bg-zinc-900 rounded-2xl p-6 w-full max-w-md border border-zinc-800 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-white">Neues Album</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            required
            placeholder="Album-Name"
            value={name}
            onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />

          {/* Type selector */}
          <div className="grid grid-cols-3 gap-2">
            {(['manual', 'smart', 'ai'] as AlbumType[]).map(t => {
              const Icon = TYPE_ICONS[t]
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => setType(t)}
                  className={`flex flex-col items-center gap-1 py-3 rounded-lg border text-xs font-medium transition-all ${
                    type === t
                      ? 'border-indigo-500 bg-indigo-900/40 text-indigo-300'
                      : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'
                  }`}
                >
                  <Icon size={18} />
                  {TYPE_LABELS[t]}
                </button>
              )
            })}
          </div>

          {type === 'ai' && (
            <div>
              <label className="block text-xs text-zinc-400 mb-1">KI-Prompt</label>
              <textarea
                placeholder='z.B. "Strandfotos mit Familie", "Sonnenuntergänge 2023"'
                value={aiPrompt}
                onChange={e => setAiPrompt(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
              <p className="text-xs text-zinc-500 mt-1">Die KI sucht Fotos deren Beschreibung zum Prompt passt.</p>
            </div>
          )}

          {type === 'smart' && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Von</label>
                  <input type="date" value={smartDate.from} onChange={e => setSmartDate(d => ({ ...d, from: e.target.value }))}
                    className="w-full px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">Bis</label>
                  <input type="date" value={smartDate.to} onChange={e => setSmartDate(d => ({ ...d, to: e.target.value }))}
                    className="w-full px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
              </div>
              <select value={smartMediaType} onChange={e => setSmartMediaType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="">Alle Medientypen</option>
                <option value="photo">Nur Fotos</option>
                <option value="video">Nur Videos</option>
              </select>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={smartFavorites} onChange={e => setSmartFavorites(e.target.checked)}
                  className="rounded accent-indigo-500" />
                Nur Favoriten
              </label>

              {/* Personen-Filter */}
              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Personen</label>
                {people.length === 0 ? (
                  <p className="text-xs text-zinc-500">Noch keine Personen erkannt.</p>
                ) : (
                  <>
                    <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto p-1">
                      {people.map(p => {
                        const sel = smartPersons.includes(p.id)
                        return (
                          <button key={p.id} type="button" onClick={() => togglePerson(p.id)}
                            className={`flex items-center gap-1.5 pl-1 pr-2.5 py-1 rounded-full border text-xs transition-colors ${
                              sel ? 'border-indigo-500 bg-indigo-900/40 text-indigo-200' : 'border-zinc-700 text-zinc-300 hover:bg-zinc-800'
                            }`}>
                            <span className="w-5 h-5 rounded-full overflow-hidden bg-zinc-700 flex items-center justify-center text-[9px]">
                              <img src={`/api/people/${p.id}/avatar`} className="w-full h-full object-cover"
                                onError={e => { (e.target as HTMLImageElement).style.display = 'none' }} />
                            </span>
                            {p.name || 'Unbekannt'}
                          </button>
                        )
                      })}
                    </div>
                    {smartPersons.length >= 2 && (
                      <div className="flex gap-1 mt-2 text-xs">
                        <button type="button" onClick={() => setPersonMatch('any')}
                          className={`px-2.5 py-1 rounded-lg border ${personMatch === 'any' ? 'border-indigo-500 bg-indigo-900/40 text-indigo-200' : 'border-zinc-700 text-zinc-400'}`}>
                          irgendeine Person
                        </button>
                        <button type="button" onClick={() => setPersonMatch('all')}
                          className={`px-2.5 py-1 rounded-lg border ${personMatch === 'all' ? 'border-indigo-500 bg-indigo-900/40 text-indigo-200' : 'border-zinc-700 text-zinc-400'}`}>
                          alle zusammen
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 py-2 rounded-lg border border-zinc-700 text-sm text-zinc-400 hover:bg-zinc-800">
              Abbrechen
            </button>
            <button type="submit" disabled={create.isPending}
              className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
              {create.isPending ? 'Erstelle…' : 'Erstellen'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Album detail view ─────────────────────────────────────────────────────────

function AlbumDetail({ album, onBack }: { album: Album; onBack: () => void }) {
  const qc = useQueryClient()
  const [showShare, setShowShare] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [sort, setSort] = useState('newest')
  const [lightbox, setLightbox] = useState<AlbumPhoto | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['album-photos', album.id, sort],
    queryFn: () => api.get(`/albums/${album.id}/photos?limit=500&sort=${sort}`).then(r => r.data),
  })

  const photos: AlbumPhoto[] = data?.items || []
  const Icon = TYPE_ICONS[album.album_type]

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={onBack} className="text-zinc-400 hover:text-white transition-colors">
          ← Zurück
        </button>
        <div className="flex items-center gap-2">
          <Icon size={18} className="text-zinc-400" />
          <h1 className="text-xl font-bold text-white">{album.name}</h1>
          <span className={`text-xs px-2 py-0.5 rounded ${TYPE_COLORS[album.album_type]}`}>
            {TYPE_LABELS[album.album_type]}
          </span>
        </div>
        <span className="text-sm text-zinc-500 ml-auto">{album.photo_count} Fotos</span>
        <select value={sort} onChange={e => setSort(e.target.value)}
          className="text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 px-2 py-1">
          <option value="newest">Neueste zuerst</option>
          <option value="oldest">Älteste zuerst</option>
          <option value="order">Album-Reihenfolge</option>
          <option value="name">Name</option>
        </select>
        <button onClick={() => setShowEdit(true)}
          className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
          <Pencil size={15} /> Bearbeiten
        </button>
        <button onClick={() => setShowShare(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300">
          <Share2 size={15} /> Teilen
        </button>
      </div>
      {showShare && <ShareDialog target={{ kind: 'album', albumId: album.id, title: album.name }} onClose={() => setShowShare(false)} />}
      {showEdit && <AlbumEditModal album={album} onClose={() => setShowEdit(false)}
        onSaved={() => { setShowEdit(false); qc.invalidateQueries({ queryKey: ['albums'] }); qc.invalidateQueries({ queryKey: ['album-photos', album.id] }) }}
        onDeleted={() => { setShowEdit(false); qc.invalidateQueries({ queryKey: ['albums'] }); onBack() }} />}

      {album.ai_prompt && (
        <div className="mb-4 p-3 rounded-lg bg-violet-900/20 border border-violet-800/40 text-sm text-violet-300">
          <span className="font-medium">KI-Prompt:</span> {album.ai_prompt}
          {album.ai_last_evaluated && (
            <span className="text-violet-400 text-xs ml-2">
              · zuletzt: {format(new Date(album.ai_last_evaluated), 'dd.MM.yyyy HH:mm', { locale: de })}
            </span>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">Lade…</div>
      ) : photos.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-zinc-500">
          <FolderOpen size={40} className="mb-3" />
          <p>Noch keine Fotos in diesem Album.</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-1">
          {photos.map(photo => (
            <button key={photo.id} onClick={() => setLightbox(photo)}
              className="aspect-square rounded-md overflow-hidden bg-zinc-800 group">
              <img
                src={thumbUrl(photo, 'small')}
                className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                loading="lazy"
              />
            </button>
          ))}
        </div>
      )}

      {lightbox && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setLightbox(null)}>
          <button className="absolute top-4 right-4 text-white/80 hover:text-white"><X size={28} /></button>
          <img src={`/api/photos/${lightbox.id}/thumbnail?size=large`}
            className="max-h-[90vh] max-w-[95vw] object-contain" onClick={e => e.stopPropagation()} />
        </div>
      )}
    </div>
  )
}

function AlbumEditModal({ album, onClose, onSaved, onDeleted }:
  { album: Album; onClose: () => void; onSaved: () => void; onDeleted: () => void }) {
  const [name, setName] = useState(album.name)
  const [type, setType] = useState<AlbumType>(album.album_type)
  const [aiPrompt, setAiPrompt] = useState(album.ai_prompt || '')
  const [personIds, setPersonIds] = useState<number[]>(((album.smart_criteria?.person_ids as number[]) || []))
  const [mediaType, setMediaType] = useState<string>(((album.smart_criteria?.media_type as string) || 'all'))
  const { data: people = [] } = useQuery<{ id: number; name: string }[]>({ queryKey: ['people-min'], queryFn: () => api.get('/people').then(r => r.data) })
  const named = people.filter(p => (p.name || '').trim())

  const save = useMutation({
    mutationFn: () => {
      const body: any = { name, album_type: type }
      if (type === 'smart') body.smart_criteria = { person_ids: personIds, person_match: 'any', ...(mediaType !== 'all' ? { media_type: mediaType } : {}) }
      if (type === 'ai') body.ai_prompt = aiPrompt
      return api.patch(`/albums/${album.id}`, body)
    },
    onSuccess: onSaved,
  })
  const refresh = useMutation({ mutationFn: () => api.post(`/albums/${album.id}/refresh`), onSuccess: onSaved })
  const del = useMutation({ mutationFn: () => api.delete(`/albums/${album.id}`), onSuccess: onDeleted })
  const sel = 'w-full px-3 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-sm text-zinc-900 dark:text-zinc-100'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-white dark:bg-zinc-900 rounded-2xl p-6 w-full max-w-md border border-zinc-200 dark:border-zinc-800 space-y-3" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-zinc-900 dark:text-white">Album bearbeiten</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>
        <div><label className="block text-xs text-zinc-500 mb-1">Name</label>
          <input value={name} onChange={e => setName(e.target.value)} className={sel} /></div>
        <div><label className="block text-xs text-zinc-500 mb-1">Typ</label>
          <div className="grid grid-cols-3 gap-2">
            {(['manual', 'smart', 'ai'] as AlbumType[]).map(t => (
              <button key={t} onClick={() => setType(t)}
                className={`py-1.5 rounded-lg text-sm ${type === t ? 'bg-indigo-600 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}>{TYPE_LABELS[t]}</button>
            ))}
          </div></div>
        {type === 'smart' && (
          <>
            <div><label className="block text-xs text-zinc-500 mb-1">Personen (alle deren Fotos — ohne Limit)</label>
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto p-1 rounded-lg border border-zinc-200 dark:border-zinc-700">
                {named.map(p => {
                  const on = personIds.includes(p.id)
                  return <button key={p.id} type="button" onClick={() => setPersonIds(s => on ? s.filter(x => x !== p.id) : [...s, p.id])}
                    className={`px-2 py-0.5 rounded-full text-xs ${on ? 'bg-indigo-600 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}>{p.name}</button>
                })}
              </div></div>
            <div><label className="block text-xs text-zinc-500 mb-1">Medientyp</label>
              <select value={mediaType} onChange={e => setMediaType(e.target.value)} className={sel}>
                <option value="all">Alle</option><option value="photo">Nur Fotos</option><option value="video">Nur Videos</option>
              </select></div>
          </>
        )}
        {type === 'ai' && (
          <div><label className="block text-xs text-zinc-500 mb-1">KI-Prompt</label>
            <input value={aiPrompt} onChange={e => setAiPrompt(e.target.value)} className={sel} placeholder="z. B. Sonnenuntergänge am Meer" /></div>
        )}
        <button onClick={() => save.mutate()} disabled={save.isPending}
          className="w-full py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
          {save.isPending ? 'Speichern…' : 'Speichern'}
        </button>
        <div className="flex gap-2">
          {type !== 'manual' && (
            <button onClick={() => refresh.mutate()} disabled={refresh.isPending}
              className="flex-1 py-2 rounded-xl border border-zinc-300 dark:border-zinc-600 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800">
              <RefreshCw size={14} className="inline mr-1" /> Aktualisieren
            </button>
          )}
          <button onClick={() => { if (window.confirm('Album löschen? Die Fotos bleiben erhalten.')) del.mutate() }}
            className="flex-1 py-2 rounded-xl text-sm text-red-500 border border-red-300 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/20">
            <Trash2 size={14} className="inline mr-1" /> Löschen
          </button>
        </div>
        <p className="text-[11px] text-zinc-400">Tipp: Ein Personen-Album als <b>Smart</b> mit der Person speichern → enthält automatisch <b>alle</b> Fotos dieser Person (kein 1000er-Limit) und aktualisiert sich.</p>
      </div>
    </div>
  )
}

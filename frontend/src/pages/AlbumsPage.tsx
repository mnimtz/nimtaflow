import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, FolderOpen, Sparkles, Brain, Trash2, RefreshCw, ChevronRight, X, Share2, Pencil, PawPrint } from 'lucide-react'
import ShareDialog from '../components/ShareDialog'
import GalleryLightbox from '../components/gallery/GalleryLightbox'
import { api, thumbUrl } from '../lib/api'
import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import { useT } from '../i18n'

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
const TYPE_LABEL_KEYS: Record<AlbumType, string> = {
  manual: 'albums.typeManual',
  smart: 'albums.typeSmart',
  ai: 'albums.typeAi',
}
const TYPE_COLORS: Record<AlbumType, string> = {
  manual: 'bg-zinc-800 text-zinc-300',
  smart: 'bg-indigo-900/60 text-indigo-300',
  ai: 'bg-violet-900/60 text-violet-300',
}

export default function AlbumsPage() {
  const { t } = useT()
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

  const petsMutation = useMutation({
    mutationFn: () => api.post('/albums/enable-pets').then(r => r.data),
    onSuccess: (a: any) => { qc.invalidateQueries({ queryKey: ['albums'] }); if (a) setSelectedAlbum(a) },
  })

  if (selectedAlbum) {
    return <AlbumDetail album={selectedAlbum} onBack={() => setSelectedAlbum(null)} />
  }

  return (
    <div className="p-4 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">{t('albums.title')}</h1>
          <p className="text-sm text-zinc-400">{t('albums.count', { n: albums.length })}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => petsMutation.mutate()}
            disabled={petsMutation.isPending}
            title={t('albums.petsHint')}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-700 text-white text-sm font-medium hover:bg-zinc-600 transition-colors disabled:opacity-50"
          >
            <PawPrint size={16} /> {petsMutation.isPending ? t('albums.petsBusy') : t('albums.petsAlbum')}
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            <Plus size={16} /> {t('albums.new')}
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">{t('albums.loading')}</div>
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
  const { t } = useT()
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
          <span className="text-xs text-zinc-500">{t('albums.photos', { n: album.photo_count })}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded ${TYPE_COLORS[album.album_type]}`}>
            {t(TYPE_LABEL_KEYS[album.album_type])}
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
            title={t('albums.refresh')}
            className="p-1 rounded bg-black/60 text-zinc-300 hover:text-white"
          >
            <RefreshCw size={13} />
          </button>
        )}
        <button
          onClick={onDelete}
          title={t('albums.delete')}
          className="p-1 rounded bg-black/60 text-zinc-300 hover:text-red-400"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </div>
  )
}

function EmptyAlbums({ onCreateClick }: { onCreateClick: () => void }) {
  const { t } = useT()
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <FolderOpen size={48} className="text-zinc-700 mb-4" />
      <h3 className="text-lg font-semibold text-white mb-2">{t('albums.emptyTitle')}</h3>
      <p className="text-sm text-zinc-500 max-w-xs mb-6">
        {t('albums.emptyText')}
      </p>
      <button
        onClick={onCreateClick}
        className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700"
      >
        {t('albums.createFirst')}
      </button>
    </div>
  )
}

// ── Create modal ─────────────────────────────────────────────────────────────

function CreateAlbumModal({ onClose }: { onClose: () => void }) {
  const { t } = useT()
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
          <h2 className="text-lg font-bold text-white">{t('albums.new')}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            required
            placeholder={t('albums.namePlaceholder')}
            value={name}
            onChange={e => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />

          {/* Type selector */}
          <div className="grid grid-cols-3 gap-2">
            {(['manual', 'smart', 'ai'] as AlbumType[]).map(ty => {
              const Icon = TYPE_ICONS[ty]
              return (
                <button
                  key={ty}
                  type="button"
                  onClick={() => setType(ty)}
                  className={`flex flex-col items-center gap-1 py-3 rounded-lg border text-xs font-medium transition-all ${
                    type === ty
                      ? 'border-indigo-500 bg-indigo-900/40 text-indigo-300'
                      : 'border-zinc-700 text-zinc-400 hover:border-zinc-500'
                  }`}
                >
                  <Icon size={18} />
                  {t(TYPE_LABEL_KEYS[ty])}
                </button>
              )
            })}
          </div>

          {type === 'ai' && (
            <div>
              <label className="block text-xs text-zinc-400 mb-1">{t('albums.aiPrompt')}</label>
              <textarea
                placeholder={t('albums.aiPromptPlaceholder')}
                value={aiPrompt}
                onChange={e => setAiPrompt(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm placeholder-zinc-500 resize-none focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
              <p className="text-xs text-zinc-500 mt-1">{t('albums.aiPromptHint')}</p>
            </div>
          )}

          {type === 'smart' && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">{t('albums.from')}</label>
                  <input type="date" value={smartDate.from} onChange={e => setSmartDate(d => ({ ...d, from: e.target.value }))}
                    className="w-full px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1">{t('albums.to')}</label>
                  <input type="date" value={smartDate.to} onChange={e => setSmartDate(d => ({ ...d, to: e.target.value }))}
                    className="w-full px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
                </div>
              </div>
              <select value={smartMediaType} onChange={e => setSmartMediaType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="">{t('albums.allMediaTypes')}</option>
                <option value="photo">{t('albums.onlyPhotos')}</option>
                <option value="video">{t('albums.onlyVideos')}</option>
              </select>
              <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                <input type="checkbox" checked={smartFavorites} onChange={e => setSmartFavorites(e.target.checked)}
                  className="rounded accent-indigo-500" />
                {t('albums.onlyFavorites')}
              </label>

              {/* Personen-Filter */}
              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">{t('albums.people')}</label>
                {people.length === 0 ? (
                  <p className="text-xs text-zinc-500">{t('albums.noPeople')}</p>
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
                            {p.name || t('albums.unknown')}
                          </button>
                        )
                      })}
                    </div>
                    {smartPersons.length >= 2 && (
                      <div className="flex gap-1 mt-2 text-xs">
                        <button type="button" onClick={() => setPersonMatch('any')}
                          className={`px-2.5 py-1 rounded-lg border ${personMatch === 'any' ? 'border-indigo-500 bg-indigo-900/40 text-indigo-200' : 'border-zinc-700 text-zinc-400'}`}>
                          {t('albums.matchAny')}
                        </button>
                        <button type="button" onClick={() => setPersonMatch('all')}
                          className={`px-2.5 py-1 rounded-lg border ${personMatch === 'all' ? 'border-indigo-500 bg-indigo-900/40 text-indigo-200' : 'border-zinc-700 text-zinc-400'}`}>
                          {t('albums.matchAll')}
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
              {t('albums.cancel')}
            </button>
            <button type="submit" disabled={create.isPending}
              className="flex-1 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50">
              {create.isPending ? t('albums.creating') : t('albums.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Album detail view ─────────────────────────────────────────────────────────

function AlbumDetail({ album, onBack }: { album: Album; onBack: () => void }) {
  const { t } = useT()
  const qc = useQueryClient()
  const [showShare, setShowShare] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [sort, setSort] = useState('newest')
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
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
          {t('albums.back')}
        </button>
        <div className="flex items-center gap-2">
          <Icon size={18} className="text-zinc-400" />
          <h1 className="text-xl font-bold text-white">{album.name}</h1>
          <span className={`text-xs px-2 py-0.5 rounded ${TYPE_COLORS[album.album_type]}`}>
            {t(TYPE_LABEL_KEYS[album.album_type])}
          </span>
        </div>
        <span className="text-sm text-zinc-500 ml-auto">{t('albums.photos', { n: album.photo_count })}</span>
        <select value={sort} onChange={e => setSort(e.target.value)}
          className="text-sm rounded-lg border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-zinc-700 dark:text-zinc-200 px-2 py-1">
          <option value="newest">{t('albums.sortNewest')}</option>
          <option value="oldest">{t('albums.sortOldest')}</option>
          <option value="order">{t('albums.sortOrder')}</option>
          <option value="name">{t('albums.sortName')}</option>
        </select>
        <button onClick={() => setShowEdit(true)}
          className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white">
          <Pencil size={15} /> {t('albums.edit')}
        </button>
        <button onClick={() => setShowShare(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-400 hover:text-indigo-300">
          <Share2 size={15} /> {t('albums.share')}
        </button>
      </div>
      {showShare && <ShareDialog target={{ kind: 'album', albumId: album.id, title: album.name }} onClose={() => setShowShare(false)} />}
      {showEdit && <AlbumEditModal album={album} onClose={() => setShowEdit(false)}
        onSaved={() => { setShowEdit(false); qc.invalidateQueries({ queryKey: ['albums'] }); qc.invalidateQueries({ queryKey: ['album-photos', album.id] }) }}
        onDeleted={() => { setShowEdit(false); qc.invalidateQueries({ queryKey: ['albums'] }); onBack() }} />}

      {album.ai_prompt && (
        <div className="mb-4 p-3 rounded-lg bg-violet-900/20 border border-violet-800/40 text-sm text-violet-300">
          <span className="font-medium">{t('albums.aiPromptLabel')}</span> {album.ai_prompt}
          {album.ai_last_evaluated && (
            <span className="text-violet-400 text-xs ml-2">
              {t('albums.aiLastEvaluated', { date: format(new Date(album.ai_last_evaluated), 'dd.MM.yyyy HH:mm', { locale: de }) })}
            </span>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-16 text-zinc-500">{t('albums.loading')}</div>
      ) : photos.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-zinc-500">
          <FolderOpen size={40} className="mb-3" />
          <p>{t('albums.emptyPhotos')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-1">
          {photos.map((photo, i) => (
            <button key={photo.id} onClick={() => setLightboxIndex(i)}
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

      {/* Einheitliche Lightbox (Details, Postkarte, KI, Teilen …) statt reinem Bild */}
      {lightboxIndex !== null && (
        <GalleryLightbox photos={photos as any} index={lightboxIndex} onClose={() => setLightboxIndex(null)} />
      )}
    </div>
  )
}

function AlbumEditModal({ album, onClose, onSaved, onDeleted }:
  { album: Album; onClose: () => void; onSaved: () => void; onDeleted: () => void }) {
  const { t } = useT()
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
          <h2 className="text-lg font-bold text-zinc-900 dark:text-white">{t('albums.editTitle')}</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300"><X size={18} /></button>
        </div>
        <div><label className="block text-xs text-zinc-500 mb-1">{t('albums.name')}</label>
          <input value={name} onChange={e => setName(e.target.value)} className={sel} /></div>
        <div><label className="block text-xs text-zinc-500 mb-1">{t('albums.type')}</label>
          <div className="grid grid-cols-3 gap-2">
            {(['manual', 'smart', 'ai'] as AlbumType[]).map(ty => (
              <button key={ty} onClick={() => setType(ty)}
                className={`py-1.5 rounded-lg text-sm ${type === ty ? 'bg-indigo-600 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}>{t(TYPE_LABEL_KEYS[ty])}</button>
            ))}
          </div></div>
        {type === 'smart' && (
          <>
            <div><label className="block text-xs text-zinc-500 mb-1">{t('albums.peopleAll')}</label>
              <div className="flex flex-wrap gap-1.5 max-h-28 overflow-y-auto p-1 rounded-lg border border-zinc-200 dark:border-zinc-700">
                {named.map(p => {
                  const on = personIds.includes(p.id)
                  return <button key={p.id} type="button" onClick={() => setPersonIds(s => on ? s.filter(x => x !== p.id) : [...s, p.id])}
                    className={`px-2 py-0.5 rounded-full text-xs ${on ? 'bg-indigo-600 text-white' : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300'}`}>{p.name}</button>
                })}
              </div></div>
            <div><label className="block text-xs text-zinc-500 mb-1">{t('albums.mediaType')}</label>
              <select value={mediaType} onChange={e => setMediaType(e.target.value)} className={sel}>
                <option value="all">{t('albums.all')}</option><option value="photo">{t('albums.onlyPhotos')}</option><option value="video">{t('albums.onlyVideos')}</option>
              </select></div>
          </>
        )}
        {type === 'ai' && (
          <div><label className="block text-xs text-zinc-500 mb-1">{t('albums.aiPrompt')}</label>
            <input value={aiPrompt} onChange={e => setAiPrompt(e.target.value)} className={sel} placeholder={t('albums.aiPromptEditPlaceholder')} /></div>
        )}
        <button onClick={() => save.mutate()} disabled={save.isPending}
          className="w-full py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
          {save.isPending ? t('albums.saving') : t('albums.save')}
        </button>
        <div className="flex gap-2">
          {type !== 'manual' && (
            <button onClick={() => refresh.mutate()} disabled={refresh.isPending}
              className="flex-1 py-2 rounded-xl border border-zinc-300 dark:border-zinc-600 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800">
              <RefreshCw size={14} className="inline mr-1" /> {t('albums.refresh')}
            </button>
          )}
          <button onClick={() => { if (window.confirm(t('albums.confirmDelete'))) del.mutate() }}
            className="flex-1 py-2 rounded-xl text-sm text-red-500 border border-red-300 dark:border-red-800 hover:bg-red-50 dark:hover:bg-red-900/20">
            <Trash2 size={14} className="inline mr-1" /> {t('albums.delete')}
          </button>
        </div>
        <p className="text-[11px] text-zinc-400">{t('albums.tip')}</p>
      </div>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Camera, Trash2, User as UserIcon, ArrowLeft, FolderPlus, RefreshCw, FolderOpen } from 'lucide-react'
import { api } from '../lib/api'
import { useT } from '../i18n'

type Profile = {
  id: number; email: string; name: string; role: string
  birthdate: string | null; avatar_path: string | null
}

const inp = 'w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-white text-sm'
const lbl = 'block text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1'

export default function ProfilePage() {
  const { t } = useT()
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data: me } = useQuery<Profile>({ queryKey: ['profile'], queryFn: () => api.get('/users/me').then(r => r.data) })

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [birthdate, setBirthdate] = useState('')
  const [cur, setCur] = useState('')
  const [npw, setNpw] = useState('')
  const [npw2, setNpw2] = useState('')
  const [msg, setMsg] = useState<{ k: 'ok' | 'err'; t: string } | null>(null)
  const [avatarV, setAvatarV] = useState(0)  // cache-bust after upload
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (me) { setName(me.name); setEmail(me.email); setBirthdate(me.birthdate || '') }
  }, [me])

  const flash = (k: 'ok' | 'err', t: string) => { setMsg({ k, t }); setTimeout(() => setMsg(null), 4000) }
  const refresh = () => { qc.invalidateQueries({ queryKey: ['profile'] }); qc.invalidateQueries({ queryKey: ['me'] }) }

  const saveProfile = useMutation({
    mutationFn: () => api.patch('/users/me', { name, email, birthdate: birthdate || null }),
    onSuccess: () => { refresh(); flash('ok', t('profile.saved')) },
    onError: (e: any) => flash('err', e?.response?.data?.detail || t('profile.saveFailed')),
  })

  const changePw = useMutation({
    mutationFn: () => api.post('/users/me/password', { current_password: cur, new_password: npw }),
    onSuccess: () => { setCur(''); setNpw(''); setNpw2(''); flash('ok', t('profile.pwChanged')) },
    onError: (e: any) => flash('err', e?.response?.data?.detail || t('profile.pwChangeFailed')),
  })

  const uploadAvatar = useMutation({
    mutationFn: (f: File) => { const fd = new FormData(); fd.append('file', f); return api.post('/users/me/avatar', fd) },
    onSuccess: () => { setAvatarV(v => v + 1); refresh(); flash('ok', t('profile.avatarUpdated')) },
    onError: () => flash('err', t('profile.avatarUploadFailed')),
  })

  const removeAvatar = useMutation({
    mutationFn: () => api.delete('/users/me/avatar'),
    onSuccess: () => { setAvatarV(v => v + 1); refresh(); flash('ok', t('profile.avatarRemoved')) },
  })

  if (!me) return <div className="p-6 text-zinc-500">{t('profile.loading')}</div>

  const hasAvatar = !!me.avatar_path
  const avatarUrl = `/api/users/${me.id}/avatar?v=${avatarV}`
  const initial = (me.name || me.email || '?').charAt(0).toUpperCase()

  return (
    <div className="p-4 md:p-6 max-w-2xl mx-auto pb-24">
      <button onClick={() => nav(-1)} className="flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200 mb-4">
        <ArrowLeft size={16} /> {t('profile.back')}
      </button>
      <h1 className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-white mb-6 flex items-center gap-2">
        <UserIcon size={22} /> {t('profile.title')}
      </h1>

      {msg && (
        <div className={`mb-4 text-sm px-3 py-2 rounded-lg ${msg.k === 'ok' ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : 'bg-red-500/15 text-red-600 dark:text-red-400'}`}>{msg.t}</div>
      )}

      {/* Avatar */}
      <div className="flex items-center gap-4 mb-8">
        <div className="w-20 h-20 rounded-full overflow-hidden bg-indigo-600 flex items-center justify-center text-white text-2xl font-semibold shrink-0">
          {hasAvatar ? <img key={avatarV} src={avatarUrl} alt="" className="w-full h-full object-cover" /> : initial}
        </div>
        <div className="flex flex-col gap-2">
          <input ref={fileRef} type="file" accept="image/*" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) uploadAvatar.mutate(f); e.target.value = '' }} />
          <button onClick={() => fileRef.current?.click()} disabled={uploadAvatar.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-500 disabled:opacity-50">
            <Camera size={15} /> {uploadAvatar.isPending ? t('profile.uploading') : t('profile.chooseAvatar')}
          </button>
          {hasAvatar && (
            <button onClick={() => removeAvatar.mutate()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-red-500 hover:bg-red-500/10">
              <Trash2 size={14} /> {t('profile.remove')}
            </button>
          )}
        </div>
      </div>

      {/* Stammdaten */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-800 p-4 md:p-5 mb-6 space-y-4">
        <h2 className="font-semibold text-zinc-900 dark:text-white">{t('profile.dataSection')}</h2>
        <div>
          <label className={lbl}>{t('profile.displayName')}</label>
          <input className={inp} value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <label className={lbl}>{t('profile.emailLogin')}</label>
          <input className={inp} type="email" value={email} onChange={e => setEmail(e.target.value)} />
          <p className="text-[11px] text-amber-600 dark:text-amber-400 mt-1">{t('profile.emailHint')}</p>
        </div>
        <div>
          <label className={lbl}>{t('profile.birthdate')}</label>
          <input className={inp} type="date" value={birthdate} onChange={e => setBirthdate(e.target.value)} />
        </div>
        <button onClick={() => saveProfile.mutate()} disabled={saveProfile.isPending}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {saveProfile.isPending ? t('profile.saving') : t('profile.save')}
        </button>
      </section>

      {/* Passwort */}
      <section className="rounded-2xl border border-zinc-200 dark:border-zinc-800 p-4 md:p-5 space-y-4">
        <h2 className="font-semibold text-zinc-900 dark:text-white">{t('profile.changePassword')}</h2>
        <div>
          <label className={lbl}>{t('profile.currentPassword')}</label>
          <input className={inp} type="password" value={cur} onChange={e => setCur(e.target.value)} autoComplete="current-password" />
        </div>
        <div>
          <label className={lbl}>{t('profile.newPassword')}</label>
          <input className={inp} type="password" value={npw} onChange={e => setNpw(e.target.value)} autoComplete="new-password" />
        </div>
        <div>
          <label className={lbl}>{t('profile.repeatNewPassword')}</label>
          <input className={inp} type="password" value={npw2} onChange={e => setNpw2(e.target.value)} autoComplete="new-password" />
        </div>
        <button
          onClick={() => { if (npw !== npw2) { flash('err', t('profile.newPwMismatch')); return } changePw.mutate() }}
          disabled={changePw.isPending || !cur || npw.length < 6}
          className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50">
          {changePw.isPending ? t('profile.changing') : t('profile.changePassword')}
        </button>
      </section>

      {/* Meine Quellen (Upload-Phase 3) — rendert nur, wenn freigeschaltet */}
      <MySources />
    </div>
  )
}

type MySource = { id: number; path: string; name: string | null; last_scan_count: number | null }

function MySources() {
  const { t } = useT()
  const qc = useQueryClient()
  const [path, setPath] = useState('')
  const [err, setErr] = useState<string | null>(null)
  // Self-gating: a 403 (feature not enabled for this account) hides the whole section.
  const { data: sources, isError } = useQuery<MySource[]>({
    queryKey: ['my-sources'], queryFn: () => api.get('/my-sources').then(r => r.data), retry: false,
  })
  const { data: roots } = useQuery<{ roots: string[] }>({
    queryKey: ['my-sources-roots'], queryFn: () => api.get('/my-sources/allowed-roots').then(r => r.data),
    retry: false, enabled: !isError,
  })
  const add = useMutation({
    mutationFn: () => api.post('/my-sources', { path: path.trim() }),
    onSuccess: () => { setPath(''); setErr(null); qc.invalidateQueries({ queryKey: ['my-sources'] }) },
    onError: (e: any) => setErr(e?.response?.data?.detail || t('profile.sourceFailed')),
  })
  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/my-sources/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-sources'] }),
  })
  const scan = useMutation({ mutationFn: (id: number) => api.post(`/my-sources/${id}/scan`) })

  if (isError) return null  // feature not enabled for this account
  const base = roots?.roots?.[0] || ''

  return (
    <section className="rounded-2xl border border-zinc-200 dark:border-zinc-800 p-4 md:p-5 mt-6 space-y-4">
      <h2 className="font-semibold text-zinc-900 dark:text-white flex items-center gap-2"><FolderOpen size={18} /> {t('profile.sourcesSection')}</h2>
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{t('profile.sourcesIntro')}</p>
      {roots?.roots?.length ? (
        <p className="text-[11px] text-zinc-500 dark:text-zinc-400">
          {t('profile.sourceAllowed')}: <code className="text-zinc-700 dark:text-zinc-300">{roots.roots.join(', ')}</code>
        </p>
      ) : null}

      <div className="flex gap-2 flex-wrap">
        <input className={inp + ' flex-1 min-w-[180px] font-mono text-xs'} value={path}
          onChange={e => setPath(e.target.value)} placeholder={base ? `${base}/…` : t('profile.sourcePath')} />
        <button onClick={() => add.mutate()} disabled={add.isPending || !path.trim()}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-50 shrink-0">
          <FolderPlus size={15} /> {t('profile.sourceAdd')}
        </button>
      </div>
      {err && <p className="text-xs text-red-500">{err}</p>}

      {sources && sources.length > 0 ? (
        <ul className="space-y-2">
          {sources.map(s => (
            <li key={s.id} className="flex items-center gap-2 text-sm border-t border-zinc-100 dark:border-zinc-800 pt-2">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-zinc-800 dark:text-zinc-200 truncate">{s.name || s.path}</p>
                <p className="text-[11px] text-zinc-500 font-mono truncate">{s.path}{s.last_scan_count != null ? ` · ${s.last_scan_count}` : ''}</p>
              </div>
              <button onClick={() => scan.mutate(s.id)} title={t('profile.sourceScan')}
                className="text-zinc-500 hover:text-indigo-500 shrink-0"><RefreshCw size={15} /></button>
              <button onClick={() => del.mutate(s.id)} title={t('profile.sourceDelete')}
                className="text-zinc-500 hover:text-red-500 shrink-0"><Trash2 size={15} /></button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-zinc-400">{t('profile.sourcesEmpty')}</p>
      )}
    </section>
  )
}

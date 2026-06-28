import { useState, useEffect, useMemo, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Check, SkipForward, UserX, Loader2 } from 'lucide-react'
import { api } from '../../lib/api'
import { useToast } from '../ui/dialogs'
import { useT } from '../../i18n'

type P = { id: number; name: string; face_count: number; photo_count: number }

export default function QuickNameOverlay({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { t } = useT()
  const inputRef = useRef<HTMLInputElement>(null)
  const { data: people = [], isLoading } = useQuery<P[]>({
    queryKey: ['people-quickname'],
    queryFn: () => api.get('/people', { params: { sort: 'faces' } }).then(r => r.data),
    staleTime: 0,
  })
  // biggest unnamed clusters first — most worth naming
  const queue = useMemo(() => people.filter(p => !(p.name || '').trim()).sort((a, b) => b.face_count - a.face_count), [people])
  const [i, setI] = useState(0)
  const [name, setName] = useState('')
  const [named, setNamed] = useState(0)
  const cur = queue[i]

  const { data: facesData } = useQuery<{ items: { id: number; photo_id: number }[] }>({
    queryKey: ['qn-faces', cur?.id],
    queryFn: () => api.get(`/people/${cur!.id}/faces`, { params: { limit: 8 } }).then(r => r.data),
    enabled: !!cur,
  })

  const advance = () => { setName(''); setI(x => x + 1); setTimeout(() => inputRef.current?.focus(), 50) }
  const nameM = useMutation({
    mutationFn: () => api.patch(`/people/${cur!.id}`, { name: name.trim() }),
    onSuccess: () => { setNamed(n => n + 1); qc.invalidateQueries({ queryKey: ['people'] }); advance() },
    onError: () => toast(t('people.qnToastSaveFailed'), 'error'),
  })
  const dissolveM = useMutation({
    mutationFn: () => api.delete(`/people/${cur!.id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['people'] }); advance() },
    onError: () => toast(t('people.qnToastDissolveFailed'), 'error'),
  })

  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 80) }, [])

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { e.preventDefault(); if (name.trim() && !nameM.isPending) nameM.mutate() }
    else if (e.key === 'Tab') { e.preventDefault(); advance() }   // skip
  }

  return (
    <div className="fixed inset-0 z-[120] bg-zinc-950/95 backdrop-blur-sm flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
        <div className="text-white font-semibold">{t('people.qnTitle')}</div>
        <div className="text-sm text-zinc-400">{t('people.qnProgress', { named, left: Math.max(0, queue.length - i) })}</div>
        <button onClick={onClose} className="text-zinc-400 hover:text-white"><X size={20} /></button>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center p-6 overflow-auto">
        {isLoading ? (
          <Loader2 className="animate-spin text-zinc-500" />
        ) : !cur ? (
          <div className="text-center text-zinc-300">
            <Check size={40} className="mx-auto mb-3 text-green-400" />
            <p className="text-lg font-semibold">{t('people.qnDone')}</p>
            <p className="text-sm text-zinc-500 mt-1">{t('people.qnDoneCount', { count: named })}</p>
            <button onClick={onClose} className="mt-4 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm">{t('people.qnClose')}</button>
          </div>
        ) : (
          <div className="w-full max-w-md flex flex-col items-center">
            <div className="w-40 h-40 rounded-full overflow-hidden bg-zinc-800 ring-2 ring-white/10 mb-3">
              <img src={`/api/people/${cur.id}/avatar?v=${cur.id}`} className="w-full h-full object-cover" onError={e => { (e.target as HTMLImageElement).style.opacity = '0.2' }} />
            </div>
            <div className="text-zinc-400 text-sm mb-3">{t('people.qnFacesPhotos', { faces: cur.face_count, photos: cur.photo_count })}</div>

            {facesData && facesData.items.length > 1 && (
              <div className="flex gap-1.5 mb-4 flex-wrap justify-center">
                {facesData.items.slice(0, 8).map(f => (
                  <img key={f.id} src={`/api/people/faces/${f.id}/crop`} loading="lazy"
                    className="w-12 h-12 rounded-lg object-cover bg-zinc-800" onError={e => { (e.target as HTMLImageElement).style.opacity = '0.2' }} />
                ))}
              </div>
            )}

            <input ref={inputRef} value={name} onChange={e => setName(e.target.value)} onKeyDown={onKey}
              placeholder={t('people.qnInputPlaceholder')}
              className="w-full px-4 py-2.5 rounded-xl bg-zinc-800 border border-zinc-700 text-white text-center text-lg focus:outline-none focus:ring-2 focus:ring-indigo-500" />

            <div className="flex items-center gap-2 mt-4">
              <button onClick={() => name.trim() && nameM.mutate()} disabled={!name.trim() || nameM.isPending}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
                {nameM.isPending ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} {t('people.qnNameBtn')}
              </button>
              <button onClick={advance} className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-zinc-700 text-white text-sm hover:bg-zinc-600">
                <SkipForward size={15} /> {t('people.qnSkip')}
              </button>
              <button onClick={() => dissolveM.mutate()} disabled={dissolveM.isPending} title={t('people.qnDissolveTitle')}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-red-300 hover:bg-red-900/30 text-sm">
                <UserX size={15} /> {t('people.qnDissolve')}
              </button>
            </div>
            <p className="text-[11px] text-zinc-600 mt-3">{t('people.qnHint')}</p>
          </div>
        )}
      </div>
    </div>
  )
}

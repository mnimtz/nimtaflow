import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { Images, Sparkles, Users, BookImage, Video, MapPin, Clock, Star, X } from 'lucide-react'

type Ph = { id: number; thumb_url: string; thumb_medium_url: string; is_video: boolean }
type Person = { id: number; name: string; face_count: number; avatar_url: string; items?: Ph[] }
type Album = { id: number; name: string; photo_count: number; cover_url: string | null }
type Memory = { years_ago: number; date: string; items: Ph[] }
type Dash = {
  stats: any
  on_this_day: Memory[]
  person_of_week: Person | null
  featured_people: Person[]
  featured_albums: Album[]
  recent: Ph[]
  highlights: Ph[]
}

export default function DashboardPage() {
  const nav = useNavigate()
  const [lightbox, setLightbox] = useState<Ph | null>(null)
  const { data, isLoading } = useQuery<Dash>({
    queryKey: ['dashboard'],
    queryFn: () => api.get('/v1/dashboard').then(r => r.data),
    staleTime: 60_000,
  })

  if (isLoading) return <div className="flex justify-center py-24 text-zinc-500">Lade Startseite…</div>
  if (!data) return null

  const greeting = (() => {
    const h = new Date().getHours()
    return h < 5 ? 'Gute Nacht' : h < 11 ? 'Guten Morgen' : h < 17 ? 'Hallo' : h < 22 ? 'Guten Abend' : 'Gute Nacht'
  })()

  const Tile = ({ p }: { p: Ph }) => (
    <button onClick={() => setLightbox(p)}
      className="relative shrink-0 w-32 h-32 rounded-xl overflow-hidden bg-zinc-200 dark:bg-zinc-800 group">
      <img src={p.thumb_medium_url} loading="lazy" className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
      {p.is_video && <Video size={14} className="absolute bottom-1 left-1 text-white drop-shadow" />}
    </button>
  )

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-9">
      <div>
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">{greeting} 👋</h1>
        {data.stats && (
          <p className="text-sm text-zinc-500 mt-1">
            {data.stats.total?.toLocaleString('de')} Medien · {data.stats.images?.toLocaleString('de')} Bilder · {data.stats.videos?.toLocaleString('de')} Videos
            {data.stats.date_min && ` · seit ${String(data.stats.date_min).slice(0, 4)}`}
          </p>
        )}
      </div>

      {/* Quick stat tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatTile icon={Images} label="Galerie" value={data.stats?.total} color="indigo" onClick={() => nav('/gallery')} />
        <StatTile icon={Users} label="Personen" value={data.stats?.with_faces} sub="mit Gesichtern" color="pink" onClick={() => nav('/people')} />
        <StatTile icon={Sparkles} label="Beschrieben" value={data.stats?.described} color="violet" onClick={() => nav('/search')} />
        <StatTile icon={MapPin} label="Mit GPS" value={data.stats?.with_gps} color="emerald" onClick={() => nav('/map')} />
      </div>

      {/* On this day */}
      {data.on_this_day?.length > 0 && data.on_this_day.map(m => (
        <Section key={m.years_ago} icon={Clock} title={m.years_ago === 1 ? 'Heute vor 1 Jahr' : `Heute vor ${m.years_ago} Jahren`}
          sub={prettyDate(m.date)}>
          <Strip>{m.items.map(p => <Tile key={p.id} p={p} />)}</Strip>
        </Section>
      ))}

      {/* Person of the week */}
      {data.person_of_week && (
        <Section icon={Star} title="Person der Woche">
          <div className="flex flex-col sm:flex-row gap-4 items-start">
            <button onClick={() => nav('/people')} className="flex flex-col items-center shrink-0 group">
              <img src={data.person_of_week.avatar_url} className="w-24 h-24 rounded-full object-cover ring-2 ring-indigo-400 group-hover:ring-indigo-500" />
              <span className="mt-2 font-medium text-zinc-900 dark:text-white">{data.person_of_week.name}</span>
              <span className="text-xs text-zinc-500">{data.person_of_week.face_count} Fotos</span>
            </button>
            <Strip>{(data.person_of_week.items ?? []).map(p => <Tile key={p.id} p={p} />)}</Strip>
          </div>
        </Section>
      )}

      {/* Highlights */}
      {data.highlights?.length > 0 && (
        <Section icon={Sparkles} title="Highlights" sub="zufällige Lieblingsmomente">
          <Strip>{data.highlights.map(p => <Tile key={p.id} p={p} />)}</Strip>
        </Section>
      )}

      {/* Featured people */}
      {data.featured_people?.length > 0 && (
        <Section icon={Users} title="Personen" onMore={() => nav('/people')}>
          <Strip>
            {data.featured_people.map(p => (
              <button key={p.id} onClick={() => nav('/people')} className="flex flex-col items-center shrink-0 w-20 group">
                <img src={p.avatar_url} className="w-16 h-16 rounded-full object-cover ring-1 ring-zinc-300 dark:ring-zinc-700 group-hover:ring-indigo-500" />
                <span className="mt-1 text-xs text-zinc-700 dark:text-zinc-300 truncate w-full text-center">{p.name}</span>
              </button>
            ))}
          </Strip>
        </Section>
      )}

      {/* Featured albums */}
      {data.featured_albums?.length > 0 && (
        <Section icon={BookImage} title="Alben" onMore={() => nav('/albums')}>
          <Strip>
            {data.featured_albums.map(a => (
              <button key={a.id} onClick={() => nav('/albums')} className="shrink-0 w-40 group text-left">
                <div className="w-40 h-28 rounded-xl overflow-hidden bg-zinc-200 dark:bg-zinc-800">
                  {a.cover_url && <img src={a.cover_url} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />}
                </div>
                <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-white truncate">{a.name}</p>
                <p className="text-xs text-zinc-500">{a.photo_count} Fotos</p>
              </button>
            ))}
          </Strip>
        </Section>
      )}

      {/* Recent */}
      {data.recent?.length > 0 && (
        <Section icon={Clock} title="Zuletzt hinzugefügt" onMore={() => nav('/gallery')}>
          <Strip>{data.recent.map(p => <Tile key={p.id} p={p} />)}</Strip>
        </Section>
      )}

      {/* Lightbox */}
      {lightbox && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center" onClick={() => setLightbox(null)}>
          <button className="absolute top-4 right-4 text-white/80 hover:text-white"><X size={28} /></button>
          {lightbox.is_video
            ? <video src={`/api/v1/photos/${lightbox.id}/stream?access_token=${localStorage.getItem('access_token')}`} controls autoPlay className="max-h-[90vh] max-w-[95vw]" onClick={e => e.stopPropagation()} />
            : <img src={`/api/photos/${lightbox.id}/thumbnail?size=large`} className="max-h-[90vh] max-w-[95vw] object-contain" onClick={e => e.stopPropagation()} />}
        </div>
      )}
    </div>
  )
}

function Section({ icon: Icon, title, sub, onMore, children }: any) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <Icon size={18} className="text-indigo-500" />
        <h2 className="text-lg font-semibold text-zinc-900 dark:text-white">{title}</h2>
        {sub && <span className="text-sm text-zinc-400">· {sub}</span>}
        {onMore && <button onClick={onMore} className="ml-auto text-sm text-indigo-500 hover:text-indigo-400">Alle →</button>}
      </div>
      {children}
    </section>
  )
}

function Strip({ children }: any) {
  return <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">{children}</div>
}

function StatTile({ icon: Icon, label, value, sub, color, onClick }: any) {
  const colors: any = {
    indigo: 'text-indigo-500 bg-indigo-500/10', pink: 'text-pink-500 bg-pink-500/10',
    violet: 'text-violet-500 bg-violet-500/10', emerald: 'text-emerald-500 bg-emerald-500/10',
  }
  return (
    <button onClick={onClick} className="text-left p-4 rounded-2xl bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700 hover:border-indigo-400 transition-colors">
      <div className={`w-9 h-9 rounded-xl flex items-center justify-center mb-2 ${colors[color]}`}><Icon size={18} /></div>
      <div className="text-xl font-bold text-zinc-900 dark:text-white">{(value ?? 0).toLocaleString('de')}</div>
      <div className="text-xs text-zinc-500">{label}{sub ? ` · ${sub}` : ''}</div>
    </button>
  )
}

function prettyDate(d: string) {
  try { return new Date(d).toLocaleDateString('de', { day: 'numeric', month: 'long' }) } catch { return d }
}

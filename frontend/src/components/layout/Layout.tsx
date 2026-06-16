import { Outlet, NavLink } from 'react-router-dom'
import { Images, Users, Map, Activity, Settings, Sun, Moon, BookImage, Sparkles, LogOut, LogIn, Network, UserCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useTheme } from '../../store/theme'
import { api } from '../../lib/api'
import clsx from 'clsx'

function UserBadge() {
  const hasToken = !!localStorage.getItem('access_token')
  const { data: me } = useQuery<{ id: number; name: string; role: string; avatar_path: string | null }>({
    queryKey: ['me'],
    queryFn: () => api.get('/auth/me').then(r => r.data),
    enabled: hasToken,
    retry: false,
    staleTime: 300_000,
  })
  const logout = () => {
    localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token')
    document.cookie = 'pf_token=; path=/; max-age=0'
    window.location.href = '/login'
  }
  if (!me) {
    return (
      <a href="/login" className="nav-pill w-full text-left">
        <LogIn size={18} className="shrink-0" /><span className="hidden md:block">Anmelden</span>
      </a>
    )
  }
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5">
      <NavLink to="/profile" title="Mein Profil" className="flex items-center gap-2 min-w-0 flex-1 group">
        <div className="w-7 h-7 rounded-full bg-indigo-600 overflow-hidden flex items-center justify-center text-white text-xs font-semibold shrink-0">
          {me.avatar_path
            ? <img src={`/api/users/${me.id}/avatar`} alt="" className="w-full h-full object-cover" />
            : me.name.charAt(0).toUpperCase()}
        </div>
        <div className="hidden md:block min-w-0 flex-1">
          <p className="text-xs font-medium text-zinc-200 truncate leading-tight group-hover:text-white">{me.name}</p>
          <p className="text-[10px] text-zinc-500 leading-tight">{me.role === 'admin' ? 'Administrator' : 'Benutzer'} · Profil</p>
        </div>
      </NavLink>
      <button onClick={logout} title="Abmelden" className="text-zinc-500 hover:text-red-400 shrink-0">
        <LogOut size={15} />
      </button>
    </div>
  )
}

function VersionBadge() {
  const { data } = useQuery<{ version: string }>({
    queryKey: ['version'],
    queryFn: () => api.get('/version').then(r => r.data),
    staleTime: 300_000,
  })
  return (
    <div className="px-3 pt-2 mt-1 border-t border-white/5" title="Laufende Docker-Version">
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-zinc-400">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
        <span className="hidden md:inline">PhotoFlow&nbsp;</span>v{data?.version ?? '…'}
      </span>
    </div>
  )
}

const nav = [
  { to: '/gallery', icon: Images, label: 'Galerie' },
  { to: '/search', icon: Sparkles, label: 'Suche' },
  { to: '/albums', icon: BookImage, label: 'Alben' },
  { to: '/people', icon: Users, label: 'Personen' },
  { to: '/map', icon: Map, label: 'Karte' },
  { to: '/pipeline', icon: Activity, label: 'Pipeline' },
]

type Me = { role: string; access_config?: Record<string, any> | null }

export default function Layout() {
  const { dark, toggle } = useTheme()
  const hasToken = !!localStorage.getItem('access_token')
  const { data: me } = useQuery<Me>({
    queryKey: ['me'], queryFn: () => api.get('/auth/me').then(r => r.data),
    enabled: hasToken, retry: false, staleTime: 300_000,
  })
  const { data: settings } = useQuery<Record<string, string>>({
    queryKey: ['settings'], queryFn: () => api.get('/settings').then(r => r.data), staleTime: 60_000,
  })
  const relationsOn = (settings?.['features.relationships'] ?? 'false') === 'true'
  // Gate nav by per-user access_config (admins + unauthenticated see everything).
  const allow = (flag: string) =>
    !me || me.role === 'admin' || (me.access_config?.[flag] ?? true)
  const fullNav = relationsOn
    ? [...nav.slice(0, 4), { to: '/relationships', icon: Network, label: 'Beziehungen' }, ...nav.slice(4)]
    : nav
  const visibleNav = fullNav.filter(n =>
    (n.to !== '/map' || allow('allow_map')) &&
    (n.to !== '/pipeline' || (me ? me.role === 'admin' || me.access_config?.allow_pipeline : true)),
  )

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-100 dark:bg-zinc-950">
      {/* ── Sidebar ──────────────────────────────── */}
      <aside className="hidden md:flex w-[220px] flex-col bg-gradient-to-b from-zinc-900 to-zinc-950 border-r border-white/5 shrink-0 select-none">
        {/* Logo */}
        <div className="h-20 flex items-center justify-center px-2 border-b border-white/5">
          <img src="/photoflow-logo.png" alt="PhotoFlow" className="w-full max-h-16 object-contain" />
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 px-2 flex flex-col gap-0.5 overflow-y-auto">
          {visibleNav.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to}>
              {({ isActive }) => (
                <div className={clsx(
                  'nav-pill',
                  isActive && 'active',
                )}>
                  <Icon size={18} className="shrink-0" />
                  <span className="hidden md:block">{label}</span>
                </div>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Bottom actions */}
        <div className="px-2 pb-3 space-y-0.5 border-t border-white/5 pt-3">
          <NavLink to="/settings">
            {({ isActive }) => (
              <div className={clsx('nav-pill', isActive && 'active')}>
                <Settings size={18} className="shrink-0" />
                <span className="hidden md:block">Einstellungen</span>
              </div>
            )}
          </NavLink>
          <button
            onClick={toggle}
            className="nav-pill w-full text-left"
          >
            {dark
              ? <Sun size={18} className="shrink-0" />
              : <Moon size={18} className="shrink-0" />
            }
            <span className="hidden md:block">{dark ? 'Helles Design' : 'Dunkles Design'}</span>
          </button>
          <UserBadge />
          <VersionBadge />
        </div>
      </aside>

      {/* ── Main ─────────────────────────────────── */}
      <main className="flex-1 overflow-auto bg-white dark:bg-zinc-950 min-w-0">
        <Outlet />
      </main>

      {/* ── Mobile bottom nav ─────────────────────── */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-zinc-900 border-t border-white/5 flex">
        {[...visibleNav, { to: '/profile', icon: UserCircle, label: 'Profil' }, { to: '/settings', icon: Settings, label: 'Einstellungen' }].map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to} className="flex-1">
            {({ isActive }) => (
              <div className={clsx(
                'flex flex-col items-center gap-1 py-2 text-[10px] font-medium transition-colors',
                isActive ? 'text-indigo-400' : 'text-zinc-500',
              )}>
                <Icon size={20} />
                {label}
              </div>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

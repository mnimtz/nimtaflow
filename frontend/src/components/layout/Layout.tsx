import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useState } from 'react'
import ErrorBoundary from '../ErrorBoundary'
import { Images, Users, Map, Activity, Gauge, Settings, Sun, Moon, BookImage, Sparkles, MessageCircle, LogOut, LogIn, Network, UserCircle, Plane, Home , Clapperboard, Menu, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useTheme } from '../../store/theme'
import { api, getToken, clearTokens } from '../../lib/api'
import { useT } from '../../i18n'
import LanguageSwitcher from '../LanguageSwitcher'
import clsx from 'clsx'

function UserBadge() {
  const { t } = useT()
  const hasToken = !!getToken()
  const { data: me } = useQuery<{ id: number; name: string; role: string; avatar_path: string | null }>({
    queryKey: ['me'],
    queryFn: () => api.get('/auth/me').then(r => r.data),
    enabled: hasToken,
    retry: false,
    staleTime: 300_000,
  })
  const logout = () => {
    clearTokens()
    window.location.href = '/login'
  }
  if (!me) {
    return (
      <a href="/login" className="nav-pill w-full text-left">
        <LogIn size={18} className="shrink-0" /><span className="hidden md:block">{t('nav.login')}</span>
      </a>
    )
  }
  return (
    <div className="flex items-center gap-2 px-2.5 py-1.5">
      <NavLink to="/profile" title={t('nav.myProfile')} className="flex items-center gap-2 min-w-0 flex-1 group">
        <div className="w-7 h-7 rounded-full bg-indigo-600 overflow-hidden flex items-center justify-center text-white text-xs font-semibold shrink-0">
          {me.avatar_path
            ? <img src={`/api/users/${me.id}/avatar`} alt="" className="w-full h-full object-cover" />
            : me.name.charAt(0).toUpperCase()}
        </div>
        <div className="hidden md:block min-w-0 flex-1">
          <p className="text-xs font-medium text-zinc-200 truncate leading-tight group-hover:text-white">{me.name}</p>
          <p className="text-[10px] text-zinc-500 leading-tight">{me.role === 'admin' ? t('nav.admin') : t('nav.user')} · {t('nav.profile')}</p>
        </div>
      </NavLink>
      <button onClick={logout} title={t('nav.logout')} className="text-zinc-500 hover:text-red-400 shrink-0">
        <LogOut size={15} />
      </button>
    </div>
  )
}

function VersionBadge() {
  const { t } = useT()
  const { data } = useQuery<{ version: string }>({
    queryKey: ['version'],
    queryFn: () => api.get('/version').then(r => r.data),
    staleTime: 300_000,
  })
  return (
    <div className="px-3 pt-2 mt-1 border-t border-white/5" title={t('nav.runningVersion')}>
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-zinc-400">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" />
        <span className="hidden md:inline">NimtaFlow&nbsp;</span>v{data?.version ?? '…'}
      </span>
      {/* AGPL §13: a network-accessible instance must offer its source to users. */}
      <a href="https://github.com/mnimtz/nimtaflow" target="_blank" rel="noopener"
         className="hidden md:block text-[10px] text-zinc-500 hover:text-zinc-300 mt-0.5">
        {t('nav.source')}
      </a>
    </div>
  )
}

const nav = [
  { to: '/start', icon: Home, labelKey: 'nav.start' },
  { to: '/gallery', icon: Images, labelKey: 'nav.gallery' },
  { to: '/search', icon: Sparkles, labelKey: 'nav.search' },
  { to: '/chat', icon: MessageCircle, labelKey: 'nav.chat' },
  { to: '/albums', icon: BookImage, labelKey: 'nav.albums' },
  { to: '/highlights', icon: Clapperboard, labelKey: 'nav.highlights' },
  { to: '/people', icon: Users, labelKey: 'nav.people' },
  { to: '/map', icon: Map, labelKey: 'nav.map' },
  { to: '/trips', icon: Plane, labelKey: 'nav.trips' },
  { to: '/leitstand', icon: Gauge, labelKey: 'nav.leitstand' },
]

type Me = { role: string; access_config?: Record<string, any> | null }

// Primary tabs shown directly in the mobile bottom bar; the rest go behind "Mehr".
const MOBILE_PRIMARY = new Set(['/start', '/gallery', '/search', '/people'])

export default function Layout() {
  const loc = useLocation()
  const { dark, toggle } = useTheme()
  const { t } = useT()
  const [moreOpen, setMoreOpen] = useState(false)
  const hasToken = !!getToken()
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
    ? [...nav.slice(0, 4), { to: '/relationships', icon: Network, labelKey: 'nav.relationships' }, ...nav.slice(4)]
    : nav
  const visibleNav = fullNav.filter(n =>
    (n.to !== '/map' || allow('allow_map')) &&
    ((n.to !== '/pipeline' && n.to !== '/leitstand') || (me ? me.role === 'admin' || me.access_config?.allow_pipeline : true)),
  )

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-100 dark:bg-zinc-950">
      {/* ── Sidebar ──────────────────────────────── */}
      <aside className="hidden md:flex w-[220px] flex-col bg-gradient-to-b from-zinc-900 to-zinc-950 border-r border-white/5 shrink-0 select-none">
        {/* Logo */}
        <div className="h-28 flex items-center justify-center px-2 border-b border-white/5">
          <img src="/photoflow-logo.png" alt="NimtaFlow" className="w-full max-h-24 object-contain" />
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 px-2 flex flex-col gap-0.5 overflow-y-auto">
          {visibleNav.map(({ to, icon: Icon, labelKey }) => (
            <NavLink key={to} to={to}>
              {({ isActive }) => (
                <div className={clsx(
                  'nav-pill',
                  isActive && 'active',
                )}>
                  <Icon size={18} className="shrink-0" />
                  <span className="hidden md:block">{t(labelKey)}</span>
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
                <span className="hidden md:block">{t('nav.settings')}</span>
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
            <span className="hidden md:block">{dark ? t('nav.lightTheme') : t('nav.darkTheme')}</span>
          </button>
          <div className="hidden md:flex items-center justify-between px-2.5 py-1.5">
            <span className="text-[11px] text-zinc-500">{t('nav.language')}</span>
            <LanguageSwitcher />
          </div>
          <UserBadge />
          <VersionBadge />
        </div>
      </aside>

      {/* ── Main (pb on mobile so content clears the fixed bottom bar) ─────── */}
      <main className="flex-1 overflow-auto bg-white dark:bg-zinc-950 min-w-0 pb-16 md:pb-0">
        <ErrorBoundary resetKey={loc.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>

      {/* ── Mobile bottom nav: 4 primary tabs + "Mehr" ───────────────────── */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-zinc-900 border-t border-white/5 flex pb-[env(safe-area-inset-bottom)]">
        {visibleNav.filter(n => MOBILE_PRIMARY.has(n.to)).map(({ to, icon: Icon, labelKey }) => (
          <NavLink key={to} to={to} className="flex-1">
            {({ isActive }) => (
              <div className={clsx('flex flex-col items-center gap-1 py-2 text-[10px] font-medium transition-colors',
                isActive ? 'text-indigo-400' : 'text-zinc-500')}>
                <Icon size={20} />{t(labelKey)}
              </div>
            )}
          </NavLink>
        ))}
        <button onClick={() => setMoreOpen(true)} className="flex-1">
          <div className="flex flex-col items-center gap-1 py-2 text-[10px] font-medium text-zinc-500">
            <Menu size={20} />{t('nav.more')}
          </div>
        </button>
      </nav>

      {/* ── "Mehr" drawer: remaining sections + actions ──────────────────── */}
      {moreOpen && (
        <div className="md:hidden fixed inset-0 z-50 bg-black/60" onClick={() => setMoreOpen(false)}>
          <div className="absolute bottom-0 left-0 right-0 bg-zinc-900 rounded-t-2xl p-4 pb-8" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-zinc-200">{t('nav.more')}</span>
              <button onClick={() => setMoreOpen(false)} className="text-zinc-400 hover:text-white"><X size={20} /></button>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {[...visibleNav.filter(n => !MOBILE_PRIMARY.has(n.to)),
                { to: '/profile', icon: UserCircle, labelKey: 'nav.profile' },
                { to: '/settings', icon: Settings, labelKey: 'nav.settings' }].map(({ to, icon: Icon, labelKey }) => (
                <NavLink key={to} to={to} onClick={() => setMoreOpen(false)}>
                  {({ isActive }) => (
                    <div className={clsx('flex flex-col items-center gap-1.5 py-3 rounded-xl text-[11px] font-medium',
                      isActive ? 'bg-indigo-600/20 text-indigo-300' : 'text-zinc-300 hover:bg-white/5')}>
                      <Icon size={22} /><span className="text-center leading-tight">{t(labelKey)}</span>
                    </div>
                  )}
                </NavLink>
              ))}
              <button onClick={() => { toggle(); }} className="flex flex-col items-center gap-1.5 py-3 rounded-xl text-[11px] font-medium text-zinc-300 hover:bg-white/5">
                {dark ? <Sun size={22} /> : <Moon size={22} />}<span className="text-center leading-tight">{dark ? t('nav.light') : t('nav.dark')}</span>
              </button>
            </div>
            <div className="mt-4 flex items-center justify-center">
              <LanguageSwitcher />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

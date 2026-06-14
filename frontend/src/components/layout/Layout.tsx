import { Outlet, NavLink } from 'react-router-dom'
import { Images, Users, Map, Activity, Settings, Sun, Moon } from 'lucide-react'
import { useTheme } from '../../store/theme'
import clsx from 'clsx'

const nav = [
  { to: '/gallery', icon: Images, label: 'Galerie' },
  { to: '/people', icon: Users, label: 'Personen' },
  { to: '/map', icon: Map, label: 'Karte' },
  { to: '/pipeline', icon: Activity, label: 'Pipeline' },
  { to: '/settings', icon: Settings, label: 'Einstellungen' },
]

export default function Layout() {
  const { dark, toggle } = useTheme()

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Sidebar */}
      <aside className="w-16 md:w-56 flex flex-col bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 shrink-0">
        {/* Logo */}
        <div className="h-14 flex items-center px-4 gap-3 border-b border-gray-200 dark:border-gray-800">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
            PF
          </div>
          <span className="hidden md:block font-semibold text-gray-900 dark:text-white">PhotoFlow</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 flex flex-col gap-1 px-2">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-2 py-2 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800',
                )
              }
            >
              <Icon size={20} className="shrink-0" />
              <span className="hidden md:block">{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Theme toggle */}
        <div className="p-2 border-t border-gray-200 dark:border-gray-800">
          <button
            onClick={toggle}
            className="w-full flex items-center gap-3 px-2 py-2 rounded-lg text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {dark ? <Sun size={20} /> : <Moon size={20} />}
            <span className="hidden md:block">{dark ? 'Hell' : 'Dunkel'}</span>
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

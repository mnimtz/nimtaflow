import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, getToken } from './lib/api'
import SetupPage from './pages/SetupPage'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import GalleryPage from './pages/GalleryPage'
import HighlightsPage from './pages/HighlightsPage'
import SearchPage from './pages/SearchPage'
import ChatPage from './pages/ChatPage'
import AlbumsPage from './pages/AlbumsPage'
import PeoplePage from './pages/PeoplePage'
import RelationshipsPage from './pages/RelationshipsPage'
import MapPage from './pages/MapPage'
import TripsPage from './pages/TripsPage'
import PipelinePage from './pages/PipelinePage'
import LeitstandPage from './pages/LeitstandPage'
import SettingsPage from './pages/SettingsPage'
import ProfilePage from './pages/ProfilePage'
import LoginPage from './pages/LoginPage'
import PublicSharePage from './pages/PublicSharePage'

export default function App() {
  // Fresh install → first-run setup screen (create the initial admin).
  const { data: status, isLoading } = useQuery<{ needs_setup: boolean; enforce: boolean }>({
    queryKey: ['auth-status'],
    queryFn: () => api.get('/auth/status').then(r => r.data),
    retry: false, staleTime: 60_000,
  })
  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 text-gray-400">Lädt…</div>
  }
  if (status?.needs_setup) return <SetupPage />

  // Auth gate: when login is enforced and there's no session token, render ONLY the
  // login (and public share) — never the app shell. Prevents the brief "flash" of the
  // navigation/registers before the 401-redirect would kick in. (Data is already
  // API-protected; this also removes the security-optics leak of the empty shell.)
  // Reaktiver Auth-Zustand: nach dem Login schreibt setTokens den Token UND feuert
  // 'pf-auth' → hier neu bewerten. Vorher war `authed` ein einmaliger getToken()-Read,
  // der nach navigate('/') nicht neu lief → man war erst nach F5 „drin".
  const [authed, setAuthed] = useState(() => !!getToken())
  useEffect(() => {
    const sync = () => setAuthed(!!getToken())
    window.addEventListener('pf-auth', sync)      // Login/Logout in diesem Tab
    window.addEventListener('storage', sync)      // Login/Logout in anderem Tab
    return () => { window.removeEventListener('pf-auth', sync); window.removeEventListener('storage', sync) }
  }, [])
  if (status?.enforce && !authed) {
    return (
      <Routes>
        <Route path="/s/:token" element={<PublicSharePage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/s/:token" element={<PublicSharePage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/start" replace />} />
        <Route path="/start" element={<DashboardPage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/albums" element={<AlbumsPage />} />
        <Route path="/highlights" element={<HighlightsPage />} />
        <Route path="/people" element={<PeoplePage />} />
        <Route path="/relationships" element={<RelationshipsPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/trips" element={<TripsPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/leitstand" element={<LeitstandPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  )
}

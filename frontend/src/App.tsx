import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import GalleryPage from './pages/GalleryPage'
import SearchPage from './pages/SearchPage'
import AlbumsPage from './pages/AlbumsPage'
import PeoplePage from './pages/PeoplePage'
import RelationshipsPage from './pages/RelationshipsPage'
import MapPage from './pages/MapPage'
import PipelinePage from './pages/PipelinePage'
import SettingsPage from './pages/SettingsPage'
import ProfilePage from './pages/ProfilePage'
import LoginPage from './pages/LoginPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/gallery" replace />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/albums" element={<AlbumsPage />} />
        <Route path="/people" element={<PeoplePage />} />
        <Route path="/relationships" element={<RelationshipsPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  )
}

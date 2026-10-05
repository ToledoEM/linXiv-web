import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, setUnauthorizedHandler } from './api'
import Sidebar, { type NavItem } from './Sidebar'
import Login from './pages/Login'
import Search from './pages/Search'
import Library from './pages/Library'
import PaperDetail from './pages/PaperDetail'
import Upload from './pages/Upload'
import StatsPage from './pages/Stats'
import Settings from './pages/Settings'

const NAV: NavItem[] = [
  { to: '/', label: 'Home', icon: '⌂', end: true },
  { to: '/library', label: 'Library', icon: '▤' },
  { to: '/search', label: 'Search', icon: '⌕' },
  { to: '/upload', label: 'Upload', icon: '⇪' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

type AuthState = { checked: boolean; enabled: boolean; authenticated: boolean }

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ checked: false, enabled: false, authenticated: false })
  const navigate = useNavigate()

  useEffect(() => {
    setUnauthorizedHandler(() => setAuth((a) => ({ ...a, authenticated: false })))
    api
      .me()
      .then((me) => setAuth({ checked: true, enabled: me.auth_enabled, authenticated: me.authenticated }))
      .catch(() => setAuth({ checked: true, enabled: true, authenticated: false }))
  }, [])

  if (!auth.checked) return null
  if (!auth.authenticated) {
    return <Login onLogin={() => setAuth((a) => ({ ...a, authenticated: true }))} />
  }

  const logout = async () => {
    await api.logout()
    setAuth((a) => ({ ...a, authenticated: false }))
    navigate('/')
  }

  return (
    <div className="layout">
      <Sidebar items={NAV} onLogout={auth.enabled ? logout : undefined} />
      <main className="content">
        <Routes>
          <Route path="/" element={<StatsPage />} />
          <Route path="/library" element={<Library />} />
          <Route path="/search" element={<Search />} />
          <Route path="/paper/*" element={<PaperDetail />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/stats" element={<Navigate to="/" replace />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api, setUnauthorizedHandler } from './api'
import Sidebar, { type NavItem } from './Sidebar'
import Login from './pages/Login'
import Search from './pages/Search'
import Library from './pages/Library'
import PaperDetail from './pages/PaperDetail'
import Upload from './pages/Upload'
import Home from './pages/Home'
import Settings from './pages/Settings'
import AddPaper from './pages/AddPaper'
import Trash from './pages/Trash'
import AuthorDetail from './pages/AuthorDetail'
import Authors from './pages/Authors'
import Graph from './pages/Graph'
import Projects from './pages/Projects'
import ProjectDetail from './pages/ProjectDetail'
import ReadingLists from './pages/ReadingLists'
import { setTexEnabled } from './texStore'

const NAV: NavItem[] = [
  { to: '/', label: 'Home', icon: '⌂', end: true },
  { to: '/library', label: 'Library', icon: '▤' },
  { to: '/projects', label: 'Projects', icon: '◫' },
  { to: '/reading', label: 'Reading', icon: '☰' },
  { to: '/graph', label: 'Graph', icon: '⋈' },
  { to: '/search', label: 'Search', icon: '⌕' },
  { to: '/add', label: 'Add Paper', icon: '＋' },
  { to: '/upload', label: 'Upload', icon: '⇪' },
  { to: '/authors', label: 'Authors', icon: '◎' },
  { to: '/trash', label: 'Trash', icon: '⌫' },
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

  useEffect(() => {
    if (!auth.authenticated) return
    api
      .settings()
      .then((r) => setTexEnabled(r.settings.tex_rendering_enabled))
      .catch(() => {})
  }, [auth.authenticated])

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
          <Route path="/" element={<Home />} />
          <Route path="/library" element={<Library />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/reading" element={<ReadingLists />} />
          <Route path="/graph" element={<Graph />} />
          <Route path="/search" element={<Search />} />
          <Route path="/paper/*" element={<PaperDetail />} />
          <Route path="/add" element={<AddPaper />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/trash" element={<Trash />} />
          <Route path="/authors" element={<Authors />} />
          <Route path="/authors/:id" element={<AuthorDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/stats" element={<Navigate to="/" replace />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}

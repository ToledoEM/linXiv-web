import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, setUnauthorizedHandler } from './api'
import Sidebar, { type NavItem } from './Sidebar'
import Login from './pages/Login'
import Setup from './pages/Setup'
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
import { useGlobalShortcuts } from './shortcuts'
import { hiddenPageFor, useSidebarPages } from './sidebarPages'

const NAV: NavItem[] = [
  { to: '/', label: 'Home', icon: '⌂', end: true },
  { to: '/library', label: 'Library', icon: '▤' },
  { to: '/projects', label: 'Projects', icon: '◫' },
  { to: '/reading', label: 'Reading', icon: '☰', pageKey: 'reading' },
  { to: '/graph', label: 'Graph', icon: '⋈', pageKey: 'graph' },
  { to: '/search', label: 'Search', icon: '⌕', pageKey: 'search' },
  { to: '/add', label: 'Add Paper', icon: '＋', pageKey: 'add' },
  { to: '/upload', label: 'Upload', icon: '⇪', pageKey: 'upload' },
  { to: '/authors', label: 'Authors', icon: '◎' },
  { to: '/trash', label: 'Trash', icon: '⌫', pageKey: 'trash' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

type AuthState = { checked: boolean; enabled: boolean; setup: boolean; authenticated: boolean }

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ checked: false, enabled: false, setup: false, authenticated: false })
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const pages = useSidebarPages()
  useGlobalShortcuts()

  // A page switched off in Settings → Sidebar is unreachable by URL too (desktop AppShell).
  useEffect(() => {
    if (hiddenPageFor(pathname, pages)) navigate('/', { replace: true })
  }, [pathname, pages, navigate])

  useEffect(() => {
    setUnauthorizedHandler(() => setAuth((a) => ({ ...a, authenticated: false })))
    api
      .me()
      .then((me) =>
        setAuth({ checked: true, enabled: me.auth_enabled, setup: me.setup_required, authenticated: me.authenticated }),
      )
      .catch(() => setAuth({ checked: true, enabled: true, setup: false, authenticated: false }))
  }, [])

  useEffect(() => {
    if (!auth.authenticated) return
    api
      .settings()
      .then((r) => setTexEnabled(r.settings.tex_rendering_enabled))
      .catch(() => {})
  }, [auth.authenticated])

  if (!auth.checked) return null
  if (auth.setup) {
    return <Setup onDone={() => setAuth((a) => ({ ...a, setup: false, authenticated: true }))} />
  }
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
      <Sidebar items={NAV.filter((i) => !i.pageKey || pages[i.pageKey])} onLogout={auth.enabled ? logout : undefined} />
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

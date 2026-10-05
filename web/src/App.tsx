import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { api, setUnauthorizedHandler } from './api'
import Login from './pages/Login'
import Search from './pages/Search'
import Library from './pages/Library'
import PaperDetail from './pages/PaperDetail'
import Upload from './pages/Upload'
import StatsPage from './pages/Stats'

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
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          linXiv<span className="brand-web">-web</span>
        </span>
        <nav>
          <NavLink to="/" end>Search</NavLink>
          <NavLink to="/library">Library</NavLink>
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/stats">Stats</NavLink>
        </nav>
        {auth.enabled && (
          <button className="link" onClick={logout}>
            Log out
          </button>
        )}
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/library" element={<Library />} />
          <Route path="/paper/*" element={<PaperDetail />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}

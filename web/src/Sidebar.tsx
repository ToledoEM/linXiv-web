import { useState } from 'react'
import { NavLink } from 'react-router-dom'

export type NavItem = { to: string; label: string; icon: string; end?: boolean }

const STORAGE_KEY = 'lxw.sidebar.collapsed'

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export default function Sidebar({ items, onLogout }: { items: NavItem[]; onLogout?: () => void }) {
  const [collapsed, setCollapsed] = useState(loadCollapsed)

  const toggle = () => {
    const next = !collapsed
    setCollapsed(next)
    try {
      localStorage.setItem(STORAGE_KEY, next ? '1' : '0')
    } catch {
      // storage unavailable: keep in-memory state only
    }
  }

  return (
    <aside className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
      <div className="sidebar-head">
        <span className="brand">
          {collapsed ? (
            'lX'
          ) : (
            <>
              linXiv<span className="brand-web">-web</span>
            </>
          )}
        </span>
        <button
          className="link sidebar-toggle"
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
        >
          {collapsed ? '»' : '«'}
        </button>
      </div>
      <nav>
        {items.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} title={item.label}>
            <span className="nav-icon" aria-hidden="true">
              {item.icon}
            </span>
            <span className="nav-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      {onLogout && (
        <button className="link sidebar-foot" onClick={onLogout} title="Log out">
          <span className="nav-icon" aria-hidden="true">
            ⎋
          </span>
          <span className="nav-label">Log out</span>
        </button>
      )}
    </aside>
  )
}

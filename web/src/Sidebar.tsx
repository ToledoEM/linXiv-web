import { useState, type MouseEvent } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import type { Account } from './account'
import { useBatchRunning } from './batchGuard'
import ConfirmDialog from './ConfirmDialog'
import ThemePicker from './ThemePicker'
import type { PageKey } from './sidebarPages'

export type NavItem = { to: string; label: string; icon: string; end?: boolean; pageKey?: PageKey }

const STORAGE_KEY = 'lxw.sidebar.collapsed'

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export default function Sidebar({
  items,
  onLogout,
  account,
}: {
  items: NavItem[]
  onLogout?: () => void
  account?: Account
}) {
  const [collapsed, setCollapsed] = useState(loadCollapsed)
  const navigate = useNavigate()
  const batchRunning = useBatchRunning()
  // Where the user was heading when a running batch interrupted them.
  const [pending, setPending] = useState<string | null>(null)

  // Leaving the page unmounts the batch panel, which stops the run.
  const guard = (to: string) => (e: MouseEvent) => {
    if (!batchRunning) return
    e.preventDefault()
    setPending(to)
  }

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
          <NavLink key={item.to} to={item.to} end={item.end} title={item.label} onClick={guard(item.to)}>
            <span className="nav-icon" aria-hidden="true">
              {item.icon}
            </span>
            <span className="nav-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-theme">
        <ThemePicker compact />
      </div>
      {account?.multiUser && account.username && (
        <div className="sidebar-user muted small" title={`Logged in as ${account.username} (${account.role})`}>
          {account.username} · {account.role}
        </div>
      )}
      {onLogout && (
        <button className="link sidebar-foot" onClick={onLogout} title="Log out">
          <span className="nav-icon" aria-hidden="true">
            ⎋
          </span>
          <span className="nav-label">Log out</span>
        </button>
      )}
      <a className="sidebar-credit" href="https://github.com/ToledoEM/linXiv-web" target="_blank" rel="noreferrer">
        linXiv-web — open source under Apache License 2.0
      </a>
      <ConfirmDialog
        open={pending !== null}
        title="A batch run is going"
        confirmLabel="Leave and stop"
        onConfirm={() => {
          const to = pending
          setPending(null)
          if (to) void navigate(to)
        }}
        onCancel={() => setPending(null)}
      >
        <p>Leaving this page stops the run. Papers already saved keep their changes.</p>
      </ConfirmDialog>
    </aside>
  )
}

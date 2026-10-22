import { useEffect, useState, type FormEvent } from 'react'
import { accountFrom, setAccount, useAccount } from './account'
import { api } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import type { MultiUserStatus } from './types'
import UsersPanel from './UsersPanel'

/** Settings → Server Admin: the multi-user switch, then the user list while it is on. */
export default function MultiUserSettings() {
  const account = useAccount()
  const [status, setStatus] = useState<MultiUserStatus | null>(null)
  const [username, setUsername] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmOff, setConfirmOff] = useState(false)

  useEffect(() => {
    api
      .multiUser()
      .then((s) => {
        setStatus(s)
        setUsername(s.owner_username ?? '')
      })
      .catch((err) => setError((err as Error).message))
  }, [])

  const toggle = async (enabled: boolean) => {
    setBusy(true)
    setError('')
    try {
      const name = username.trim().toLowerCase()
      const next = await api.setMultiUser(enabled, enabled && name ? name : undefined)
      setStatus(next)
      // The username shows in the sidebar; the login page asks for it from now on.
      setAccount(accountFrom(await api.me()))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
      setConfirmOff(false)
    }
  }

  const enable = (e: FormEvent) => {
    e.preventDefault()
    void toggle(true)
  }

  if (!status) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  return (
    <>
      <div className="card settings-section">
        <h3>Multi-user mode</h3>
        {status.enabled ? (
          <>
            <p>
              On. You sign in as <strong>{status.owner_username}</strong> with the server password; your library is the
              existing one. Every other account gets its own library, and everyone reads the shared library.
            </p>
            {account.owner ? (
              <div className="actions">
                <button type="button" className="danger" disabled={busy} onClick={() => setConfirmOff(true)}>
                  Turn off
                </button>
              </div>
            ) : (
              <p className="muted small">Only the server owner can turn multi-user mode off.</p>
            )}
          </>
        ) : (
          <form onSubmit={enable}>
            <p className="muted small">
              Off: one password, one library. Turning it on keeps your library as it is and adds named accounts, each
              with its own library, plus a shared library that only admins change. The login page then asks for a
              username.
            </p>
            <label className="field">
              <span>Your username</span>
              <input
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                maxLength={32}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              <span className="muted small">
                You keep the server password. Lowercase letters, digits, dot, dash, underscore.
              </span>
            </label>
            <div className="actions">
              <button disabled={busy || !username.trim()}>{busy ? 'Turning on…' : 'Turn on'}</button>
            </div>
          </form>
        )}
        <ErrorText error={error} />
      </div>

      {status.enabled && <UsersPanel selfName={account.username} />}

      <ConfirmDialog
        open={confirmOff}
        title="Turn multi-user mode off?"
        confirmLabel="Turn off"
        busy={busy}
        onConfirm={() => void toggle(false)}
        onCancel={() => setConfirmOff(false)}
      >
        <p>
          Only you can log in afterwards (password only); everyone else is logged out now. Accounts, their libraries and
          the shared library are kept and come back when you turn it on again.
        </p>
      </ConfirmDialog>
    </>
  )
}

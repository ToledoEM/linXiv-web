import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import type { Role, UserAccount } from './types'

const MIN = 8
const ROLES: { value: Role; label: string }[] = [
  { value: 'user', label: 'User' },
  { value: 'admin', label: 'Admin' },
]

type Edit = { id: number; username: string; password: string }

/** Settings → Server Admin → Users (multi-user mode): add, rename, set role or
 *  password, delete. Each account has its own library; deleting the account keeps it. */
export default function UsersPanel({ selfName }: { selfName: string | null }) {
  const [users, setUsers] = useState<UserAccount[] | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('user')
  const [edit, setEdit] = useState<Edit | null>(null)
  const [doomed, setDoomed] = useState<UserAccount | null>(null)

  const refresh = useCallback(
    () =>
      api
        .users()
        .then(setUsers)
        .catch((err) => setError((err as Error).message)),
    [],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  const act = async (fn: () => Promise<string | void>) => {
    setBusy(true)
    setError('')
    setNote('')
    try {
      const msg = await fn()
      if (msg) setNote(msg)
      await refresh()
      return true
    } catch (err) {
      setError((err as Error).message)
      return false
    } finally {
      setBusy(false)
    }
  }

  const create = async (e: FormEvent) => {
    e.preventDefault()
    const name = username.trim().toLowerCase()
    const ok = await act(async () => {
      await api.createUser({ username: name, password, role })
      return `Account ${name} created with its own empty library.`
    })
    if (ok) {
      setUsername('')
      setPassword('')
      setRole('user')
    }
  }

  const saveEdit = async (u: UserAccount) => {
    if (!edit) return
    const body: { username?: string; password?: string } = {}
    const name = edit.username.trim().toLowerCase()
    if (name && name !== u.username) body.username = name
    if (edit.password) body.password = edit.password
    if (!body.username && !body.password) {
      setEdit(null)
      return
    }
    const ok = await act(async () => {
      await api.updateUser(u.id, body)
      return body.password ? `Password set for ${name}; their browsers were logged out.` : `Renamed to ${name}.`
    })
    if (ok) setEdit(null)
  }

  const remove = async () => {
    const u = doomed
    if (!u) return
    await act(async () => {
      const r = await api.deleteUser(u.id)
      return `Account ${u.username} deleted. Its library stays on disk: ${r.library_dir}`
    })
    setDoomed(null)
  }

  const editValid = !!edit && (edit.password === '' || edit.password.length >= MIN) && edit.username.trim() !== ''

  return (
    <div className="card settings-section">
      <h3>Users</h3>
      <p className="muted small">
        Each account has its own library and settings. Users read the shared library and copy papers from it; only
        admins change it. No two accounts may share a password.
      </p>
      {users && (
        <div className="table-wrap">
          <table className="users-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Library</th>
                <th>Created</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    {edit?.id === u.id ? (
                      <div className="field">
                        <input
                          aria-label="Username"
                          value={edit.username}
                          onChange={(e) => setEdit({ ...edit, username: e.target.value })}
                        />
                        <input
                          aria-label="New password"
                          type="password"
                          autoComplete="new-password"
                          placeholder="New password (optional)"
                          value={edit.password}
                          onChange={(e) => setEdit({ ...edit, password: e.target.value })}
                        />
                      </div>
                    ) : (
                      <>
                        {u.username}
                        {u.owner && <span className="pill">owner</span>}
                        {u.username === selfName && <span className="muted small"> (you)</span>}
                      </>
                    )}
                  </td>
                  <td>
                    <select
                      aria-label={`Role of ${u.username}`}
                      value={u.role}
                      disabled={busy || u.owner}
                      title={u.owner ? 'The server owner stays admin' : undefined}
                      onChange={(e) =>
                        void act(async () => {
                          await api.updateUser(u.id, { role: e.target.value as Role })
                          return `${u.username} is now ${e.target.value}; their browsers were logged out.`
                        })
                      }
                    >
                      {ROLES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="mono small">{u.library}</td>
                  <td className="small">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="actions">
                      {edit?.id === u.id ? (
                        <>
                          <button type="button" disabled={busy || !editValid} onClick={() => void saveEdit(u)}>
                            Save
                          </button>
                          <button type="button" className="link" onClick={() => setEdit(null)}>
                            Cancel
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setEdit({ id: u.id, username: u.username, password: '' })}
                          >
                            Edit
                          </button>
                          {!u.owner && u.username !== selfName && (
                            <button type="button" className="danger" disabled={busy} onClick={() => setDoomed(u)}>
                              Delete
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {note && <p className="success">{note}</p>}
      <ErrorText error={error} />

      <form className="users-add" onSubmit={(e) => void create(e)}>
        <h4>Add user</h4>
        <label className="field">
          <span>Username</span>
          <input
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            maxLength={32}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <span className="muted small">Lowercase letters, digits, dot, dash, underscore.</span>
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="new-password"
            minLength={MIN}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="muted small">At least {MIN} characters; must differ from every other account's.</span>
        </label>
        <label className="field">
          <span>Role</span>
          <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <div className="actions">
          <button disabled={busy || !username.trim() || password.length < MIN}>Add user</button>
        </div>
      </form>

      <ConfirmDialog
        open={doomed !== null}
        title={`Delete ${doomed?.username ?? ''}?`}
        confirmLabel="Delete account"
        busy={busy}
        onConfirm={() => void remove()}
        onCancel={() => setDoomed(null)}
      >
        <p>
          The account is removed and its sessions end. Its library ({doomed?.library}) stays on disk; nothing is deleted
          from it.
        </p>
      </ConfirmDialog>
    </div>
  )
}

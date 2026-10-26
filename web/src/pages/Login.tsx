import { useState, type FormEvent } from 'react'
import { api } from '../api'

/** `multiUser`: the server has named accounts, so the form asks for a username too. */
export default function Login({ onLogin, multiUser = false }: { onLogin: () => void; multiUser?: boolean }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(password, remember, multiUser ? username.trim() : undefined)
      onLogin()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit} className="card">
        <h1>
          linXiv<span className="brand-web">-web</span>
        </h1>
        {multiUser && (
          <label>
            Username
            <input
              autoFocus
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
        )}
        <label>
          Password
          <input
            type="password"
            autoFocus={!multiUser}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Remember me on this browser
        </label>
        <button disabled={busy || !password || (multiUser && !username.trim())}>Log in</button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}

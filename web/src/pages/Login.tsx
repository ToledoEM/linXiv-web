import { useState, type FormEvent } from 'react'
import { api } from '../api'

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(password, remember)
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
        <label>
          Password
          <input type="password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Remember me on this browser
        </label>
        <button disabled={busy || !password}>Log in</button>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}

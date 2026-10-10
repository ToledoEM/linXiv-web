import { useEffect, useState, type FormEvent } from 'react'
import { api } from './api'

type Msg = { ok: boolean; text: string } | null
type Source = 'env' | 'stored' | null

const MIN = 8

/** Settings → Server & data → Login: change the admin password, end other sessions. */
export default function LoginSettings() {
  const [source, setSource] = useState<Source | undefined>(undefined)
  const [authOn, setAuthOn] = useState(true)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState<'' | 'password' | 'sessions'>('')
  const [armed, setArmed] = useState(false)
  const [pwMsg, setPwMsg] = useState<Msg>(null)
  const [sessionMsg, setSessionMsg] = useState<Msg>(null)

  useEffect(() => {
    api
      .me()
      .then((m) => {
        setSource(m.password_source)
        setAuthOn(m.auth_enabled)
      })
      .catch(() => setSource(null))
  }, [])

  const mismatch = confirm !== '' && confirm !== next
  const canSave = source === 'stored' && current !== '' && next.length >= MIN && next === confirm && !busy

  const change = async (e: FormEvent) => {
    e.preventDefault()
    if (!canSave) return
    setBusy('password')
    setPwMsg(null)
    try {
      await api.changePassword(current, next)
      setCurrent('')
      setNext('')
      setConfirm('')
      setPwMsg({ ok: true, text: 'Password changed. Other browsers were logged out.' })
    } catch (err) {
      setPwMsg({ ok: false, text: (err as Error).message })
    } finally {
      setBusy('')
    }
  }

  const revokeOthers = async () => {
    setArmed(false)
    setBusy('sessions')
    setSessionMsg(null)
    try {
      const r = await api.revokeOtherSessions()
      setSessionMsg({ ok: true, text: `${r.revoked} other session${r.revoked === 1 ? '' : 's'} logged out.` })
    } catch (err) {
      setSessionMsg({ ok: false, text: (err as Error).message })
    } finally {
      setBusy('')
    }
  }

  if (source === undefined) return null

  return (
    <div className="card settings-section">
      <h3>Login</h3>
      {!authOn ? (
        <p className="muted small">No password is set: this loopback-only instance is open without login.</p>
      ) : source === 'env' ? (
        <p className="muted small">
          The password comes from <code>LINXIV_WEB_PASSWORD_HASH</code> / <code>LINXIV_WEB_PASSWORD</code>. Change it
          there and restart the container.
        </p>
      ) : (
        <form onSubmit={(e) => void change(e)}>
          <label className="field">
            <span>Current password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </label>
          <label className="field">
            <span>New password</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={MIN}
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Repeat new password</span>
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            {mismatch && <span className="error small">Passwords don't match.</span>}
          </label>
          <p className="muted small">At least {MIN} characters. Every other browser is logged out.</p>
          <div className="actions">
            <button type="submit" disabled={!canSave}>
              {busy === 'password' ? 'Changing…' : 'Change password'}
            </button>
          </div>
          {pwMsg && <p className={pwMsg.ok ? 'success' : 'error'}>{pwMsg.text}</p>}
        </form>
      )}
      {authOn && (
        <>
          <p className="muted small">
            Lost a device or logged in somewhere you shouldn't have? End every session except this one.
          </p>
          <div className="actions">
            {armed ? (
              <>
                <button className="danger armed" disabled={!!busy} onClick={() => void revokeOthers()}>
                  Confirm: log out others
                </button>
                <button className="link" disabled={!!busy} onClick={() => setArmed(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <button className="danger" disabled={!!busy} onClick={() => setArmed(true)}>
                Log out other sessions
              </button>
            )}
          </div>
          {sessionMsg && <p className={sessionMsg.ok ? 'success' : 'error'}>{sessionMsg.text}</p>}
        </>
      )}
    </div>
  )
}

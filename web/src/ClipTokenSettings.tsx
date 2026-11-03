import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { ClipTokenStatus } from './types'

/** Settings → Library: the token the browser add-on saves papers with. One per account. */
export default function ClipTokenSettings() {
  const [status, setStatus] = useState<ClipTokenStatus | null>(null)
  const [token, setToken] = useState('')
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(
    () =>
      api
        .clipTokenStatus()
        .then(setStatus)
        .catch((err) => setError((err as Error).message)),
    [],
  )

  useEffect(() => {
    void load()
  }, [load])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card settings-section">
      <h3>Browser add-on</h3>
      <p className="muted small">
        Lets the linXiv Firefox add-on save papers to your library. Saved papers go on the reading list{' '}
        <em>Imported - to check</em>. A paper already in your library joins the list and stays as it is.
      </p>
      <div className="field">
        <span>Access token</span>
        <span className="muted small">
          {status?.set
            ? `Token set (…${status.hint}, created ${status.created?.slice(0, 10)}).`
            : 'No token yet: the add-on cannot save here.'}
        </span>
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                setToken((await api.clipCreateToken()).token)
              })
            }
          >
            {status?.set ? 'Replace token' : 'Create token'}
          </button>
          {status?.set && (
            <button
              type="button"
              className={armed ? 'danger armed' : 'link danger-link'}
              disabled={busy}
              onBlur={() => setArmed(false)}
              onClick={() => {
                if (!armed) return setArmed(true)
                setArmed(false)
                void run(async () => {
                  await api.clipRevokeToken()
                  setToken('')
                })
              }}
            >
              {armed ? 'Revoke now?' : 'Revoke token'}
            </button>
          )}
        </div>
        {token && (
          <>
            <pre className="mono small">{token}</pre>
            <p className="success small">Copy the token now: it is shown only once.</p>
          </>
        )}
      </div>
      <ErrorText error={error} />
    </div>
  )
}

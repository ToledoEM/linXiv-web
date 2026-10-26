import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { DIAGNOSTICS_URL, api, fetchDiagnostics } from './api'
import { ErrorText } from './components'
import type { SystemStatus, UpdateMode, UpdateStatus, UserSettings } from './types'

const MODES: { value: UpdateMode; label: string }[] = [
  { value: 'off', label: 'Off' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly (Recommended)' },
  { value: 'monthly', label: 'Monthly' },
]

const when = (ts: string) => new Date(ts).toLocaleString()

/** Folder sizes: B up to TB. */
function formatSize(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${units[i]}`
}

function UpdateLine({ u }: { u: UpdateStatus }) {
  if (u.update_available) {
    return (
      <p className="update-available">
        Version {u.latest} is available. Pull <span className="mono">{`${u.image}:${u.latest}`}</span>, then recreate
        the container (<span className="mono">docker compose pull &amp;&amp; docker compose up -d</span>).
      </p>
    )
  }
  if (u.latest && !u.error) return <p className="muted small">Up to date (latest release {u.latest}).</p>
  return null
}

/** Settings → About for non-admin accounts: version only (release check and server
 *  status are admin only). */
export function AboutBasic() {
  const [version, setVersion] = useState('')
  useEffect(() => {
    api
      .health()
      .then((h) => setVersion(h.version))
      .catch(() => setVersion(''))
  }, [])
  return (
    <div className="card settings-section">
      <h3>About</h3>
      <strong>linXiv-web</strong>
      <div className="muted small">Version {version || '…'}</div>
      <p className="muted small">
        Web interface for linXiv. Open source under the Apache License 2.0.{' '}
        <a href="https://github.com/ToledoEM/linXiv-web" target="_blank" rel="noreferrer">
          Source on GitHub
        </a>
      </p>
    </div>
  )
}

/** Settings → About: version + release check, health, disk space (Sonarr-style status page). */
export default function AboutSettings({
  draft,
  set,
  footer,
}: {
  draft: UserSettings
  set: <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => void
  footer: ReactNode
}) {
  const [update, setUpdate] = useState<UpdateStatus | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState('')
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [systemError, setSystemError] = useState('')

  const loadSystem = useCallback(
    () =>
      api
        .systemStatus()
        .then((s) => {
          setSystem(s)
          setSystemError('')
        })
        .catch((err) => setSystemError((err as Error).message)),
    [],
  )

  useEffect(() => {
    api
      .updateStatus()
      .then(setUpdate)
      .catch((err) => setCheckError((err as Error).message))
    void loadSystem()
  }, [loadSystem])

  const check = async () => {
    setChecking(true)
    setCheckError('')
    try {
      setUpdate(await api.checkUpdate())
      void loadSystem()
    } catch (err) {
      setCheckError((err as Error).message)
    } finally {
      setChecking(false)
    }
  }

  return (
    <>
      <div className="card settings-section">
        <h3>About</h3>
        <div className="about-row">
          <div>
            <strong>linXiv-web</strong>
            <div className="muted small">Version {update?.current ?? '…'}</div>
          </div>
          <button type="button" onClick={check} disabled={checking}>
            {checking ? 'Checking…' : 'Check for updates'}
          </button>
        </div>
        {update && <UpdateLine u={update} />}
        {update?.error && <p className="error">Last check failed: {update.error}</p>}
        <ErrorText error={checkError} />
        {update?.checked_at && <p className="muted small">Last checked {when(update.checked_at)}.</p>}
        <p className="muted small">
          Web interface for linXiv. Open source under the Apache License 2.0.{' '}
          <a href="https://github.com/ToledoEM/linXiv-web" target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
        </p>
        <div className="about-divider" />
        <label className="about-row">
          <span>
            <strong>Check automatically</strong>
            <span className="muted small block">
              Look for a new image release (ghcr.io tags) in the background on this schedule. Off by default.
            </span>
          </span>
          <select
            value={draft.web_update_check}
            onChange={(e) => set('web_update_check', e.target.value as UpdateMode)}
          >
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        {footer}
      </div>

      <div className="card settings-section">
        <h3>Health</h3>
        <ErrorText error={systemError} />
        {system &&
          (system.issues.length === 0 ? (
            <p>No issues with your configuration.</p>
          ) : (
            <ul className="health-list">
              {system.issues.map((i) => (
                <li key={i.message} className={`health-${i.level}`}>
                  <span className="pill">{i.level}</span> {i.message}
                </li>
              ))}
            </ul>
          ))}
      </div>

      <div className="card settings-section">
        <h3>Disk space</h3>
        <p className="muted small">Space linXiv uses in each folder.</p>
        {system && (
          <div className="table-wrap">
            <table className="disk-table">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Used</th>
                  <th>Files</th>
                  <th aria-label="Share of linXiv's total" />
                </tr>
              </thead>
              <tbody>
                {system.disk.map((d) => {
                  const all = system.disk.reduce((sum, r) => sum + (r.used ?? 0), 0)
                  const share = all > 0 && d.used !== undefined ? (d.used / all) * 100 : 0
                  return (
                    <tr key={d.label}>
                      <td>
                        <span className="mono">{d.path}</span>
                        <span className="muted small block">{d.label}</span>
                      </td>
                      {d.error || d.used === undefined ? (
                        <td colSpan={3} className="error">
                          {d.error ?? 'unknown'}
                        </td>
                      ) : (
                        <>
                          <td className="nowrap">{formatSize(d.used)}</td>
                          <td className="nowrap">{(d.files ?? 0).toLocaleString()}</td>
                          <td className="disk-bar-cell">
                            <div
                              className="disk-bar"
                              role="meter"
                              aria-valuemin={0}
                              aria-valuemax={100}
                              aria-valuenow={Math.round(share)}
                              title={`${Math.round(share)}% of linXiv's total`}
                            >
                              <div style={{ width: `${share}%` }} />
                            </div>
                          </td>
                        </>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Diagnostics />
    </>
  )
}

/** Redacted Markdown report for bug reports: view, copy, download. */
function Diagnostics() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const create = async () => {
    setBusy(true)
    setError('')
    setCopied(false)
    try {
      setText(await fetchDiagnostics())
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setError('Copy failed: select the text and copy it by hand.')
    }
  }

  return (
    <div className="card settings-section">
      <h3>Diagnostics</h3>
      <p className="muted small">
        A report to attach to a bug report: versions, configuration, library counts, disk, health and whether outside
        services are reachable. API keys, passwords and private addresses show only as set or not set.
      </p>
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => void create()}>
          {busy ? 'Checking…' : text ? 'Create again' : 'Create report'}
        </button>
        {text && (
          <>
            <button type="button" onClick={() => void copy()}>
              {copied ? 'Copied' : 'Copy'}
            </button>
            <a className="button" href={DIAGNOSTICS_URL} download="linxiv-web-diagnostics.md">
              Download .md
            </a>
          </>
        )}
      </div>
      <ErrorText error={error} />
      {text && <pre className="log-view diagnostics-view">{text}</pre>}
    </div>
  )
}

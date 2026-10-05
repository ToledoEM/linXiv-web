import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorText } from '../components'
import { MathText } from '../tex'
import type { TrashListing } from '../types'

const when = (ts?: string | null) => (ts ? ts.replace('T', ' ').slice(0, 16) : '')

/** Two-click permanent delete: the first click arms the button. */
function PurgeButton({ busy, onConfirm }: { busy: boolean; onConfirm: () => void }) {
  const [armed, setArmed] = useState(false)
  if (!armed) {
    return (
      <button className="danger" disabled={busy} onClick={() => setArmed(true)}>
        Delete forever
      </button>
    )
  }
  return (
    <>
      <button className="danger armed" disabled={busy} onClick={onConfirm}>
        Confirm delete
      </button>
      <button className="link" disabled={busy} onClick={() => setArmed(false)}>
        Cancel
      </button>
    </>
  )
}

export default function Trash() {
  const [trash, setTrash] = useState<TrashListing | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api
      .trash()
      .then(setTrash)
      .catch((err) => setError((err as Error).message))
  }, [])

  useEffect(load, [load])

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    setError('')
    try {
      await fn()
      load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy('')
    }
  }

  if (!trash) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  return (
    <section>
      <h2>Trash</h2>
      <p className="muted">
        Deleted papers stay here until you restore them or delete them forever. Restoring brings back the
        paper with its PDF and project links.
      </p>
      <ErrorText error={error} />

      <h3>Papers</h3>
      {trash.papers.length === 0 ? (
        <p className="muted">No deleted papers.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Paper</th>
                <th>Deleted</th>
                <th>PDF</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {trash.papers.map((p) => (
                <tr key={p.source_id}>
                  <td>
                    <MathText forceInline>{p.title}</MathText>
                    <div className="muted small">
                      {p.authors?.slice(0, 3).join(', ')}
                      {p.authors?.length > 3 && ' et al.'} · <span className="mono">{p.source_id}</span>
                    </div>
                  </td>
                  <td className="nowrap small">{when(p.deleted_at)}</td>
                  <td>{p.had_pdf ? '✓' : ''}</td>
                  <td>
                    <div className="actions row-actions">
                      <button
                        disabled={!!busy}
                        onClick={() => act(p.source_id, () => api.restorePaper(p.source_id))}
                      >
                        Restore
                      </button>
                      <PurgeButton
                        busy={!!busy}
                        onConfirm={() => act(p.source_id, () => api.purgePaper(p.source_id))}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {trash.projects.length > 0 && (
        <>
          <h3>Projects</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Deleted</th>
                  <th>Papers</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {trash.projects.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td className="nowrap small">{when(p.deleted_at)}</td>
                    <td>{p.paper_count}</td>
                    <td>
                      <div className="actions row-actions">
                        <button
                          disabled={!!busy}
                          onClick={() => act(`project:${p.id}`, () => api.restoreProject(p.id))}
                        >
                          Restore
                        </button>
                        <PurgeButton
                          busy={!!busy}
                          onConfirm={() => act(`project:${p.id}`, () => api.purgeProject(p.id))}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="small">
        <Link to="/library">Back to library</Link>
      </p>
    </section>
  )
}

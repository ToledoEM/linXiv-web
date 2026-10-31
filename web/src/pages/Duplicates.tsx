import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, duplicatesTsvUrl, paperPath } from '../api'
import { ErrorText } from '../components'
import ConfirmDialog from '../ConfirmDialog'
import { formatBytes } from '../format'
import { useLibrary } from '../library'
import type { DuplicateGroup, DuplicatesReport } from '../types'

const sidsOf = (g: DuplicateGroup) => [...new Set(g.papers.map((p) => p.source_id))]

/** Papers whose saved PDFs are the same file (Settings → Server Admin →
 *  Find duplicate papers): keep one and merge the others into it, or dismiss. */
export default function Duplicates() {
  const library = useLibrary()
  const [data, setData] = useState<DuplicatesReport | null>(null)
  const [keep, setKeep] = useState<Record<string, string>>({})
  const [confirm, setConfirm] = useState<DuplicateGroup | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .duplicates()
      .then(setData)
      .catch((err) => setError((err as Error).message))
  }, [])

  const winner = (g: DuplicateGroup) => keep[g.sha256] ?? g.papers[0].source_id

  const merge = async (g: DuplicateGroup) => {
    setConfirm(null)
    setBusy(true)
    setError('')
    const w = winner(g)
    try {
      let next = data
      for (const loser of sidsOf(g).filter((s) => s !== w)) next = await api.mergeDuplicate(w, loser)
      setData(next)
    } catch (err) {
      setError((err as Error).message)
      api.duplicates().then(setData).catch(() => {})
    } finally {
      setBusy(false)
    }
  }

  const dismiss = async (g: DuplicateGroup) => {
    setBusy(true)
    setError('')
    try {
      setData(await api.dismissDuplicates(sidsOf(g)))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!data) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  return (
    <section>
      <h2>Duplicates</h2>
      <p className="muted small library-count">
        {data.scanned_at
          ? `${data.groups.length} group${data.groups.length === 1 ? '' : 's'} of papers sharing the same PDF file · checked ${data.scanned_at.replace('T', ' ').slice(0, 16)}`
          : 'Not checked yet: an admin runs "Find duplicate papers" in Settings → Server Admin.'}
        {data.groups.length > 0 && (
          <>
            {' · '}
            <a href={duplicatesTsvUrl()} download>
              Download list (TSV)
            </a>
          </>
        )}
      </p>
      <ErrorText error={error} />
      {data.scanned_at && data.groups.length === 0 && <p className="muted">No duplicates found.</p>}
      {data.groups.map((g) => (
        <div key={g.sha256} className="card dup-group">
          <div className="table-wrap">
            <table className="users-table">
              <tbody>
                {g.papers.map((p) => (
                  <tr key={`${p.source_id}-${p.version}`}>
                    {library.canWrite && (
                      <td className="check-col">
                        <input
                          type="radio"
                          name={`keep-${g.sha256}`}
                          aria-label={`Keep ${p.source_id}`}
                          checked={winner(g) === p.source_id}
                          disabled={busy}
                          onChange={() => setKeep({ ...keep, [g.sha256]: p.source_id })}
                        />
                      </td>
                    )}
                    <td>
                      <Link to={paperPath(p.source_id)}>{p.title || p.source_id}</Link>
                      <div className="muted small mono">
                        {p.source_id} v{p.version}
                      </div>
                      <div className="muted small mono file-line">{p.file}</div>
                    </td>
                    <td className="nowrap muted small">{formatBytes(p.size)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {library.canWrite && (
            <div className="actions">
              <button type="button" disabled={busy} onClick={() => setConfirm(g)}>
                Merge into kept paper
              </button>
              <button type="button" className="link" disabled={busy} onClick={() => void dismiss(g)}>
                Not duplicates
              </button>
            </div>
          )}
        </div>
      ))}
      <ConfirmDialog
        open={confirm !== null}
        title="Merge duplicates?"
        confirmLabel="Merge"
        busy={busy}
        onConfirm={() => confirm && void merge(confirm)}
        onCancel={() => setConfirm(null)}
      >
        <p>
          {confirm && winner(confirm)} is kept. Notes, highlights, projects, tags and PDFs of the other paper
          {confirm && sidsOf(confirm).length > 2 ? 's' : ''} move to it, then{' '}
          {confirm && sidsOf(confirm).length > 2 ? 'they are' : 'it is'} deleted.
        </p>
      </ConfirmDialog>
    </section>
  )
}

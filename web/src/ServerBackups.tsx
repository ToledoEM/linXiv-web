import { useEffect, useState } from 'react'
import { api, serverBackupUrl } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import { formatBytes } from './format'
import type { ServerBackup } from './types'

// papers-20261026-030000.db -> 2026-10-26 03:00:00
const when = (name: string) =>
  name.replace(/^papers-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})\.db$/, '$1-$2-$3 $4:$5:$6')

/** Database backups the "Back up databases" operation keeps on the server. */
export default function ServerBackups({
  keep,
  onKeep,
  version,
}: {
  keep: number
  onKeep: (n: number) => void
  /** Changes when a backup run finishes: reload the list. */
  version: string | null
}) {
  const [list, setList] = useState<ServerBackup[] | null>(null)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState(String(keep))
  const [doomed, setDoomed] = useState<ServerBackup | null>(null)

  useEffect(() => {
    api
      .maintenanceBackups()
      .then((r) => setList(r.backups))
      .catch((err) => setError((err as Error).message))
  }, [version])

  const saveKeep = () => {
    const n = Math.floor(Number(draft))
    if (n >= 1 && n <= 100 && n !== keep) onKeep(n)
    else setDraft(String(keep))
  }

  const remove = async (b: ServerBackup) => {
    setDoomed(null)
    try {
      await api.deleteMaintenanceBackup(b)
      setList((l) => (l ?? []).filter((x) => x !== b))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="server-backups">
      <h4>Database backups on the server</h4>
      <div className="actions">
        <label className="check">
          Keep the newest
          <input
            type="number"
            aria-label="Backups to keep"
            min={1}
            max={100}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={saveKeep}
          />
          per library
        </label>
      </div>
      {list && list.length === 0 && <p className="muted small">None yet.</p>}
      {list && list.length > 0 && (
        <div className="table-wrap">
          <table className="users-table">
            <tbody>
              {list.map((b) => (
                <tr key={`${b.library}/${b.name}`}>
                  <td className="mono small">{b.library}</td>
                  <td>{when(b.name)}</td>
                  <td className="muted small nowrap">{formatBytes(b.size)}</td>
                  <td className="nowrap">
                    <a href={serverBackupUrl(b)} download>
                      Download
                    </a>{' '}
                    <button type="button" className="link" onClick={() => setDoomed(b)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        To restore one, download it and use Restore in Settings → Server &amp; data → Backup while in that library.
      </p>
      <ErrorText error={error} />
      <ConfirmDialog
        open={doomed !== null}
        title="Delete this backup?"
        confirmLabel="Delete"
        onConfirm={() => doomed && void remove(doomed)}
        onCancel={() => setDoomed(null)}
      >
        <p>
          {doomed?.library} · {doomed && when(doomed.name)}
        </p>
      </ConfirmDialog>
    </div>
  )
}

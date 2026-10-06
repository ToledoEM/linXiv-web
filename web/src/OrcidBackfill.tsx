import { useState } from 'react'
import { ApiError, api } from './api'
import { ErrorText } from './components'

/** ORCID backfill (desktop Settings → OrcidBackfillSection). */
export default function OrcidBackfill() {
  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState<{ checked: number; updated: number; errored: number } | null>(null)
  const [error, setError] = useState('')

  const run = async () => {
    setRunning(true)
    setError('')
    try {
      const r = await api.orcidBackfill()
      setLastRun({ checked: r.checked, updated: r.updated.length, errored: r.errored })
    } catch (err) {
      setLastRun(null)
      setError(
        err instanceof ApiError && err.status === 409
          ? 'A backfill is already running.'
          : `ORCID backfill failed (${(err as Error).message}). CrossRef/OpenAlex may be unreachable; try again in a minute.`,
      )
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="card settings-section">
      <h3>Author ORCIDs</h3>
      <p className="muted small">
        New papers already pick up ORCIDs when CrossRef or OpenAlex provide one. This checks up to 20 existing authors
        that have none per click, via the DOI of a paper they're linked to. Click again for more.
      </p>
      <div className="actions">
        <button type="button" onClick={run} disabled={running}>
          {running ? 'Fetching…' : 'Fetch ORCIDs from sources'}
        </button>
        {lastRun && !running && (
          <span className="muted small">
            Checked {lastRun.checked} author{lastRun.checked === 1 ? '' : 's'},{' '}
            {lastRun.updated === 0
              ? 'no ORCIDs found'
              : `filled ${lastRun.updated} ORCID${lastRun.updated === 1 ? '' : 's'}`}
          </span>
        )}
      </div>
      {lastRun && lastRun.errored > 0 && !running && (
        <p className="error">
          {lastRun.errored} lookup{lastRun.errored === 1 ? '' : 's'} failed. CrossRef/OpenAlex may be rate-limiting; try
          again shortly.
        </p>
      )}
      <ErrorText error={error} />
    </div>
  )
}

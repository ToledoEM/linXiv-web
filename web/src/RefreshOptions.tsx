import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { RefreshOptions as Options, RefreshScope } from './types'

const SCOPE_LABEL: Record<RefreshScope, string> = {
  recent_or_preprint: 'Papers published in the last year, and preprints (arXiv, bioRxiv, medRxiv)',
  all: 'Every paper with a recorded source',
}

/** "Refresh metadata": which papers are asked again. Saves on change. */
export default function RefreshOptions() {
  const [opts, setOpts] = useState<Options | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .refreshOptions()
      .then(setOpts)
      .catch((err) => setError((err as Error).message))
  }, [])

  if (!opts) return error ? <ErrorText error={error} /> : null

  const save = async (scope: RefreshScope) => {
    setBusy(true)
    setError('')
    try {
      setOpts(await api.setRefreshOptions(scope))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fill-options small">
      <fieldset>
        <legend>Refresh</legend>
        {opts.all_scopes.map((s) => (
          <label key={s} className="check">
            <input
              type="radio"
              name="refresh-scope"
              checked={opts.scope === s}
              disabled={busy}
              onChange={() => void save(s)}
            />
            {SCOPE_LABEL[s] ?? s}
          </label>
        ))}
      </fieldset>
      <ErrorText error={error} />
    </div>
  )
}

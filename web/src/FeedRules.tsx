import { useEffect, useState, type FormEvent } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { FeedRule } from './types'

const FIELDS: FeedRule['field'][] = ['TITLE', 'SUMMARY', 'AUTHOR']
const ACTIONS: FeedRule['action'][] = ['DENY', 'ALLOW']

/** Home feed auto-filter rules (desktop Settings → FeedFilterRulesSection). */
export default function FeedRules() {
  const [rules, setRules] = useState<FeedRule[] | null>(null)
  const [field, setField] = useState<FeedRule['field']>('TITLE')
  const [action, setAction] = useState<FeedRule['action']>('DENY')
  const [keywords, setKeywords] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = () =>
    api
      .feedRules()
      .then((r) => setRules(r.rules))
      .catch((err) => setError((err as Error).message))

  useEffect(() => {
    void load()
  }, [])

  const run = async (fn: () => Promise<unknown>) => {
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

  const add = (e: FormEvent) => {
    e.preventDefault()
    const k = keywords.trim()
    if (!k || busy) return
    void run(async () => {
      await api.addFeedRule({ field, keywords: k, action })
      setKeywords('')
    })
  }

  return (
    <div className="card settings-section">
      <h3>Feed filters</h3>
      <p className="muted small">
        Auto-hide home feed entries. A DENY rule hides a match (all comma-separated keywords must appear); an ALLOW
        rule overrides a DENY match.
      </p>
      <form className="toolbar" onSubmit={add}>
        <select aria-label="Field" value={field} onChange={(e) => setField(e.target.value as FeedRule['field'])}>
          {FIELDS.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <select aria-label="Action" value={action} onChange={(e) => setAction(e.target.value as FeedRule['action'])}>
          {ACTIONS.map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <input
          className="grow"
          aria-label="Keywords"
          placeholder="keyword, another keyword"
          value={keywords}
          maxLength={1000}
          onChange={(e) => setKeywords(e.target.value)}
        />
        <button disabled={busy || !keywords.trim()}>Add rule</button>
      </form>
      <ErrorText error={error} />
      {rules === null ? (
        !error && <p className="muted small">Loading…</p>
      ) : rules.length === 0 ? (
        <p className="muted small">No filter rules yet.</p>
      ) : (
        <ul className="rule-list">
          {rules.map((r) => (
            <li key={r.rule_id}>
              <span>
                <strong>{r.action}</strong> {r.field}: {r.keywords}
              </span>
              <button
                type="button"
                className="link"
                disabled={busy}
                aria-label={`Remove rule ${r.keywords}`}
                onClick={() => run(() => api.deleteFeedRule(r.rule_id))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

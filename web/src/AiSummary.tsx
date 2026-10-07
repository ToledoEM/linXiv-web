import { useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { SummaryResult } from './types'

/** Paper page: AI summary from the abstract, or abstract + saved PDF text; preview, then save as a note. */
export default function AiSummary({
  sourceId,
  hasPdf,
  projectId,
  onSaved,
}: {
  sourceId: string
  hasPdf: boolean
  /** Scope for the saved note (project the page was opened from), else library. */
  projectId: number | null
  onSaved: () => void
}) {
  const [usePdf, setUsePdf] = useState(false)
  const [result, setResult] = useState<SummaryResult | null>(null)
  const [busy, setBusy] = useState<'' | 'summarize' | 'save'>('')
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const go = async (kind: 'summarize' | 'save', fn: () => Promise<void>) => {
    setBusy(kind)
    setError('')
    setDone('')
    try {
      await fn()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy('')
    }
  }

  const summarize = () =>
    go('summarize', async () => {
      setResult(null)
      setResult(await api.summarize(sourceId, usePdf && hasPdf))
    })

  const save = () =>
    go('save', async () => {
      if (!result) return
      const points = result.key_points.map((p) => `- ${p}`).join('\n')
      await api.createNote({
        source_id: sourceId,
        title: 'AI summary',
        content: points ? `${result.summary}\n\n${points}` : result.summary,
        project_id: projectId,
      })
      setResult(null)
      setDone('Saved as a note.')
      onSaved()
    })

  return (
    <div className="ai-summary">
      <div className="actions">
        <div className="chips" role="group" aria-label="Summary source">
          <button
            type="button"
            className={!usePdf || !hasPdf ? 'chip active' : 'chip'}
            aria-pressed={!usePdf || !hasPdf}
            onClick={() => setUsePdf(false)}
          >
            Abstract only
          </button>
          <button
            type="button"
            className={usePdf && hasPdf ? 'chip active' : 'chip'}
            aria-pressed={usePdf && hasPdf}
            disabled={!hasPdf}
            title={hasPdf ? 'Also send the text of the saved PDF' : 'No PDF saved for this paper'}
            onClick={() => setUsePdf(true)}
          >
            Abstract + PDF text
          </button>
        </div>
        <button type="button" disabled={!!busy} onClick={summarize}>
          {busy === 'summarize' ? 'Summarizing…' : 'AI summary'}
        </button>
        {done && <span className="success small">{done}</span>}
      </div>
      <ErrorText error={error} />
      {result && (
        <div className="card ai-summary-card">
          <span className="muted small">
            AI summary from the abstract
            {result.used_pdf && ` and the PDF text${result.truncated ? ' (truncated)' : ''}`}. Check it before saving.
          </span>
          <p className="abstract">{result.summary}</p>
          {result.key_points.length > 0 && (
            <ul>
              {result.key_points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          )}
          <div className="actions">
            <button type="button" disabled={!!busy} onClick={save}>
              {busy === 'save' ? 'Saving…' : 'Save as note'}
            </button>
            <button type="button" className="link" disabled={!!busy} onClick={() => setResult(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

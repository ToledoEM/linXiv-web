import { useState } from 'react'
import { api } from './api'
import ColorSwatches from './ColorSwatches'
import { ErrorText } from './components'
import { parseAnchor } from './pdfAnchor'
import type { Annotation } from './types'
import { submitOnCtrlEnter } from './submitShortcut'

function HighlightItem({
  annotation,
  sourceId,
  version,
  onChanged,
}: {
  annotation: Annotation
  sourceId: string
  version: number
  onChanged: () => Promise<unknown> | void
}) {
  const anchor = parseAnchor(annotation.anchor)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(annotation.comment)
  const [color, setColor] = useState(anchor?.color ?? '')
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      await onChanged()
      setEditing(false)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const changed = draft !== annotation.comment || (!!anchor && color !== anchor.color)
  const save = () =>
    run(() =>
      api.updateAnnotation(
        annotation.id,
        anchor && color !== anchor.color ? { comment: draft, color, source_id: sourceId } : { comment: draft },
      ),
    )

  return (
    <li className="card hl-item" style={anchor ? ({ '--hl': anchor.color } as React.CSSProperties) : undefined}>
      {anchor ? (
        <>
          {anchor.quote && <blockquote>“{anchor.quote}”</blockquote>}
          <div className="hl-meta muted small">
            <span>Page {anchor.page}</span>
            {anchor.version !== version && <span>v{anchor.version} (not shown on this version's PDF)</span>}
            {annotation.project_id !== null && <span>Project #{annotation.project_id}</span>}
          </div>
        </>
      ) : (
        <p className="muted small">Not a readable highlight (invalid anchor).</p>
      )}
      {editing ? (
        <>
          <textarea
            rows={3}
            aria-label="Comment"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={submitOnCtrlEnter(() => {
              if (!busy && changed) void save()
            })}
          />
          {anchor && <ColorSwatches value={color} onChange={setColor} />}
          <div className="actions">
            <button type="button" disabled={busy || !changed} onClick={save}>
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              className="link"
              disabled={busy}
              onClick={() => {
                setEditing(false)
                setDraft(annotation.comment)
                setColor(anchor?.color ?? '')
              }}
            >
              Cancel
            </button>
          </div>
        </>
      ) : (
        <>
          {annotation.comment && <p className="note-body">{annotation.comment}</p>}
          <div className="actions">
            <button type="button" className="link" onClick={() => setEditing(true)}>
              {annotation.comment ? 'Edit' : 'Add comment'}
            </button>
            <button
              type="button"
              className={armed ? 'danger armed' : 'link danger-link'}
              disabled={busy}
              onBlur={() => setArmed(false)}
              onClick={() => (armed ? run(() => api.deleteAnnotation(annotation.id)) : setArmed(true))}
            >
              {armed ? 'Delete forever' : 'Delete'}
            </button>
          </div>
        </>
      )}
      <ErrorText error={error} />
    </li>
  )
}

/** Highlights on this paper (desktop paper page → Annotations tab). */
export default function Highlights({
  annotations,
  sourceId,
  version,
  onChanged,
}: {
  annotations: Annotation[]
  sourceId: string
  version: number
  onChanged: () => Promise<unknown> | void
}) {
  // Reading order: page, then top of the first rect; invalid anchors last.
  const sorted = [...annotations].sort((a, b) => {
    const x = parseAnchor(a.anchor)
    const y = parseAnchor(b.anchor)
    if (!x || !y) return x ? -1 : y ? 1 : a.id - b.id
    return x.page - y.page || x.rects[0].y - y.rects[0].y
  })
  return (
    <>
      <h3>Highlights{annotations.length > 0 && ` (${annotations.length})`}</h3>
      {sorted.length === 0 ? (
        <p className="muted small">No highlights yet. Select text in the PDF to create one.</p>
      ) : (
        <ul className="hl-list">
          {sorted.map((a) => (
            <HighlightItem
              key={`${a.id}-${a.updated_at}`}
              annotation={a}
              sourceId={sourceId}
              version={version}
              onChanged={onChanged}
            />
          ))}
        </ul>
      )}
    </>
  )
}

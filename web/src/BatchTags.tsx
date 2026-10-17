import { useRef, useState } from 'react'
import { api } from './api'
import { useBatchGuard } from './batchGuard'
import { ErrorText } from './components'
import { toggled } from './projects'
import TagSuggestions from './TagSuggestions'
import { MathText } from './tex'
import type { TagSuggestion } from './types'

type Status = 'waiting' | 'asking' | 'ready' | 'none' | 'error' | 'saving' | 'saved'

interface Item {
  status: Status
  suggested: TagSuggestion[]
  picked: Set<string>
  error?: string
}

const blank = (): Item => ({ status: 'waiting', suggested: [], picked: new Set() })

const LABEL: Record<Status, string> = {
  waiting: 'not asked',
  asking: 'asking…',
  ready: 'suggestions',
  none: 'nothing new',
  error: 'failed',
  saving: 'saving…',
  saved: 'saved',
}

/** Library batch: AI tag suggestions for every selected paper, approve per paper
 * or all at once (same layout as BatchMetadata). */
export default function BatchTags({
  selected,
  titles,
  onSaved,
  onSkip,
}: {
  /** Selected source_ids, in table order. */
  selected: string[]
  titles: Record<string, string>
  onSaved: () => void
  onSkip: (sourceId: string) => void
}) {
  const [items, setItems] = useState<Record<string, Item>>({})
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(0)
  const [armedAll, setArmedAll] = useState(false)
  const [summary, setSummary] = useState('')
  const stopRef = useRef(false)
  useBatchGuard(running)

  const item = (sid: string) => items[sid] ?? blank()
  const patch = (sid: string, p: Partial<Item>) =>
    setItems((all) => ({ ...all, [sid]: { ...(all[sid] ?? blank()), ...p } }))

  const suggestAll = async () => {
    stopRef.current = false
    setRunning(true)
    setProgress(0)
    setSummary('')
    for (const [i, sid] of selected.entries()) {
      if (stopRef.current) break
      if (item(sid).status === 'saved') {
        setProgress(i + 1)
        continue
      }
      patch(sid, { ...blank(), status: 'asking' })
      try {
        const r = await api.suggestTags(sid)
        patch(sid, {
          status: r.suggested.length ? 'ready' : 'none',
          suggested: r.suggested,
          picked: new Set(r.suggested.map((s) => s.tag)),
        })
      } catch (err) {
        patch(sid, { status: 'error', error: (err as Error).message })
      }
      setProgress(i + 1)
    }
    setRunning(false)
  }

  const approve = async (sid: string, notify = true): Promise<boolean> => {
    const it = item(sid)
    if (it.status !== 'ready' || !it.picked.size) return false
    patch(sid, { status: 'saving', error: undefined })
    try {
      await api.addTags(sid, [...it.picked])
      patch(sid, { status: 'saved' })
      if (notify) onSaved()
      return true
    } catch (err) {
      patch(sid, { status: 'ready', error: (err as Error).message })
      return false
    }
  }

  const ready = selected.filter((sid) => item(sid).status === 'ready' && item(sid).picked.size > 0)

  const approveAll = async () => {
    if (!armedAll) return setArmedAll(true)
    setArmedAll(false)
    let saved = 0
    let failed = 0
    for (const sid of ready) {
      if (await approve(sid, false)) saved += 1
      else failed += 1
    }
    if (saved) onSaved()
    setSummary(`${saved} saved${failed ? `, ${failed} failed` : ''}.`)
  }

  return (
    <aside className="batch-panel card" aria-label="Batch AI tags">
      <div className="batch-head">
        <strong>Batch AI tags</strong>
        <div className="actions">
          {running ? (
            <button type="button" className="danger" onClick={() => (stopRef.current = true)}>
              Stop
            </button>
          ) : (
            <button type="button" disabled={!selected.length} onClick={suggestAll}>
              Suggest tags for {selected.length} selected
            </button>
          )}
        </div>
        {(running || progress > 0) && (
          <p className="muted small">
            {running ? 'Asking' : 'Asked'} {progress} / {selected.length}
          </p>
        )}
        {!selected.length && <p className="muted small">Tick papers in the table to add them to the batch.</p>}
      </div>

      <ul className="batch-list">
        {selected.map((sid) => {
          const it = item(sid)
          const cardStatus = it.status === 'ready' ? 'match' : it.status
          return (
            <li key={sid} className={`batch-card st-${cardStatus}`}>
              <div className="batch-card-head">
                <span className="batch-title">
                  <MathText forceInline>{titles[sid] ?? sid}</MathText>
                </span>
                <span className={`pill batch-status st-${cardStatus}`}>{LABEL[it.status]}</span>
              </div>
              <span className="muted small mono">{sid}</span>
              {(it.status === 'ready' || it.status === 'saving' || it.status === 'none') && (
                <TagSuggestions
                  suggestions={it.suggested}
                  picked={it.picked}
                  disabled={it.status !== 'ready'}
                  onToggle={(t) => patch(sid, { picked: toggled(it.picked, t) })}
                />
              )}
              <ErrorText error={it.error} />
              {it.status !== 'saved' && (
                <div className="actions">
                  {it.status === 'ready' && (
                    <button type="button" disabled={!it.picked.size} onClick={() => approve(sid)}>
                      Add {it.picked.size} tag{it.picked.size === 1 ? '' : 's'}
                    </button>
                  )}
                  <button type="button" className="link" disabled={it.status === 'saving'} onClick={() => onSkip(sid)}>
                    Skip
                  </button>
                </div>
              )}
            </li>
          )
        })}
      </ul>

      {selected.length > 0 && (
        <div className="batch-foot">
          <button
            type="button"
            className={armedAll ? 'danger armed' : ''}
            disabled={!ready.length || running}
            onBlur={() => setArmedAll(false)}
            onClick={approveAll}
          >
            {armedAll
              ? `Add tags to ${ready.length} paper${ready.length === 1 ? '' : 's'} now`
              : `Approve all (${ready.length})`}
          </button>
          {summary && <span className="small">{summary}</span>}
        </div>
      )}
    </aside>
  )
}

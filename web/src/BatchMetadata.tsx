import { useRef, useState } from 'react'
import { useAiEnabled } from './aiEnabled'
import { api } from './api'
import { useBatchGuard } from './batchGuard'
import { ErrorText } from './components'
import { paperLabel } from './format'
import { useLookupPrefs } from './lookupSource'
import {
  defaultPicked,
  diffFields,
  fromCandidate,
  fromPaper,
  byFileNameOk,
  initialSource,
  MATCH_LABEL,
  sourcesFor,
  toMetadataInput,
  type Field,
  type MatchKind,
} from './metadataFields'
import { MathText } from './tex'
import type { LookupSource, MetadataCandidate, Paper } from './types'

type Status = 'waiting' | 'looking' | 'nomatch' | 'error' | 'match' | 'saving' | 'saved'

interface Item {
  status: Status
  paper?: Paper
  match?: MatchKind
  candidates: MetadataCandidate[]
  chosen: number
  picked: Set<Field>
  error?: string
}

const blank = (): Item => ({ status: 'waiting', candidates: [], chosen: 0, picked: new Set() })

/** Library batch edit: one lookup source for every selected paper, a field diff per
 * paper, and approve per paper or all at once (same routes as Edit metadata). */
export default function BatchMetadata({
  selected,
  titles,
  onSaved,
  onSkip,
}: {
  /** Selected source_ids, in table order. */
  selected: string[]
  /** Titles known from the table, for cards not looked up yet. */
  titles: Record<string, string>
  onSaved: () => void
  onSkip: (sourceId: string) => void
}) {
  // Settings default ("auto" = Crossref for a batch) until the user picks another source.
  const lookupPrefs = useLookupPrefs()
  const [picked, setSource] = useState<LookupSource | null>(null)
  const source = picked ?? initialSource(null, lookupPrefs)
  // Search by the title in each PDF's file name instead of the stored DOI/title.
  const [byFile, setByFile] = useState(false)
  const fileOk = byFileNameOk(source)
  const aiOn = useAiEnabled()
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

  const lookupAll = async () => {
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
      patch(sid, { ...blank(), status: 'looking' })
      try {
        // Fresh current values: the diff must compare against what is stored now.
        const paper = await api.paper(sid)
        const r = await api.lookupMetadata(sid, source, byFile && fileOk && Boolean(paper.pdf_file))
        const found = r.candidates[0]
        patch(sid, {
          status: found ? 'match' : 'nomatch',
          paper,
          match: r.match,
          candidates: r.candidates,
          chosen: 0,
          picked: found ? defaultPicked(fromPaper(paper), fromCandidate(found)) : new Set(),
        })
      } catch (err) {
        patch(sid, { status: 'error', error: (err as Error).message })
      }
      setProgress(i + 1)
    }
    setRunning(false)
  }

  const choose = (sid: string, idx: number) => {
    const it = item(sid)
    const c = it.candidates[idx]
    if (!it.paper || !c) return
    patch(sid, { chosen: idx, picked: defaultPicked(fromPaper(it.paper), fromCandidate(c)) })
  }

  const toggle = (sid: string, field: Field) => {
    const next = new Set(item(sid).picked)
    if (next.has(field)) next.delete(field)
    else next.add(field)
    patch(sid, { picked: next })
  }

  /** Save one paper: stored values with the ticked found fields on top. */
  const approve = async (sid: string, notify = true): Promise<boolean> => {
    const it = item(sid)
    const c = it.candidates[it.chosen]
    if (!it.paper || !c || !it.picked.size) return false
    const found = fromCandidate(c)
    const form = { ...fromPaper(it.paper) }
    for (const f of it.picked) form[f] = found[f]
    const checked = toMetadataInput(form)
    if ('error' in checked) {
      patch(sid, { error: checked.error })
      return false
    }
    patch(sid, { status: 'saving', error: undefined })
    try {
      // Tags as loaded for the diff, so the server skips its own `paper get`.
      await api.saveMetadata(sid, { ...checked.input, tags: it.paper.tags })
      patch(sid, { status: 'saved' })
      if (notify) onSaved()
      return true
    } catch (err) {
      patch(sid, { status: 'match', error: (err as Error).message })
      return false
    }
  }

  const ready = selected.filter((sid) => item(sid).status === 'match' && item(sid).picked.size > 0)

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
    <aside className="batch-panel card" aria-label="Batch edit metadata">
      <div className="batch-head">
        <strong>Batch edit metadata</strong>
        <div className="actions">
          <select
            aria-label="Lookup source"
            value={source}
            disabled={running}
            onChange={(e) => setSource(e.target.value as LookupSource)}
          >
            {sourcesFor(aiOn, lookupPrefs).map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <label className="check" title="Search with the title in each PDF's file name, ignoring the stored DOI">
            <input
              type="checkbox"
              checked={byFile && fileOk}
              disabled={running || !fileOk}
              onChange={(e) => setByFile(e.target.checked)}
            />
            By PDF file name
          </label>
          {running ? (
            <button type="button" className="danger" onClick={() => (stopRef.current = true)}>
              Stop
            </button>
          ) : (
            <button type="button" disabled={!selected.length} onClick={lookupAll}>
              Look up {selected.length} selected
            </button>
          )}
        </div>
        {(running || progress > 0) && (
          <p className="muted small">
            {running ? 'Looking up' : 'Looked up'} {progress} / {selected.length}
          </p>
        )}
        {!selected.length && <p className="muted small">Tick papers in the table to add them to the batch.</p>}
      </div>

      <ul className="batch-list">
        {selected.map((sid) => {
          const it = item(sid)
          const c = it.candidates[it.chosen]
          const current = it.paper ? fromPaper(it.paper) : null
          const found = c ? fromCandidate(c) : null
          const diffs = current && found ? diffFields(current, found) : []
          return (
            <li key={sid} className={`batch-card st-${it.status}`}>
              <div className="batch-card-head">
                <span className="batch-title">
                  {it.paper?.title?.trim() ? (
                    <MathText forceInline>{it.paper.title}</MathText>
                  ) : (
                    <span className="muted">{it.paper ? paperLabel(it.paper) : (titles[sid] ?? sid)}</span>
                  )}
                </span>
                <span className={`pill batch-status st-${it.status}`}>{statusLabel(it, source)}</span>
              </div>
              <span className="muted small mono">{sid}</span>
              {it.paper?.pdf_file && <span className="muted small mono block file-line">{it.paper.pdf_file}</span>}
              {it.candidates.length > 1 && (
                <select
                  aria-label={`Match for ${sid}`}
                  value={it.chosen}
                  disabled={it.status !== 'match'}
                  onChange={(e) => choose(sid, Number(e.target.value))}
                >
                  {it.candidates.map((cand, i) => (
                    <option key={`${cand.ref}-${i}`} value={i}>
                      {(cand.title ?? '(no title)').slice(0, 80)} · {cand.published ?? 'no date'}
                    </option>
                  ))}
                </select>
              )}
              {it.status === 'match' && current && found && diffs.length === 0 && (
                <p className="success small">Agrees with the current metadata.</p>
              )}
              {(it.status === 'match' || it.status === 'saving') && current && found && diffs.length > 0 && (
                <table className="batch-diff">
                  <tbody>
                    {diffs.map((f) => (
                      <tr key={f.key}>
                        <td className="check-col">
                          <input
                            type="checkbox"
                            aria-label={`Use found ${f.label} for ${sid}`}
                            checked={it.picked.has(f.key)}
                            disabled={it.status !== 'match'}
                            onChange={() => toggle(sid, f.key)}
                          />
                        </td>
                        <th scope="row">{f.label}</th>
                        <td>
                          <div className="diff-old">{current[f.key] || <em>empty</em>}</div>
                          <div className="diff-new">{found[f.key] || <em>empty</em>}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <ErrorText error={it.error} />
              {it.status !== 'saved' && (
                <div className="actions">
                  {it.status === 'match' && (
                    <button type="button" disabled={!it.picked.size} onClick={() => approve(sid)}>
                      Approve
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
            {armedAll ? `Save ${ready.length} paper${ready.length === 1 ? '' : 's'} now` : `Approve all (${ready.length})`}
          </button>
          {summary && <span className="small">{summary}</span>}
        </div>
      )}
    </aside>
  )
}

function statusLabel(it: Item, source: LookupSource): string {
  switch (it.status) {
    case 'waiting':
      return 'not looked up'
    case 'looking':
      return 'looking up…'
    case 'nomatch':
      return `no match ${it.match ? MATCH_LABEL[it.match] : ''} (${sourcesFor(true).find((s) => s.value === source)?.label})`
    case 'error':
      return 'lookup failed'
    case 'match':
      return `match ${it.match ? MATCH_LABEL[it.match] : ''}`
    case 'saving':
      return 'saving…'
    case 'saved':
      return 'saved'
  }
}

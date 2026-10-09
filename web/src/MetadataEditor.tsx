import { useState, type FormEvent } from 'react'
import { useAiEnabled } from './aiEnabled'
import { api } from './api'
import { ErrorText } from './components'
import { MathText } from './tex'
import {
  defaultPicked,
  diffFields,
  fromCandidate,
  fromPaper,
  byFileNameOk,
  MATCH_LABEL,
  sourcesFor,
  toMetadataInput,
  type Field,
  type Form,
} from './metadataFields'
import type { LookupSource, MetadataCandidate, Paper } from './types'
import { formSubmitOnCtrlEnter } from './submitShortcut'

/** Field-by-field diff with a checkbox per difference (Zotero-style "retrieve metadata"). */
function Compare({
  current,
  candidate,
  onApply,
  onClose,
}: {
  current: Form
  candidate: MetadataCandidate
  onApply: (patch: Partial<Form>) => void
  onClose: () => void
}) {
  const found = fromCandidate(candidate)
  const diffs = diffFields(current, found)
  // Pre-tick fields where the source has a value; a blank found value would erase data.
  const [picked, setPicked] = useState<Set<Field>>(() => defaultPicked(current, found))
  const toggle = (k: Field) =>
    setPicked((s) => {
      const next = new Set(s)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })

  if (diffs.length === 0) {
    return (
      <div className="card compare">
        <p className="success">This match agrees with the current metadata.</p>
        <button className="link" onClick={onClose}>
          Close
        </button>
      </div>
    )
  }

  return (
    <div className="card compare">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="check-col" />
              <th>Field</th>
              <th>Current</th>
              <th>Found ({candidate.source})</th>
            </tr>
          </thead>
          <tbody>
            {diffs.map((f) => (
              <tr key={f.key}>
                <td className="check-col">
                  <input
                    type="checkbox"
                    aria-label={`Use found ${f.label}`}
                    checked={picked.has(f.key)}
                    onChange={() => toggle(f.key)}
                  />
                </td>
                <td className="nowrap">{f.label}</td>
                <td className="diff-cell muted">{current[f.key] || <em>empty</em>}</td>
                <td className="diff-cell">{found[f.key] || <em className="muted">empty</em>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="actions">
        <button
          disabled={!picked.size}
          onClick={() => onApply(Object.fromEntries([...picked].map((k) => [k, found[k]])) as Partial<Form>)}
        >
          Apply selected
        </button>
        <button className="link" onClick={onClose}>
          Cancel
        </button>
        <span className="muted small">Applied values fill the form; nothing is saved until you press Save.</span>
      </div>
    </div>
  )
}

export default function MetadataEditor({
  paper,
  onSaved,
  onCancel,
}: {
  paper: Paper
  onSaved: () => Promise<void>
  onCancel: () => void
}) {
  const [form, setForm] = useState<Form>(() => fromPaper(paper))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  // bioRxiv/medRxiv DOIs (10.1101/…, bioRxiv's newer 10.64898/…) default to their own API.
  const [source, setSource] = useState<LookupSource>(
    paper.source_id.startsWith('arxiv:')
      ? 'arxiv'
      : /^10\.(1101|64898)\//.test(paper.doi ?? '')
        ? 'biorxiv'
        : 'crossref',
  )
  // Junk or mismatched titles read from the PDF: start with the file name's title.
  const [byFile, setByFile] = useState(Boolean(paper.title_suspect && paper.pdf_file))
  const fileOk = Boolean(paper.pdf_file) && byFileNameOk(source)
  const [looking, setLooking] = useState(false)
  const aiOn = useAiEnabled()
  const [lookupError, setLookupError] = useState('')
  const [found, setFound] = useState<{ match: keyof typeof MATCH_LABEL; candidates: MetadataCandidate[] } | null>(null)
  const [comparing, setComparing] = useState<MetadataCandidate | null>(null)
  const set = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }))

  const lookup = async () => {
    setLooking(true)
    setLookupError('')
    setFound(null)
    setComparing(null)
    try {
      const r = await api.lookupMetadata(paper.source_id, source, byFile && fileOk)
      setFound(r)
      if (r.candidates.length === 1) setComparing(r.candidates[0])
    } catch (err) {
      setLookupError((err as Error).message)
    } finally {
      setLooking(false)
    }
  }

  const save = async (e: FormEvent) => {
    e.preventDefault()
    const checked = toMetadataInput(form)
    if ('error' in checked) return setError(checked.error)
    setSaving(true)
    setError('')
    try {
      await api.saveMetadata(paper.source_id, checked.input)
      await onSaved()
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <div className="metadata-editor">
      <div className="card lookup">
        <div className="toolbar">
          <strong>Retrieve metadata</strong>
          <select aria-label="Lookup source" value={source} onChange={(e) => setSource(e.target.value as LookupSource)}>
            {sourcesFor(aiOn).map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          {paper.pdf_file && (
            <label className="check" title={`Search with the title in ${paper.pdf_file}, ignoring the stored DOI`}>
              <input
                type="checkbox"
                checked={byFile && fileOk}
                disabled={!fileOk}
                onChange={(e) => setByFile(e.target.checked)}
              />
              Search by PDF file name
            </label>
          )}
          <button type="button" onClick={lookup} disabled={looking}>
            {looking ? 'Looking up…' : 'Look up'}
          </button>
        </div>
        <ErrorText error={lookupError} />
        {found && found.candidates.length === 0 && (
          <p className="muted small">No match found {MATCH_LABEL[found.match]}.</p>
        )}
        {found && found.candidates.length > 0 && (
          <>
            <p className="muted small">
              {found.candidates.length} match{found.candidates.length === 1 ? '' : 'es'} {MATCH_LABEL[found.match]}. Pick
              one to compare.
            </p>
            <ul className="candidates">
              {found.candidates.map((c, i) => (
                <li key={`${c.ref}-${i}`} className={comparing === c ? 'active' : ''}>
                  <button type="button" className="candidate" onClick={() => setComparing(c)}>
                    <MathText forceInline>{c.title ?? '(no title)'}</MathText>
                    <span className="muted small block">
                      {c.authors.slice(0, 3).join(', ')}
                      {c.authors.length > 3 && ' et al.'} · {c.published ?? 'no date'} ·{' '}
                      <span className="mono">{c.ref}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {comparing && (
          <Compare
            key={`${comparing.ref}`}
            current={form}
            candidate={comparing}
            onApply={(patch) => {
              set(patch)
              setComparing(null)
            }}
            onClose={() => setComparing(null)}
          />
        )}
      </div>

      <form className="card project-form" onSubmit={save} onKeyDown={formSubmitOnCtrlEnter}>
        <label className="field">
          <span>Title</span>
          <input value={form.title} onChange={(e) => set({ title: e.target.value })} required />
        </label>
        <label className="field">
          <span>Authors (one per line)</span>
          <textarea rows={Math.min(8, Math.max(3, form.authors.split('\n').length))} value={form.authors} onChange={(e) => set({ authors: e.target.value })} />
        </label>
        <div className="field-row">
          <label className="field">
            <span>Published</span>
            <input type="date" value={form.published} onChange={(e) => set({ published: e.target.value })} required />
          </label>
          <label className="field grow">
            <span>Journal / category</span>
            <input value={form.category} onChange={(e) => set({ category: e.target.value })} />
          </label>
        </div>
        <div className="field-row">
          <label className="field grow">
            <span>DOI</span>
            <input className="mono" value={form.doi} onChange={(e) => set({ doi: e.target.value })} />
          </label>
          <label className="field grow">
            <span>URL</span>
            <input value={form.url} onChange={(e) => set({ url: e.target.value })} />
          </label>
        </div>
        <label className="field">
          <span>Abstract</span>
          <textarea rows={6} value={form.summary} onChange={(e) => set({ summary: e.target.value })} />
        </label>
        <p className="muted small">Tags, journal reference, comment and arXiv categories are kept as they are.</p>
        <ErrorText error={error} />
        <div className="actions">
          <button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="link" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

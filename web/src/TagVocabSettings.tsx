import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api, tagVocabExportUrl } from './api'
import { ErrorText } from './components'
import type { TagAlias, TagPendingAlias, TagVocabImport, TagVocabOverview } from './types'

const ORIGIN: Record<TagAlias['origin'], string> = { csv: 'CSV', user: 'added here', llm: 'approved' }

/** Settings → Tag vocabulary: CSV vocabulary import/export, aliases, and the aliases
 *  AI tagging proposed, waiting for review. */
export default function TagVocabSettings() {
  const [overview, setOverview] = useState<TagVocabOverview | null>(null)
  const [pending, setPending] = useState<TagPendingAlias[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [replace, setReplace] = useState(false)
  const [imported, setImported] = useState<TagVocabImport | null>(null)
  const [alias, setAlias] = useState('')
  const [canonical, setCanonical] = useState('')
  const [filter, setFilter] = useState('')

  const load = useCallback(
    () =>
      Promise.all([api.tagVocab(), api.tagPending()]).then(([o, p]) => {
        setOverview(o)
        setPending(p)
      }),
    [],
  )

  useEffect(() => {
    let live = true
    Promise.all([api.tagVocab(), api.tagPending()])
      .then(([o, p]) => {
        if (!live) return
        setOverview(o)
        setPending(p)
      })
      .catch((err) => live && setError((err as Error).message))
    return () => {
      live = false
    }
  }, [])

  const act = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy('')
    }
  }

  const importCsv = (e: FormEvent) => {
    e.preventDefault()
    if (!file) return
    void act('import', async () => setImported(await api.importTagVocab(file, replace)))
  }

  const addAlias = (e: FormEvent) => {
    e.preventDefault()
    void act('alias', async () => {
      await api.addTagAlias(alias.trim(), canonical.trim())
      setAlias('')
      setCanonical('')
    })
  }

  const q = filter.trim().toLowerCase()
  const aliases = (overview?.aliases ?? []).filter(
    (a) => !q || a.alias.toLowerCase().includes(q) || a.canonical.toLowerCase().includes(q),
  )

  return (
    <>
      <div className="card settings-section">
        <h3>Aliases to review</h3>
        <p className="muted small">
          When AI tagging decides a suggested tag is another name for an existing one, it proposes an alias. Approved
          aliases are applied on every later suggestion without asking the model; rejected ones are not proposed again.
        </p>
        {pending.length === 0 ? (
          <p className="muted small">Nothing to review.</p>
        ) : (
          <ul className="tag-vocab-list">
            {pending.map((p) => (
              <li key={p.alias_key} className="actions">
                <span>
                  <strong>{p.alias}</strong> → {p.canonical}
                  {p.source_id && <span className="muted small mono"> · {p.source_id}</span>}
                </span>
                <button type="button" disabled={!!busy} onClick={() => act(p.alias_key, () => api.resolveTagPending(p.alias_key, true))}>
                  Approve
                </button>
                <button
                  type="button"
                  className="link"
                  disabled={!!busy}
                  onClick={() => act(p.alias_key, () => api.resolveTagPending(p.alias_key, false))}
                >
                  Reject
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="card settings-section">
        <h3>Vocabulary CSV</h3>
        <p className="muted small">
          Tags from a CSV join your library's tags as the vocabulary AI tagging matches against. Columns:{' '}
          <code>tag</code>, optional <code>aliases</code> (separated by <code>|</code>) and <code>weight</code> (used
          instead of the paper count). A consolidation tag map with <code>old_tag,new_tag,cluster,papers</code> also
          works: <code>new_tag</code> is the tag and each other <code>old_tag</code> becomes its alias.
        </p>
        {overview && (
          <p className="small">
            {overview.vocab.length} CSV tag{overview.vocab.length === 1 ? '' : 's'}, {overview.aliases.length} alias
            {overview.aliases.length === 1 ? '' : 'es'}.
          </p>
        )}
        <form onSubmit={importCsv} className="actions">
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="Tag vocabulary CSV"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <label className="check">
            <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
            Replace the CSV vocabulary and CSV aliases
          </label>
          <button disabled={!file || !!busy}>{busy === 'import' ? 'Importing…' : 'Import CSV'}</button>
          <a className="button" href={tagVocabExportUrl()} download>
            Download CSV
          </a>
        </form>
        {imported && (
          <p className="muted small">
            Imported {imported.tags} tags and {imported.aliases} aliases
            {imported.layout === 'tag_map' ? ' from a tag map' : ''}
            {imported.replaced ? ', replacing the earlier CSV' : ''}.
            {imported.skipped_siblings > 0 &&
              ` ${imported.skipped_siblings} aliases left out because they name another member of the tag's family (STAT5 for stat3).`}
            {imported.errors.length > 0 && ` Skipped: ${imported.errors.join('; ')}`}
          </p>
        )}
      </div>

      <div className="card settings-section">
        <h3>Aliases</h3>
        <form onSubmit={addAlias} className="actions">
          <input aria-label="Alias" placeholder="alias, e.g. NN" value={alias} onChange={(e) => setAlias(e.target.value)} />
          <span aria-hidden="true">→</span>
          <input
            aria-label="Tag the alias stands for"
            placeholder="tag, e.g. neural network"
            value={canonical}
            onChange={(e) => setCanonical(e.target.value)}
          />
          <button disabled={!alias.trim() || !canonical.trim() || !!busy}>Add alias</button>
        </form>
        {(overview?.aliases.length ?? 0) > 10 && (
          <input aria-label="Filter aliases" placeholder="filter" value={filter} onChange={(e) => setFilter(e.target.value)} />
        )}
        {aliases.length === 0 ? (
          <p className="muted small">No aliases{q ? ' match' : ' yet'}.</p>
        ) : (
          <ul className="tag-vocab-list">
            {aliases.slice(0, 200).map((a) => (
              <li key={a.alias_key}>
                {a.alias} → {a.canonical} <span className="muted small">· {ORIGIN[a.origin]}</span>{' '}
                <button
                  type="button"
                  className="link danger-link"
                  disabled={!!busy}
                  aria-label={`Delete alias ${a.alias}`}
                  onClick={() => act(a.alias_key, () => api.deleteTagAlias(a.alias_key))}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
        {aliases.length > 200 && <p className="muted small">First 200 of {aliases.length}; filter to find others.</p>}
      </div>
      <ErrorText error={error} />
    </>
  )
}

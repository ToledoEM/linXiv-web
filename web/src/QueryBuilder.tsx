import { buildArxivQuery, FIELDS, makeClause, OPERATORS, type Clause } from './searchQuery'
import SuggestInput from './SuggestInput'

/** arXiv clause builder (desktop QueryBuilder + ClauseRow): rows of operator,
 * field and term; "Insert query" hands the built string to the search box. */
export default function QueryBuilder({
  clauses,
  onChange,
  onInsert,
  historyEnabled,
}: {
  clauses: Clause[]
  onChange: (clauses: Clause[]) => void
  onInsert: (query: string) => void
  historyEnabled: boolean
}) {
  const preview = buildArxivQuery(clauses)
  const update = (i: number, patch: Partial<Clause>) =>
    onChange(clauses.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  const remove = (i: number) =>
    onChange(clauses.length <= 1 ? [makeClause()] : clauses.filter((_, j) => j !== i))

  return (
    <div className="card query-builder">
      {clauses.map((c, i) => (
        <div key={c.uid} className="clause-row">
          <select
            aria-label="Operator"
            value={c.operator}
            onChange={(e) => update(i, { operator: e.target.value as Clause['operator'] })}
            // The first row's operator is unused; hidden but kept for alignment.
            style={i === 0 ? { visibility: 'hidden' } : undefined}
            tabIndex={i === 0 ? -1 : undefined}
          >
            {OPERATORS.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
          <select
            aria-label="Field"
            value={c.field}
            onChange={(e) => update(i, { field: e.target.value as Clause['field'] })}
          >
            {FIELDS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <SuggestInput
            aria-label={`Clause ${i + 1} term`}
            placeholder="Search term…"
            value={c.value}
            onValueChange={(value) => update(i, { value })}
            enabled={historyEnabled}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.defaultPrevented && preview) {
                e.preventDefault()
                onInsert(preview)
              }
            }}
          />
          <button type="button" className="link" aria-label={`Remove clause ${i + 1}`} onClick={() => remove(i)}>
            ✕
          </button>
        </div>
      ))}
      <div className="clause-actions">
        <button type="button" className="link" onClick={() => onChange([...clauses, makeClause()])}>
          + Add clause
        </button>
        <span className="grow" />
        {preview ? (
          <code className="query-preview" title={preview}>
            {preview}
          </code>
        ) : (
          <span className="muted small">(empty)</span>
        )}
        <button type="button" className="link" onClick={() => onChange([makeClause()])}>
          Clear
        </button>
        <button type="button" disabled={!preview} onClick={() => onInsert(preview)}>
          Insert query →
        </button>
      </div>
    </div>
  )
}

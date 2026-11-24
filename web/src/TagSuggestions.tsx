import type { TagDropped, TagHow, TagSuggestion } from './types'

const HOW: Record<TagHow, string> = {
  exact: 'Same tag in another spelling',
  alias: 'Known alias',
  fuzzy: 'Closest existing tag',
  'llm-map': 'Existing tag picked by the model',
  'llm-alias': 'Existing tag picked by the model; the alias waits for review in Settings → Tag vocabulary',
  new: 'New tag',
}

function title(s: TagSuggestion): string {
  const where = s.known ? 'Already used in your library' : s.in_vocab ? 'In your tag vocabulary' : 'New tag'
  const how = s.how && s.how !== 'new' ? `. ${HOW[s.how]}` : ''
  const from = s.from ? ` (model wrote "${s.from}")` : ''
  return `${where}${how}${from}`
}

/** AI-suggested tags as toggle chips; ticked ones get added. New tags (not yet in the
 *  library or the tag vocabulary) are marked, and so is the model's own wording when
 *  it was matched to an existing tag. Candidates the tag mode left out are listed below. */
export default function TagSuggestions({
  suggestions,
  picked,
  onToggle,
  disabled,
  dropped = [],
}: {
  suggestions: TagSuggestion[]
  picked: Set<string>
  onToggle: (tag: string) => void
  disabled?: boolean
  dropped?: TagDropped[]
}) {
  return (
    <>
      {suggestions.length ? (
        <div className="chips tag-suggestions" role="group" aria-label="Suggested tags">
          {suggestions.map((s) => (
            <button
              key={s.tag}
              type="button"
              className={picked.has(s.tag) ? 'chip active' : 'chip'}
              aria-pressed={picked.has(s.tag)}
              disabled={disabled}
              title={title(s)}
              onClick={() => onToggle(s.tag)}
            >
              {s.tag}
              {s.from && <span className="chip-new"> ← {s.from}</span>}
              {!s.known && !s.in_vocab && <span className="chip-new"> new</span>}
              {s.how === 'llm-alias' && <span className="chip-new"> alias?</span>}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted small">No new tags suggested.</p>
      )}
      {dropped.length > 0 && (
        <p className="muted small">
          Left out: {dropped.map((d) => `${d.candidate} (${d.reason})`).join(', ')}
        </p>
      )}
    </>
  )
}

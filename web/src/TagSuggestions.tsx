import type { TagSuggestion } from './types'

/** AI-suggested tags as toggle chips; ticked ones get added. New tags (not yet in the library) are marked. */
export default function TagSuggestions({
  suggestions,
  picked,
  onToggle,
  disabled,
}: {
  suggestions: TagSuggestion[]
  picked: Set<string>
  onToggle: (tag: string) => void
  disabled?: boolean
}) {
  if (!suggestions.length) return <p className="muted small">No new tags suggested.</p>
  return (
    <div className="chips tag-suggestions" role="group" aria-label="Suggested tags">
      {suggestions.map((s) => (
        <button
          key={s.tag}
          type="button"
          className={picked.has(s.tag) ? 'chip active' : 'chip'}
          aria-pressed={picked.has(s.tag)}
          disabled={disabled}
          title={s.known ? 'Already used in your library' : 'New tag'}
          onClick={() => onToggle(s.tag)}
        >
          {s.tag}
          {!s.known && <span className="chip-new"> new</span>}
        </button>
      ))}
    </div>
  )
}

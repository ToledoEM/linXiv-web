import { useId, useState, type InputHTMLAttributes, type KeyboardEvent } from 'react'
import { suggestions as findSuggestions } from './searchHistory'

/** A text input with a past-terms dropdown (desktop ClauseRow suggestions):
 * ↑/↓ move, Enter picks, Escape closes; Enter with nothing highlighted submits as usual. */
export default function SuggestInput({
  value,
  onValueChange,
  enabled,
  ...rest
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> & {
  value: string
  onValueChange: (value: string) => void
  enabled: boolean
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const listId = useId()
  const items = enabled && open ? findSuggestions(value).filter((t) => t !== value.trim()) : []

  const pick = (term: string) => {
    onValueChange(term)
    setOpen(false)
    setActive(-1)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!items.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % items.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      pick(items[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="suggest grow">
      <input
        {...rest}
        value={value}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={items.length > 0}
        aria-controls={listId}
        autoComplete="off"
        onChange={(e) => {
          onValueChange(e.target.value)
          setOpen(true)
          setActive(-1)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {items.length > 0 && (
        <ul className="suggest-list" id={listId} role="listbox">
          {items.map((term, i) => (
            <li
              key={term}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : ''}
              // mousedown, not click: the input's blur would close the list first
              onMouseDown={(e) => {
                e.preventDefault()
                pick(term)
              }}
            >
              {term}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

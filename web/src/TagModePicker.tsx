import { TAG_MODES } from './tagModes'
import type { TagMode } from './types'

/** Overrides of the saved Tag vocabulary settings for one AI tag run; unset = saved. */
export interface TagRunOptions {
  mode?: TagMode
  pdf?: boolean
}

/** Mode and text source for AI tag suggestions (paper page, Library batch). */
export default function TagModePicker({
  value,
  onChange,
  disabled,
}: {
  value: TagRunOptions
  onChange: (next: TagRunOptions) => void
  disabled?: boolean
}) {
  return (
    <>
      <select
        aria-label="AI tag mode"
        disabled={disabled}
        value={value.mode ?? ''}
        onChange={(e) => onChange({ ...value, mode: (e.target.value || undefined) as TagMode | undefined })}
      >
        <option value="">Saved mode</option>
        {TAG_MODES.map((m) => (
          <option key={m.value} value={m.value} title={m.hint}>
            {m.label}
          </option>
        ))}
      </select>
      <select
        aria-label="AI tag text"
        disabled={disabled}
        value={value.pdf === undefined ? '' : value.pdf ? 'pdf' : 'abstract'}
        onChange={(e) =>
          onChange({ ...value, pdf: e.target.value === '' ? undefined : e.target.value === 'pdf' })
        }
      >
        <option value="">Saved text source</option>
        <option value="abstract">Abstract only</option>
        <option value="pdf">Abstract + PDF text</option>
      </select>
    </>
  )
}

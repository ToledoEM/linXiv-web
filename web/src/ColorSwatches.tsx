import { HIGHLIGHT_COLORS } from './pdfAnchor'

/** Highlight color row shared by the reader and the Highlights list (desktop ColorSwatches). */
export default function ColorSwatches({
  value,
  onChange,
  label = 'Highlight color',
}: {
  value?: string
  onChange: (color: string) => void
  label?: string
}) {
  return (
    <div className="swatches hl-swatches">
      {HIGHLIGHT_COLORS.map((c) => (
        <button
          key={c}
          type="button"
          className={`swatch-btn${c === value ? ' selected' : ''}`}
          style={{ background: c, color: c }}
          aria-label={`${label} ${c}`}
          aria-pressed={c === value}
          onClick={() => onChange(c)}
        />
      ))}
    </div>
  )
}

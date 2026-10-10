import { useEffect, useId, useRef, useState, type ReactNode } from 'react'

/** Modal confirmation on the native <dialog>: Esc or a backdrop click cancels.
 *  With `phrase`, the confirm button stays disabled until it is typed exactly. */
export default function ConfirmDialog({
  open,
  title,
  children,
  phrase,
  confirmLabel = 'Confirm',
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  children?: ReactNode
  phrase?: string
  confirmLabel?: string
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [typed, setTyped] = useState('')
  const titleId = useId()

  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) {
      setTyped('')
      d.showModal()
    } else if (!open && d.open) {
      d.close()
    }
  }, [open])

  const ok = !busy && (!phrase || typed === phrase)

  return (
    <dialog
      ref={ref}
      className="confirm-dialog"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault() // the parent decides; `open` closes it
        if (!busy) onCancel()
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel() // backdrop
      }}
    >
      {/* No <form>: the dialog may sit inside a Settings form (nested forms are invalid). */}
      <h3 id={titleId}>{title}</h3>
      {children}
      {phrase && (
        <label className="field">
          <span>
            Type <strong>{phrase}</strong> to confirm
          </span>
          <input
            value={typed}
            autoFocus
            autoComplete="off"
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter') return
              e.preventDefault() // never submit an enclosing form
              if (ok) onConfirm()
            }}
          />
        </label>
      )}
      <div className="actions">
        <button type="button" className="danger" disabled={!ok} onClick={onConfirm}>
          {busy ? 'Working…' : confirmLabel}
        </button>
        <button type="button" className="link" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </dialog>
  )
}

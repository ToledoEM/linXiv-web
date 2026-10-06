import type { KeyboardEvent } from 'react'

// Ctrl-Enter (Windows/Linux) or Cmd-Enter (macOS): "submit this form/editor" (desktop submitShortcut.ts).
export const isSubmitChord = (e: KeyboardEvent) => !e.repeat && (e.metaKey || e.ctrlKey) && !e.altKey && e.key === 'Enter'

/** onKeyDown for a button-driven save surface (editor with no <form>). */
export function submitOnCtrlEnter(onSubmit: () => void) {
  return (e: KeyboardEvent) => {
    if (!isSubmitChord(e)) return
    e.preventDefault() // in a textarea, don't also insert a newline
    onSubmit()
  }
}

/** onKeyDown for a <form>: fires native submit so onSubmit and validation run. */
export function formSubmitOnCtrlEnter(e: KeyboardEvent<HTMLFormElement>) {
  if (!isSubmitChord(e)) return
  e.preventDefault()
  e.currentTarget.requestSubmit()
}

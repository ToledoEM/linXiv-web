// Vitest setup: unmount React trees between tests, and give jsdom the
// <dialog> methods it lacks (showModal/close only toggle `open` here).
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(cleanup)

// Absent in the `node` environment (notesMarkdown.test.ts).
if (typeof HTMLDialogElement !== 'undefined') {
  const proto = HTMLDialogElement.prototype
  proto.showModal ??= function (this: HTMLDialogElement) {
    this.open = true
  }
  proto.close ??= function (this: HTMLDialogElement) {
    this.open = false
  }
}

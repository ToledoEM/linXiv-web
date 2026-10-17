// Guard against leaving the page while a batch run is going: the batch panels drive
// their loops from component state, so unmounting them (navigating away) abandons the
// run. While one is active the browser asks before a reload/close and the sidebar asks
// before an in-app navigation.
//
// React Router's useBlocker needs a data router; the app uses <BrowserRouter>, so the
// in-app side is handled where the links are (App.tsx), not by the router.

import { useEffect, useState } from 'react'

const EVENT = 'lxw-batch-running'
// Several panels can run at once (metadata and tags): count them, don't flip a flag.
let active = 0

function publish(): void {
  window.dispatchEvent(new CustomEvent<boolean>(EVENT, { detail: active > 0 }))
}

export function batchRunning(): boolean {
  return active > 0
}

const beforeUnload = (e: BeforeUnloadEvent) => {
  // The browser shows its own wording; preventDefault is what triggers it.
  e.preventDefault()
}

/** Call with a panel's `running` flag: holds the guard while that run is going. */
export function useBatchGuard(running: boolean): void {
  useEffect(() => {
    if (!running) return
    active += 1
    if (active === 1) window.addEventListener('beforeunload', beforeUnload)
    publish()
    return () => {
      active -= 1
      if (active === 0) window.removeEventListener('beforeunload', beforeUnload)
      publish()
    }
  }, [running])
}

/** Whether any batch run is active (App uses it to confirm sidebar navigation). */
export function useBatchRunning(): boolean {
  const [on, setOn] = useState(batchRunning)
  useEffect(() => {
    // The initial value comes from useState; later changes arrive on the event.
    const handler = (e: Event) => setOn((e as CustomEvent<boolean>).detail)
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
  return on
}

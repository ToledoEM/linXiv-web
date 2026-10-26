import { useState } from 'react'
import { api } from './api'

/** Shared library: copy papers (with PDFs, notes, highlights) into your own library.
 *  Papers already in your library keep what you stored. */
export default function CopyToMine({ ids, onDone }: { ids: string[]; onDone?: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const run = async () => {
    setBusy(true)
    setError('')
    setDone('')
    try {
      const r = await api.copyFromShared(ids)
      const n = r.copied.length
      const parts = [`Copied ${n} paper${n === 1 ? '' : 's'} to your library.`]
      if (r.failed.length) parts.push(`${r.failed.length} not found.`)
      if (r.skipped_pdfs.length)
        parts.push(`${r.skipped_pdfs.length} PDF${r.skipped_pdfs.length === 1 ? '' : 's'} not copied.`)
      setDone(parts.join(' '))
      onDone?.()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button onClick={() => void run()} disabled={busy || !ids.length} title="Copy into your own library">
        {busy ? 'Copying…' : 'Copy to my library'}
      </button>
      {done && <span className="success small">{done}</span>}
      {error && <span className="error small">{error}</span>}
    </>
  )
}

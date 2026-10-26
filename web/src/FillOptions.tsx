import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { FillOptions as Options } from './types'

const GAP_LABEL: Record<string, string> = {
  title: 'Junk title',
  authors: 'No authors',
  date: 'No date',
  abstract: 'No abstract',
  journal: 'No journal',
  doi: 'No DOI',
}
const SOURCE_LABEL: Record<string, string> = {
  arxiv: 'arXiv (arXiv papers, by arXiv id)',
  biorxiv: 'bioRxiv / medRxiv (their DOIs)',
  crossref: 'Crossref (any DOI)',
  pubmed: 'PubMed (any DOI)',
}

/** "Complete metadata of new papers": which gaps count, and which sources are
 *  asked in which order. Each change saves at once. */
export default function FillOptions() {
  const [opts, setOpts] = useState<Options | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .fillOptions()
      .then(setOpts)
      .catch((err) => setError((err as Error).message))
  }, [])

  if (!opts) return error ? <ErrorText error={error} /> : null

  const save = async (gaps: string[], sources: string[]) => {
    setBusy(true)
    setError('')
    try {
      setOpts(await api.setFillOptions(gaps, sources))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const toggleGap = (g: string) =>
    void save(opts.gaps.includes(g) ? opts.gaps.filter((x) => x !== g) : [...opts.gaps, g], opts.sources)
  const toggleSource = (s: string) =>
    void save(opts.gaps, opts.sources.includes(s) ? opts.sources.filter((x) => x !== s) : [...opts.sources, s])
  const move = (i: number, by: -1 | 1) => {
    const next = [...opts.sources]
    ;[next[i], next[i + by]] = [next[i + by], next[i]]
    void save(opts.gaps, next)
  }
  // Ticked sources in their order, then the unticked ones.
  const listed = [...opts.sources, ...opts.all_sources.filter((s) => !opts.sources.includes(s))]

  return (
    <div className="fill-options small">
      <fieldset>
        <legend>A new paper counts as incomplete with</legend>
        {opts.all_gaps.map((g) => {
          const on = opts.gaps.includes(g)
          return (
            <label key={g} className="check">
              <input
                type="checkbox"
                checked={on}
                disabled={busy || (on && opts.gaps.length === 1)}
                onChange={() => toggleGap(g)}
              />
              {GAP_LABEL[g] ?? g}
            </label>
          )
        })}
      </fieldset>
      <fieldset>
        <legend>Look up in, in this order</legend>
        <ol className="plain">
          {listed.map((s) => {
            const i = opts.sources.indexOf(s)
            const on = i >= 0
            return (
              <li key={s}>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={on}
                    disabled={busy || (on && opts.sources.length === 1)}
                    onChange={() => toggleSource(s)}
                  />
                  {SOURCE_LABEL[s] ?? s}
                </label>
                {on && (
                  <>
                    <button
                      type="button"
                      className="link"
                      aria-label={`Move ${s} up`}
                      disabled={busy || i === 0}
                      onClick={() => move(i, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="link"
                      aria-label={`Move ${s} down`}
                      disabled={busy || i === opts.sources.length - 1}
                      onClick={() => move(i, 1)}
                    >
                      ↓
                    </button>
                  </>
                )}
              </li>
            )
          })}
        </ol>
        <p className="muted">
          Each source is asked only when it applies to the paper, and only by its own id, never by title. OpenAlex is not
          offered: linXiv can&apos;t look it up by an exact DOI.
        </p>
      </fieldset>
      <ErrorText error={error} />
    </div>
  )
}

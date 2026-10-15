import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, paperPath } from './api'
import { Authors, ErrorText } from './components'
import { MathText } from './tex'
import type { FeedEntry, FeedResponse } from './types'

// Rows shown from the (up to 200) filtered entries, as on linXiv desktop.
const ENTRY_LIMIT = 25

type Configured = Extract<FeedResponse, { configured: true }>

function FeedRow({ entry, saved, onDismissed }: { entry: FeedEntry; saved: boolean; onDismissed: () => void }) {
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>(saved ? 'saved' : 'idle')
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)
  const [error, setError] = useState('')
  const { arxiv_id: id, version } = entry

  const save = async () => {
    if (!id) return
    setSaveState('saving')
    setError('')
    try {
      await api.fetch(id, 'arxiv')
      setSaveState('saved')
    } catch (err) {
      setSaveState('idle')
      setError(`Save failed: ${(err as Error).message}`)
    }
  }

  const dismiss = async (permanent: boolean) => {
    if (!id || version === null) return
    setBusy(true)
    setError('')
    try {
      await api.dismissFeedEntry(id, version, permanent)
      onDismissed()
    } catch (err) {
      setBusy(false)
      setError(`Dismiss failed: ${(err as Error).message}`)
    }
  }

  const title = <MathText forceInline>{entry.title || entry.link || 'Untitled entry'}</MathText>
  return (
    <li className="feed-row">
      <div className="feed-main">
        {entry.link ? (
          <a href={entry.link} target="_blank" rel="noreferrer">
            {title}
          </a>
        ) : (
          title
        )}
        <Authors authors={entry.authors} max={6} />
        {entry.summary && (
          <p className="feed-summary small">
            <MathText forceInline>{entry.summary}</MathText>
          </p>
        )}
        {entry.published && <div className="muted small mono">{entry.published}</div>}
        <ErrorText error={error} />
      </div>
      {id && (
        <div className="feed-actions">
          {version !== null && (
            <a className="small" href={`https://arxiv.org/pdf/${id}v${version}`} target="_blank" rel="noreferrer">
              PDF ↗
            </a>
          )}
          {saveState === 'saved' ? (
            <Link className="small" to={paperPath(`arxiv:${id}`)}>
              Saved
            </Link>
          ) : (
            <button type="button" onClick={save} disabled={saveState === 'saving'}>
              {saveState === 'saving' ? 'Saving…' : 'Save'}
            </button>
          )}
          {version !== null && (
            <>
              <button
                type="button"
                className="link small"
                title="Dismiss this version"
                disabled={busy}
                onClick={() => dismiss(false)}
              >
                Dismiss
              </button>
              <button
                type="button"
                className={armed ? 'danger armed small' : 'link small'}
                title="Hide every version of this paper"
                disabled={busy}
                onClick={() => (armed ? dismiss(true) : setArmed(true))}
                onBlur={() => setArmed(false)}
              >
                {armed ? 'Never show again' : 'Never'}
              </button>
            </>
          )}
        </div>
      )}
    </li>
  )
}

/** Home RSS/Atom feed (desktop HomePage → FeedSection). Hidden when no feed URL is set. */
export default function HomeFeed() {
  const [feed, setFeed] = useState<Configured | null>(null)
  const [configured, setConfigured] = useState(true)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // `loading` starts set; Refresh sets it again before reloading.
  const load = useCallback(
    (refresh = false) =>
      api
        .feed(refresh)
        .then(
          (r) => {
            if (r.configured) setFeed(r)
            setConfigured(r.configured)
            setError('')
          },
          (err: Error) => setError(err.message),
        )
        .finally(() => setLoading(false)),
    [],
  )

  useEffect(() => {
    void load()
  }, [load])

  if (!configured) return null

  // Dismissed rows leave locally; the server prunes its cached page the same way.
  const drop = (entry: FeedEntry) =>
    setFeed((f) => (f ? { ...f, entries: f.entries.filter((e) => e !== entry) } : f))

  const saved = new Set(feed?.saved_arxiv_ids ?? [])
  const entries = feed?.entries ?? []
  const shown = entries.slice(0, ENTRY_LIMIT)

  return (
    <div className="home-feed">
      <div className="page-head">
        <h3>{feed?.title || 'Home feed'}</h3>
        <button
          type="button"
          className="link small page-head-action"
          disabled={loading}
          onClick={() => {
            setLoading(true)
            void load(true)
          }}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {error ? (
        <div className="card">
          <ErrorText error={error} />
          <p className="muted small">
            The feed URL is set in <Link to="/settings#library">Settings</Link>.
          </p>
        </div>
      ) : !feed ? (
        <p className="card muted center">Loading feed…</p>
      ) : entries.length === 0 ? (
        <p className="card muted center">The feed has no entries.</p>
      ) : (
        <>
          <ul className="card feed-list">
            {shown.map((e, i) => (
              <FeedRow
                key={`${e.arxiv_id ?? e.link}-${e.version ?? i}`}
                entry={e}
                saved={!!e.arxiv_id && saved.has(e.arxiv_id)}
                onDismissed={() => drop(e)}
              />
            ))}
          </ul>
          {entries.length > shown.length && (
            <p className="muted small center">
              Showing {shown.length} of {entries.length} entries
            </p>
          )}
        </>
      )}
    </div>
  )
}

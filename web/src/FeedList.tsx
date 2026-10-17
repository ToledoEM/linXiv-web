// Editor for the Home feeds (Settings → Library). The list is stored as JSON in the
// `web_feeds` setting; `home_feed_url` stays as the first feed for installs that never
// edit the list, and is cleared once the list is saved.

import { useState } from 'react'
import { MAX_FEEDS, parseFeeds, type FeedDraft } from './feeds'

/** Owns the rows while they are edited: a half-typed row has no URL yet, so it
 *  cannot survive a round trip through the serialized setting. */
export default function FeedList({
  stored,
  legacy,
  onChange,
}: {
  stored: string
  legacy: string
  onChange: (next: FeedDraft[]) => void
}) {
  const [feeds, setFeeds] = useState<FeedDraft[]>(() => parseFeeds(stored, legacy))

  const update = (next: FeedDraft[]) => {
    setFeeds(next)
    onChange(next)
  }

  const patch = (i: number, p: Partial<FeedDraft>) => update(feeds.map((f, n) => (n === i ? { ...f, ...p } : f)))

  return (
    <div className="field">
      <span>Feeds</span>
      <ul className="feed-edit-list">
        {feeds.map((f, i) => (
          <li key={i} className="feed-edit-row">
            <input
              aria-label={`Feed ${i + 1} name`}
              placeholder="name"
              maxLength={80}
              value={f.name}
              onChange={(e) => patch(i, { name: e.target.value })}
            />
            <input
              className="grow"
              aria-label={`Feed ${i + 1} URL`}
              type="url"
              pattern="https?://.+"
              maxLength={512}
              placeholder="https://rss.arxiv.org/rss/cs.LG"
              value={f.url}
              onChange={(e) => patch(i, { url: e.target.value.trim() })}
            />
            <label className="small inline-check">
              <input type="checkbox" checked={f.enabled} onChange={(e) => patch(i, { enabled: e.target.checked })} />
              On
            </label>
            <button type="button" className="link" onClick={() => update(feeds.filter((_, n) => n !== i))}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="actions">
        <button
          type="button"
          disabled={feeds.length >= MAX_FEEDS}
          onClick={() => update([...feeds, { name: '', url: '', enabled: true }])}
        >
          Add feed
        </button>
        <span className="muted small">
          RSS or Atom feeds shown on Home, e.g. https://rss.arxiv.org/rss/cs.LG. Up to {MAX_FEEDS}; filter rules below apply to
          all of them.
        </span>
      </div>
    </div>
  )
}

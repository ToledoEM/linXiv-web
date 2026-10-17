// Home feed list stored in the `web_feeds` setting, shared by the Settings editor and
// anything else that needs to read it. Kept out of FeedList.tsx so that file only
// exports a component (react-refresh).

import type { FeedSource } from './types'

export type FeedDraft = { name: string; url: string; enabled: boolean }

export const MAX_FEEDS = 10

/** Feeds from the stored JSON, falling back to the single legacy URL. */
export function parseFeeds(raw: string, legacy: string): FeedDraft[] {
  let list: FeedDraft[] = []
  try {
    const parsed: unknown = raw.trim() ? JSON.parse(raw) : []
    if (Array.isArray(parsed)) {
      list = (parsed as FeedSource[])
        .filter((f) => f && typeof f.url === 'string' && f.url.trim())
        .map((f) => ({ name: (f.name ?? '').trim(), url: f.url!.trim(), enabled: f.enabled !== false }))
    }
  } catch {
    list = []
  }
  if (!list.length && legacy.trim()) list = [{ name: 'Home feed', url: legacy.trim(), enabled: true }]
  return list
}

export const serializeFeeds = (feeds: FeedDraft[]): string =>
  JSON.stringify(
    feeds
      .filter((f) => f.url.trim())
      .map((f) => ({ id: f.url.trim(), name: f.name.trim() || f.url.trim(), url: f.url.trim(), enabled: f.enabled })),
  )

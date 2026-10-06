// Search-term history for autocomplete (desktop core storage/queries/search_history.rs).
// linXiv keeps it in a DB table the CLI cannot reach, so the web app keeps its own
// copy in this browser, with the same rules: exact-term upsert with a use count,
// pruned to `search_history_max` most-recently-used terms; suggestions are a
// case-insensitive prefix match ranked by use count, then recency.

const KEY = 'lxw.searchHistory'
export const DEFAULT_HISTORY_MAX = 200
const SUGGESTION_LIMIT = 10

interface Entry {
  term: string
  count: number
  last: number
}

function load(): Entry[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '[]') as unknown
    return Array.isArray(raw)
      ? raw.filter(
          (e): e is Entry => typeof e?.term === 'string' && typeof e.count === 'number' && typeof e.last === 'number',
        )
      : []
  } catch {
    return []
  }
}

function save(entries: Entry[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(entries))
  } catch {
    // storage unavailable: history lasts for this page load only
  }
}

const rank = (a: Entry, b: Entry) => b.count - a.count || b.last - a.last

/** Record `term` (trimmed; blank is a no-op) and prune to `max` entries. */
export function addTerm(term: string, max = DEFAULT_HISTORY_MAX): void {
  const t = term.trim()
  if (!t) return
  const entries = load()
  const hit = entries.find((e) => e.term === t)
  const now = Date.now()
  if (hit) {
    hit.count += 1
    hit.last = Math.max(now, hit.last + 1)
  } else {
    entries.push({ term: t, count: 1, last: now })
  }
  entries.sort((a, b) => b.last - a.last || b.count - a.count)
  save(entries.slice(0, Math.max(1, max)))
}

/** Up to 10 past terms starting with `prefix` (case-insensitive); blank → []. */
export function suggestions(prefix: string, limit = SUGGESTION_LIMIT): string[] {
  const p = prefix.trim().toLowerCase()
  if (!p) return []
  return load()
    .filter((e) => e.term.toLowerCase().startsWith(p))
    .sort(rank)
    .slice(0, limit)
    .map((e) => e.term)
}

export function historySize(): number {
  return load().length
}

export function clearHistory(): void {
  save([])
}

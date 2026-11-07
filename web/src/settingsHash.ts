/** Settings deep links: `#<group>` or `#<group>/<section>` (e.g. `#server/backup`). */
export function splitSettingsHash(hash: string): { group: string; section: string | null } {
  let raw = hash.replace(/^#/, '')
  try {
    raw = decodeURIComponent(raw)
  } catch {
    // malformed escape: use it as typed
  }
  const [group = '', section = ''] = raw.split('/', 2)
  return { group, section: section || null }
}

/** URL part for a card title: `Contacts & API keys` → `contacts-and-api-keys`. */
export const sectionSlug = (title: string) =>
  title
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

// Author name parsing and sort keys, ported from linXiv desktop v0.6.0
// (src/lib/authorName.ts) so names sort the same way in both apps.
import type { Author } from './types'

// Surname particles that attach to the following token(s): "Ludwig van Beethoven" → "van Beethoven".
const PARTICLES = new Set([
  'van', 'von', 'der', 'den', 'de', 'del', 'della', 'da', 'di', 'du',
  'la', 'le', 'los', 'las', 'st', 'st.', 'mac', 'mc', 'bin', 'al', 'ter', 'ten',
])

// Trailing generational/professional suffixes attach to the last name ("Smith Jr.").
const SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v', 'v.', 'phd', 'phd.', 'md', 'md.'])

export function parseFullName(full: string): { first: string; last: string } {
  const name = full.trim()
  if (!name) return { first: '', last: '' }
  // A comma means "Last, First", taken as written.
  const comma = name.indexOf(',')
  if (comma !== -1) return { last: name.slice(0, comma).trim(), first: name.slice(comma + 1).trim() }

  let tokens = name.split(/\s+/)
  if (tokens.length === 1) return { first: '', last: tokens[0] }
  let suffix = ''
  if (SUFFIXES.has(tokens[tokens.length - 1].toLowerCase())) {
    suffix = tokens[tokens.length - 1]
    tokens = tokens.slice(0, -1)
  }
  if (tokens.length === 1) return { first: '', last: suffix ? `${tokens[0]} ${suffix}` : tokens[0] }
  // Absorb particles leftward, keeping at least one first-name token ("Van Morrison").
  let i = tokens.length - 1
  while (i > 1 && PARTICLES.has(tokens[i - 1].toLowerCase())) i--
  const last = tokens.slice(i).join(' ')
  return { first: tokens.slice(0, i).join(' '), last: suffix ? `${last} ${suffix}` : last }
}

export type NameSortBy = 'full_name' | 'first_name' | 'last_name'

// Stored first/last field, else the parse of full_name, else full_name; lowercased.
export function nameSortKey(a: Author, by: NameSortBy): string {
  const full = a.full_name ?? ''
  if (by === 'full_name') return full.toLowerCase()
  const parsed = parseFullName(full)
  const key = by === 'first_name' ? a.first_name || parsed.first : a.last_name || parsed.last
  return (key || full).toLowerCase()
}

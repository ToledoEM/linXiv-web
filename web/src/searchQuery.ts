// arXiv advanced-query clauses (desktop src/lib/search.ts + QueryBuilder makeClause).

export interface Clause {
  operator: 'AND' | 'OR' | 'AND NOT'
  /** arXiv field prefix; `all` searches every field. */
  field: 'all' | 'ti' | 'au' | 'abs'
  value: string
  uid: string
}

export const OPERATORS: Clause['operator'][] = ['AND', 'OR', 'AND NOT']
export const FIELDS: { value: Clause['field']; label: string }[] = [
  { value: 'all', label: 'All fields' },
  { value: 'ti', label: 'Title' },
  { value: 'au', label: 'Author' },
  { value: 'abs', label: 'Abstract' },
]

let seq = 0
export function makeClause(): Clause {
  seq += 1
  return { operator: 'AND', field: 'all', value: '', uid: `c${seq}-${Date.now()}` }
}

/** `ti:x AND au:y ANDNOT abs:z`; blank clauses are skipped, the first one's operator is unused. */
export function buildArxivQuery(clauses: Clause[]): string {
  return clauses
    .filter((c) => c.value.trim() !== '')
    .map((c, i) => {
      const term = c.field === 'all' ? c.value.trim() : `${c.field}:${c.value.trim()}`
      if (i === 0) return term
      const op = c.operator === 'AND NOT' ? 'ANDNOT' : c.operator
      return `${op} ${term}`
    })
    .join(' ')
}

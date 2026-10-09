import type { Paper } from './types'

/** A paper's title, else its PDF file name, else its id: never an empty link. */
export function paperLabel(p: Pick<Paper, 'title' | 'pdf_file' | 'source_id'>): string {
  return p.title?.trim() || p.pdf_file || p.source_id
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

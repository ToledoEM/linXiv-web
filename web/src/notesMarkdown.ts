// A paper's notes as one Obsidian Markdown file: YAML frontmatter with the
// paper's metadata, then one section per note. Same layout as the server's
// project export (`server/app/notes_md.py`); keep the two in step.

import { validDoi } from './format'
import type { Note, Paper } from './types'

const q = (s: string) => JSON.stringify(s) // a JSON string is a valid YAML double-quoted scalar

const when = (ts: string) => ts.replace('T', ' ').slice(0, 16)

/** Obsidian tags may not contain spaces. */
const obsidianTag = (t: string) => t.trim().replace(/\s+/g, '-')

/** File name without extension: title minus characters Obsidian/filesystems reject. */
export function noteFileName(paper: Pick<Paper, 'title' | 'source_id'>): string {
  const clean = (s: string) =>
    s
      .replace(/[\\/:*?"<>|#^[\]]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 100)
      .trim()
  return clean(paper.title ?? '') || clean(paper.source_id.replace(/[:/]/g, '_')) || 'paper'
}

export function notesMarkdown(
  paper: Pick<Paper, 'title' | 'authors' | 'doi' | 'source_id' | 'published' | 'url' | 'tags'>,
  notes: Note[],
  scopeLabel: (projectId: number | null) => string,
): string {
  const title = paper.title?.trim() || paper.source_id
  const lines = ['---', `title: ${q(title)}`]
  const authors = (paper.authors ?? []).filter((a) => a.trim())
  if (authors.length) lines.push('authors:', ...authors.map((a) => `  - ${q(a)}`))
  const doi = validDoi(paper.doi)
  if (doi) lines.push(`doi: ${q(doi)}`)
  lines.push(`source_id: ${q(paper.source_id)}`)
  if (paper.published) lines.push(`published: ${q(paper.published)}`)
  if (paper.url) lines.push(`url: ${q(paper.url)}`)
  const tags = (paper.tags ?? []).map(obsidianTag).filter(Boolean)
  if (tags.length) lines.push('tags:', ...tags.map((t) => `  - ${q(t)}`))
  lines.push('---', '', `# ${title}`, '')
  for (const n of notes) {
    lines.push(`## ${n.title.trim() || 'Untitled note'}`)
    lines.push(`*${scopeLabel(n.project_id)} · created ${when(n.created_at)} · updated ${when(n.updated_at)}*`, '')
    lines.push(n.content.replace(/\s+$/, ''), '')
  }
  return lines.join('\n')
}

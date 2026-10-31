// @vitest-environment node
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { noteFileName, notesMarkdown } from './notesMarkdown'
import type { Note } from './types'

// Same input as server/tests (test_notes_md_matches_golden): both sides must
// produce the shared golden file byte for byte.
const PAPER = {
  source_id: 'arxiv:2204.12985',
  title: 'Deep: Learning "Fast"',
  authors: ['Ada Lovelace', 'Alan Turing'],
  doi: '10.1000/xyz',
  published: '2022-04-27',
  url: 'https://arxiv.org/pdf/2204.12985v1',
  tags: ['machine learning', 'nlp'],
}

const note = (o: Partial<Note>) => ({ uuid: '', source_fk: 0, ...o }) as Note
const NOTES = [
  note({
    id: 1,
    project_id: null,
    title: 'Key idea',
    content: 'Uses $x^2$ and **bold**.\n\n',
    created_at: '2026-10-01T09:30:00Z',
    updated_at: '2026-10-02T10:00:00Z',
  }),
  note({
    id: 2,
    project_id: 1,
    title: ' ',
    content: 'Second.',
    created_at: '2026-10-03T08:00:00Z',
    updated_at: '2026-10-03T08:00:00Z',
  }),
]

const GOLDEN = new URL('../../server/tests/fixtures/notes-md-golden.md', import.meta.url)

describe('notesMarkdown', () => {
  it('matches the server golden file', () => {
    const text = notesMarkdown(PAPER, NOTES, (pid) => (pid === null ? 'Global' : 'Disc Proj'))
    expect(text).toBe(readFileSync(GOLDEN, 'utf8'))
  })
})

describe('noteFileName', () => {
  it('strips characters file systems and Obsidian reject', () => {
    expect(noteFileName(PAPER)).toBe('Deep Learning Fast')
  })

  it('falls back to the id, then to "paper"', () => {
    expect(noteFileName({ source_id: 'doi:10.1/a', title: '' })).toBe('doi_10.1_a')
    expect(noteFileName({ source_id: '', title: '???' })).toBe('paper')
  })

  it('caps the name at 100 characters', () => {
    expect(noteFileName({ source_id: 'x', title: 'a'.repeat(150) })).toHaveLength(100)
  })
})

// Shapes of `linxiv` CLI JSON (v0.6.0), as passed through by the server.

export type Source = 'arxiv' | 'openalex' | 'crossref'

export interface SearchResult {
  source_id: string
  version?: number
  title: string
  summary?: string
  authors: string[]
  published?: string
  paper_url?: string
  primary_category?: string
  entry_id?: string
}

export interface Paper {
  paper_id: number
  source_id: string
  version: number
  title: string
  summary?: string
  published?: string
  updated?: string
  url?: string | null
  doi?: string | null
  category?: string | null
  categories?: string[]
  journal_ref?: string | null
  comment?: string | null
  authors: string[]
  tags: string[]
  has_pdf: boolean
  pdf_path?: string | null
  source?: string
  /** arXiv TeX source fetched and indexed for full-text search. */
  downloaded_source?: boolean
}

export interface PaperVersions {
  source_id: string
  latest_version: number
  versions: Paper[]
}

export interface SavedPdf {
  source_id: string
  title: string
  version: number
  size_bytes: number
}

export interface Stats {
  paper_count: number
  tag_count: number
  category_count: number
  pdf_count: number
  recent_papers: Paper[]
  [key: string]: unknown
}

export interface UserSettings {
  pdf_save_limit_mb: number
  tex_rendering_enabled: boolean
  ARXIV_MAILTO: string
  CROSSREF_MAILTO: string
  OPENALEX_MAILTO: string
}

export interface SettingsResponse {
  settings: UserSettings
  /** Contact keys set as env vars on the server; those win over stored values. */
  env_overrides: string[]
}

export interface TrashedPaper {
  source_fk: number
  source_id: string
  title: string
  authors: string[]
  published?: string
  deleted_at: string
  pdf_path?: string | null
  had_pdf: boolean
  project_fks: number[]
}

/** linXiv ProjectOut fields, flattened, plus deleted_at. */
export interface TrashedProject {
  id: number
  name: string
  description?: string
  paper_count: number
  deleted_at?: string | null
}

export interface TrashListing {
  papers: TrashedPaper[]
  projects: TrashedProject[]
}

export interface Author {
  author_id: number
  orcid: string | null
  full_name: string | null
  first_name: string | null
  last_name: string | null
  paper_count: number
}

/** `author get`: one row per linked paper version. */
export interface AuthorPaper {
  paper_id: number
  source_id: string
  source_fk: number
  version: number
  title: string | null
}

export interface AuthorDetail extends Author {
  papers: AuthorPaper[]
}

export type AuthorRef = Omit<Author, 'paper_count'>

/** `candidates` share this author's ORCID; `name_candidates` only the exact full name. */
export interface MergeCandidates {
  candidates: AuthorRef[]
  name_candidates: AuthorRef[]
}

export type AuthorUpdate = Partial<Record<'full_name' | 'first_name' | 'last_name' | 'orcid', string>>

/** linXiv ProjectOut (`project list` / `project get`). */
export interface Project {
  id: number
  name: string
  description: string
  color_hex: string | null
  project_tags: string[]
  source_ids: string[]
  paper_count: number
  status: 'active' | 'archived' | 'deleted'
  created_at: string
  updated_at: string
  archived_at: string | null
  share_id: string | null
}

export interface ProjectInput {
  name: string
  description: string
  color_hex: string | null
  project_tags: string[]
}

/** linXiv note (`note list` / `note get`). */
export interface Note {
  id: number
  uuid: string
  source_fk: number
  project_id: number | null
  title: string
  content: string
  created_at: string
  updated_at: string
}

/** Editable fields saved through `paper repair`. */
export interface MetadataInput {
  title: string
  authors: string[]
  published: string
  summary: string
  category: string | null
  doi: string | null
  url: string | null
}

export type LookupSource = 'crossref' | 'arxiv' | 'openalex' | 'pubmed'

/** One metadata match from GET /api/papers/{id}/lookup. */
export interface MetadataCandidate {
  source: LookupSource
  ref: string | null
  title: string | null
  authors: string[]
  published: string | null
  summary: string | null
  category: string | null
  doi: string | null
  url: string | null
}

/** `versions new` / `versions check` entry: a saved arXiv paper with a newer version stored. */
export interface NewVersion {
  source_fk: number
  source_id: string
  title: string
  version: number
}

/** Background job (GET /api/jobs/{id}). */
export interface Job {
  id: number
  kind: string
  state: 'running' | 'done' | 'failed' | 'cancelled'
  total: number
  done: number
  current: string | null
  result: Record<string, number>
  errors: { source_id: string; error: string }[]
  error: string | null
  started_at: number
  finished_at: number | null
  cancel_requested: boolean
}

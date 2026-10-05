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

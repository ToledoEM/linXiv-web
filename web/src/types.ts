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

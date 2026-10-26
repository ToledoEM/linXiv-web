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
  /** The PDF's path inside the PDF folder (server-added; null when elsewhere or none). */
  pdf_file?: string | null
  /** Server-added: the title looks like junk read from the PDF, or unlike the file name. */
  title_suspect?: boolean
  /** Library search: found only via indexed full text or a note. */
  deep_match?: boolean
  source?: string
  /** arXiv TeX source fetched and indexed for full-text search. */
  downloaded_source?: boolean
}

export interface PaperVersions {
  source_id: string
  latest_version: number
  versions: Paper[]
}

export type SavedPdfView = 'all' | 'random' | 'size' | 'untagged'

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
  /** RSS/Atom URL shown on Home; empty = no feed. */
  home_feed_url: string
  /** Extra Home feeds as JSON: [{id, name, url, enabled}]; empty = just home_feed_url. */
  web_feeds: string
  rss_cache_retention_days: number
  /** Record search terms for autocomplete (kept in this browser). */
  search_history_enabled: boolean
  search_history_max: number
  /** Background full-text indexer (shared linXiv setting, off by default). */
  full_text_worker_enabled: boolean
  /** Last layout applied in Settings → PDF folders (read-only here; set by the layout job). */
  web_pdf_folder_layout: PdfLayout
  /** Source preselected in Retrieve metadata; "auto" picks by paper id/DOI. */
  web_lookup_source: DefaultLookupSource
  web_lookup_disabled: string
  /** App log level (Settings → Server & data → Logs). */
  web_log_level: LogLevel
  /** Automatic release check (Settings → About). */
  web_update_check: UpdateMode
  /** Write-only GitHub token (read:packages) for the release check. */
  GHCR_TOKEN: string
  /** Write-only: always "" from the server; send a new key to set it, "" to remove. */
  NCBI_API_KEY: string
  /** AI features master switch (off by default). */
  ai_enabled: boolean
  genai_provider: AiProvider
  genai_model: string
  /** Base URL of the OpenAI-compatible endpoint (generic provider only). */
  genai_base_url: string
  /** Write-only AI keys, like NCBI_API_KEY. */
  GEMINI_API_KEY: string
  OPENAI_API_KEY: string
  ANTHROPIC_API_KEY: string
  GENAI_API_KEY_TAG_GEN: string
  /** linXiv MCP over HTTP at /mcp (off by default). */
  mcp_enabled: boolean
  mcp_profile: McpProfile
}

export type McpProfile = 'read' | 'write' | 'full'

export interface McpStatus {
  enabled: boolean
  profile: McpProfile
  token: { set: boolean; hint: string | null; created: string | null }
  sessions: number
  tool_counts: Record<McpProfile, number>
}

export type AiProvider = 'gemini' | 'openai' | 'anthropic' | 'generic'
export type AiKeyName = 'GEMINI_API_KEY' | 'OPENAI_API_KEY' | 'ANTHROPIC_API_KEY' | 'GENAI_API_KEY_TAG_GEN'

/** `GET /api/tags/counts`: papers per tag (count desc), untagged and total papers. */
export interface TagCounts {
  tags: { tag: string; count: number }[]
  untagged: number
  total: number
}

/** One AI tag suggestion; `known` = already used somewhere in the library. */
export interface TagSuggestion {
  tag: string
  known: boolean
}

/** What one AI function asks the model to return (Settings → AI). */
export interface AiTask {
  id: string
  label: string
  schema: Record<string, unknown>
  example: unknown
}

/** AI summary preview (`POST /api/ai/summary/{id}`); saved by the UI as a note. */
export interface SummaryResult {
  source_id: string
  summary: string
  key_points: string[]
  used_pdf: boolean
  truncated: boolean
}

export interface AiTestResult {
  ok: boolean
  provider: AiProvider
  model: string
  ms: number
}

export type PdfLayout = 'none' | 'year' | 'journal' | 'year/journal' | 'journal/year'

export interface PdfLayoutPreview {
  layout: PdfLayout
  to_move: number
  in_place: number
  missing: number
  conflicts: string[]
  sample: { source_id: string; version: number; from: string; to: string }[]
}

/** One cached feed entry (`feed get`). arxiv_id/version are null for non-arXiv items. */
export interface FeedEntry {
  title: string
  link: string
  authors: string[]
  summary: string
  published: string
  arxiv_id: string | null
  version: number | null
  /** Which configured feed the entry came from (merged pages). */
  feed_id?: string
  feed_name?: string
}

/** A feed configured in Settings; `url` is only sent back for the editor. */
export interface FeedSource {
  id: string
  name: string
  url?: string
  enabled?: boolean
}

export type FeedResponse =
  | { configured: false }
  | {
      configured: true
      url: string
      title: string
      entries: FeedEntry[]
      saved_arxiv_ids: string[]
      feeds: FeedSource[]
      /** Feeds that failed this load; the rest still render. */
      errors: { id: string; name: string; error: string }[]
    }

export interface FeedRule {
  rule_id: number
  field: 'TITLE' | 'SUMMARY' | 'AUTHOR'
  keywords: string
  action: 'DENY' | 'ALLOW'
  enabled: boolean
}

export interface SettingsResponse {
  settings: UserSettings
  /** Contact keys set as env vars on the server; those win over stored values. */
  env_overrides: string[]
  /** NCBI (PubMed) API key status; the key itself is never returned. */
  ncbi_api_key: NcbiKeyStatus
  /** AI provider key statuses; the keys themselves are never returned. */
  ai_keys: Record<AiKeyName, NcbiKeyStatus>
  /** GitHub token for the release check; the token itself is never returned. */
  ghcr_token: NcbiKeyStatus
}

export type UpdateMode = 'off' | 'daily' | 'weekly' | 'monthly'

/** Settings → About release check (GHCR image tags). */
export interface UpdateStatus {
  current: string
  latest: string | null
  update_available: boolean
  checked_at: string | null
  error: string | null
  image: string
  mode: UpdateMode
}

export interface DiskRow {
  label: string
  path: string
  /** Bytes and file count inside the folder (linXiv's own usage). */
  used?: number
  files?: number
  /** Free / total of the folder's filesystem (feeds the Health check). */
  total?: number
  free?: number
  error?: string
}

export interface SystemStatus {
  disk: DiskRow[]
  issues: { level: 'error' | 'warning' | 'info'; message: string }[]
}

export interface NcbiKeyStatus {
  set: boolean
  last4: string | null
  source: 'settings' | 'env' | null
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

/** 'ai' = AI metadata cleanup (POST /api/ai/cleanup), same candidate shape. */
export type LookupSource = 'crossref' | 'arxiv' | 'openalex' | 'pubmed' | 'biorxiv' | 'ai'
export type DefaultLookupSource = 'auto' | Exclude<LookupSource, 'ai'>
export type LogLevel = 'debug' | 'info' | 'warning' | 'error'
export type LogWindow = '1h' | '24h' | '7d' | '30d' | 'all'

export interface LogsResponse {
  /** Newest last. */
  lines: string[]
  /** Older lines in the window were left out (limit). */
  truncated: boolean
  level: LogLevel
  files: { name: string; size: number }[]
}

/** One metadata match from GET /api/papers/{id}/lookup. */
export interface MetadataCandidate {
  /** 'filename' = title and year folder taken from the PDF's file name. */
  source: LookupSource | 'filename'
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

/** Last run of one maintenance operation; `libraries` maps library key to what it did there. */
export interface MaintenanceRun {
  started_at: string
  finished_at: string
  state: 'done' | 'cancelled'
  errors: number
  libraries: Record<string, Record<string, unknown>>
}

export interface MaintenanceOp {
  id: string
  label: string
  description: string
  destructive: boolean
  last: MaintenanceRun | null
  job: Job | null
}

/** GET /api/maintenance: nightly schedule (server local hour) and the operations. */
export interface MaintenanceOverview {
  hour: number
  nightly: string[]
  timezone: string | null
  nightly_on: string | null
  /** Database backups kept per library by the "backup" operation. */
  keep_backups: number
  ops: MaintenanceOp[]
}

/** Database backup kept on the server; `library` is the library key (root, shared, u<id>). */
export interface ServerBackup {
  library: string
  name: string
  size: number
}

/** Last "Check PDF files" result of one library; lists are capped, counts are not. */
export interface PdfCheckReport {
  library: string
  checked_at: string
  pdfs: number
  missing_count: number
  unlinked_count: number
  missing: { source_id: string; version: number; title: string }[]
  unlinked: { file: string; size: number }[]
}

export interface DuplicatePaper {
  source_id: string
  version: number
  title: string
  /** File path inside the PDF folder. */
  file: string
  size: number
}

/** Papers whose saved PDFs are byte-identical (same SHA-256). */
export interface DuplicateGroup {
  sha256: string
  papers: DuplicatePaper[]
}

export interface DuplicatesReport {
  scanned_at: string | null
  groups: DuplicateGroup[]
}

/** `annotation list` row; `anchor` is the raw JSON string (parse with parseAnchor). */
export interface Annotation {
  id: number
  uuid: string
  source_fk: number
  project_id: number | null
  anchor: string
  comment: string
  created_at: string
  updated_at: string
}

/** One line of the activity log (`server/app/activity.py`): no bodies, no values. */
export interface ActivityEvent {
  at: string
  /** Acting username (multi-user mode only). */
  actor?: string
  client: string
  method: string
  route: string
  target: Record<string, string>
  status: number
  fields?: string[]
}

export type Role = 'admin' | 'user'

/** `GET /api/me`. `owner`: the server owner's account (root library, server password). */
export interface Me {
  auth_enabled: boolean
  setup_required: boolean
  authenticated: boolean
  password_source: 'env' | 'stored' | null
  multi_user: boolean
  username: string | null
  role: Role | null
  owner: boolean
}

/** Multi-user account (`server/app/routes/users.py`); never carries a password. */
export interface UserAccount {
  id: number
  username: string
  role: Role
  library: string
  created_at: string
  owner: boolean
}

export interface MultiUserStatus {
  enabled: boolean
  owner_username: string | null
}

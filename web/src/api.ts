import type {
  ActivityEvent,
  AiProvider,
  AiTask,
  AiTestResult,
  Annotation,
  Author,
  AuthorDetail,
  AuthorUpdate,
  DuplicatesReport,
  FeedResponse,
  FeedRule,
  Job,
  LogsResponse,
  LogWindow,
  LookupSource,
  MaintenanceOverview,
  MaintenanceSchedule,
  MaintenanceScheduleInput,
  McpStatus,
  Me,
  MergeCandidates,
  MultiUserStatus,
  MetadataCandidate,
  MetadataInput,
  NewVersion,
  Note,
  Paper,
  PdfLayout,
  PdfCheckReport,
  PdfLayoutPreview,
  PaperVersions,
  Project,
  ProjectInput,
  SavedPdf,
  SavedPdfView,
  ServerBackup,
  SystemStatus,
  UpdateStatus,
  SearchResult,
  SettingsResponse,
  SummaryResult,
  TagCounts,
  TagSuggestion,
  Source,
  Stats,
  TrashListing,
  Role,
  UserAccount,
  UserSettings,
} from './types'
import type { GraphView } from './graph/model'
import { libraryHeaders, withLibrary } from './library'
import type { Anchor } from './pdfAnchor'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function csrfToken(): string | undefined {
  return document.cookie
    .split('; ')
    .find((c) => c.startsWith('lxw_csrf='))
    ?.slice('lxw_csrf='.length)
}

/** Paper ids may contain ':' and '/' (arxiv:hep-th/9901001); keep the slashes. */
export function idPath(sourceId: string): string {
  return sourceId.split('/').map(encodeURIComponent).join('/')
}

/** Browser route of a paper page; ':' is legal in a path, so `doi:10.x/y` reads as typed. */
export function paperPath(sourceId: string): string {
  return `/paper/${idPath(sourceId).replace(/%3A/gi, ':')}`
}

export function pdfUrl(sourceId: string): string {
  return withLibrary(`/api/papers/${idPath(sourceId)}/pdf`)
}

export type ExportFormat = 'lxproj' | 'bibtex' | 'obsidian' | 'zotero' | 'notes-md'

/** Plain GET download link: the browser streams the file with the session cookie. */
export function projectExportUrl(id: number, format: ExportFormat, pdfs = false): string {
  return withLibrary(`/api/projects/${id}/export?format=${format}${pdfs && format === 'lxproj' ? '&pdfs=true' : ''}`)
}

/** App log export for a time window (GET; streamed with the session cookie). */
export const logsExportUrl = (window: LogWindow) =>
  `/api/logs/export?window=${encodeURIComponent(window)}`
export const ACTIVITY_EXPORT_URL = '/api/activity/export'
/** Knowledge Graph as GraphML or a zip of nodes.csv + edges.csv (GET; streamed with the session cookie). */
export const graphExportUrl = (format: 'graphml' | 'csv', excludeSingleAuthors: boolean) =>
  withLibrary(`/api/graph/export${qs({ format, exclude_single_authors: excludeSingleAuthors || undefined })}`)
/** Database snapshot download of the library in view. */
export const backupUrl = () => withLibrary(BACKUP_URL)
export const DIAGNOSTICS_URL = '/api/system/diagnostics'
/** A database backup kept on the server by the "backup" maintenance operation (GET downloads it). */
export const serverBackupUrl = (b: ServerBackup) =>
  `/api/maintenance/backups/${encodeURIComponent(b.library)}/${encodeURIComponent(b.name)}`

/** Tell the activity tray a background job just started (it polls slowly when idle). */
function started<T>(p: Promise<T>): Promise<T> {
  return p.then((job) => {
    window.dispatchEvent(new Event('lxw-job-started'))
    return job
  })
}

/** The diagnostics report (Markdown text, not JSON). */
export async function fetchDiagnostics(): Promise<string> {
  const res = await fetch(DIAGNOSTICS_URL, { credentials: 'same-origin' })
  if (res.status === 401) onUnauthorized()
  if (!res.ok) throw new ApiError(res.status, res.statusText || `HTTP ${res.status}`)
  return res.text()
}

let onUnauthorized: () => void = () => {}
/** Database snapshot download (GET; the browser streams it with the session cookie). */
export const BACKUP_URL = '/api/backup'

export interface BackupImportReport {
  papers: number
  notes: number
  projects: number
  authors: number
  tags: number
  annotations: number
  pdf_refs_cleared: number
}

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(
  method: string,
  url: string,
  body?: unknown,
  onResponse?: (res: Response) => void,
): Promise<T> {
  const headers: Record<string, string> = {}
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET') {
    const token = csrfToken()
    if (token) headers['X-CSRF-Token'] = token
  }
  Object.assign(headers, libraryHeaders(url))
  const res = await fetch(url, { method, headers, body: payload, credentials: 'same-origin' })
  onResponse?.(res)
  if (res.status === 401 && !url.endsWith('/login')) onUnauthorized()
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    const detail = data?.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) // pydantic 422: [{msg: 'Value error, …'}, …]
          ? detail.map((d) => String(d?.msg ?? d).replace(/^Value error, /, '')).join('; ')
          : JSON.stringify(detail ?? res.statusText)
    throw new ApiError(res.status, msg)
  }
  return data as T
}

const qs = (params: Record<string, string | number | boolean | undefined>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** POST that returns a file: the body as a Blob (errors read like `request`). */
async function requestBlob(url: string, body: unknown): Promise<Blob> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...libraryHeaders(url) }
  const token = csrfToken()
  if (token) headers['X-CSRF-Token'] = token
  const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body), credentials: 'same-origin' })
  if (res.status === 401) onUnauthorized()
  if (!res.ok) {
    let msg = res.statusText
    try {
      const detail = (await res.json())?.detail
      msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? msg)
    } catch {
      // not JSON: keep the status text
    }
    throw new ApiError(res.status, msg)
  }
  return res.blob()
}

/** Hand a Blob to the browser as a download. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const api = {
  me: () => request<Me>('GET', '/api/me'),
  changePassword: (current: string, next: string) =>
    request('POST', '/api/password', { current, new: next }),
  revokeOtherSessions: () => request<{ revoked: number }>('POST', '/api/sessions/revoke-others'),
  setup: (password: string) => request('POST', '/api/setup', { password }),
  health: () => request<{ ok: boolean; version: string }>('GET', '/api/health'),
  updateStatus: () => request<UpdateStatus>('GET', '/api/update'),
  checkUpdate: () => request<UpdateStatus>('POST', '/api/update/check'),
  systemStatus: () => request<SystemStatus>('GET', '/api/system/status'),
  /** `username` only in multi-user mode (single-user login is password only). */
  login: (password: string, remember = false, username?: string) =>
    request('POST', '/api/login', username ? { username, password, remember } : { password, remember }),
  logout: () => request('POST', '/api/logout'),
  multiUser: () => request<MultiUserStatus>('GET', '/api/admin/multi-user'),
  setMultiUser: (enabled: boolean, username?: string) =>
    request<MultiUserStatus>('POST', '/api/admin/multi-user', username ? { enabled, username } : { enabled }),
  users: () => request<UserAccount[]>('GET', '/api/users'),
  createUser: (body: { username: string; password: string; role: Role }) =>
    request<UserAccount>('POST', '/api/users', body),
  updateUser: (id: number, body: { username?: string; password?: string; role?: Role }) =>
    request<UserAccount>('PUT', `/api/users/${id}`, body),
  deleteUser: (id: number) => request<{ ok: boolean; library_dir: string }>('DELETE', `/api/users/${id}`),

  search: (q: string, source: Source, max: number) =>
    request<SearchResult[]>('GET', `/api/search${qs({ q, source, max })}`),
  fetch: (id: string, source: Source) =>
    request<Paper>('POST', `/api/papers/${idPath(id)}/fetch${qs({ source })}`),

  /** `onResponse` sees the raw response, e.g. the `X-Deep-Search-Error` header. */
  papers: (
    params: {
    q?: string
    tag?: string
    untagged?: boolean
    fulltext?: boolean
    limit?: number
    offset?: number
    sort?: string
    dir?: 'asc' | 'desc'
    pdf?: 'has' | 'none'
    },
    onResponse?: (res: Response) => void,
  ) => request<Paper[]>('GET', `/api/papers${qs(params)}`, undefined, onResponse),
  paper: (id: string) => request<Paper>('GET', `/api/papers/${idPath(id)}`),
  versions: (id: string) => request<PaperVersions>('GET', `/api/papers/${idPath(id)}/versions`),
  deletePaper: (id: string) => request('DELETE', `/api/papers/${idPath(id)}`),
  saveMetadata: (id: string, body: MetadataInput) =>
    request<Paper>('PUT', `/api/papers/${idPath(id)}/metadata`, body),
  /** `byFileName`: search by the title in the PDF's file name, not the stored DOI/title. */
  lookupMetadata: (id: string, source: LookupSource, byFileName = false) =>
    source === 'ai'
      ? request<{ match: 'ai'; candidates: MetadataCandidate[] }>('POST', `/api/ai/cleanup/${idPath(id)}`)
      : request<{ match: 'doi' | 'arxiv' | 'title' | 'filename'; candidates: MetadataCandidate[] }>(
          'GET',
          `/api/papers/${idPath(id)}/lookup${qs({ source, by: byFileName ? 'filename' : undefined })}`,
        ),

  addTags: (id: string, tags: string[]) =>
    request<{ tags: string[] }>('POST', `/api/papers/${idPath(id)}/tags`, { tags }),
  removeTag: (id: string, tag: string) =>
    request<{ tags: string[] }>('DELETE', `/api/papers/${idPath(id)}/tags${qs({ tag })}`),
  allTags: () => request<string[]>('GET', '/api/tags'),
  tagCounts: () => request<TagCounts>('GET', '/api/tags/counts'),

  downloadPdf: (id: string, url?: string) =>
    request('POST', `/api/papers/${idPath(id)}/pdf`, url ? { url } : {}),
  deletePdf: (id: string) => request('DELETE', `/api/papers/${idPath(id)}/pdf`),
  exportBibtex: (ids: string[]) => requestBlob('/api/export/bibtex', { ids }),
  pdfs: (view?: SavedPdfView, limit?: number) =>
    request<{ pdfs: SavedPdf[]; total?: number }>('GET', `/api/pdfs${qs({ view, limit })}`),
  importPdf: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ source_id: string; title: string }>('POST', '/api/pdfs/import', form)
  },

  add: (input: string) =>
    request<{
      kind: 'arxiv' | 'doi' | 'pdf'
      paper: Partial<Paper> & { source_id: string }
      /** Publisher links only: whether the publisher's PDF was attached. */
      pdf_saved?: boolean
    }>(
      'POST',
      '/api/add',
      { input },
    ),

  trash: () => request<TrashListing>('GET', '/api/trash'),
  restorePaper: (id: string) => request('POST', `/api/trash/papers/${idPath(id)}/restore`),
  purgePaper: (id: string) => request('DELETE', `/api/trash/papers/${idPath(id)}`),
  restoreProject: (id: number) => request('POST', `/api/trash/projects/${id}/restore`),
  purgeProject: (id: number) => request('DELETE', `/api/trash/projects/${id}`),

  importFile: (kind: 'bibtex' | 'zotero', file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ saved_count: number; source_ids: string[] }>('POST', `/api/import/${kind}`, form)
  },

  authors: (hideSingle: boolean) => request<Author[]>('GET', `/api/authors${qs({ hide_single: hideSingle || undefined })}`),
  author: (id: number) => request<AuthorDetail>('GET', `/api/authors/${id}`),
  updateAuthor: (id: number, body: AuthorUpdate) =>
    request<{ updated_author_id: number }>('PATCH', `/api/authors/${id}`, body),
  deleteAuthor: (id: number) => request('DELETE', `/api/authors/${id}`),
  feed: (refresh = false, feed?: string, sample?: number) =>
    request<FeedResponse>(
      'GET',
      `/api/feed${qs({ refresh: refresh || undefined, feed: feed && feed !== 'all' ? feed : undefined, sample })}`,
    ),
  dismissFeedEntry: (arxivId: string, version: number, permanent = false) =>
    request('POST', '/api/feed/dismiss', { arxiv_id: arxivId, version, permanent }),
  feedRules: () => request<{ rules: FeedRule[] }>('GET', '/api/feed/rules'),
  addFeedRule: (rule: Pick<FeedRule, 'field' | 'keywords' | 'action'>) =>
    request<{ rule_id: number }>('POST', '/api/feed/rules', rule),
  deleteFeedRule: (id: number) => request('DELETE', `/api/feed/rules/${id}`),
  importBackup: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<BackupImportReport>('POST', '/api/backup/import', form)
  },
  restoreBackup: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request('POST', '/api/backup/restore', form)
  },
  annotations: (paper: string) => request<Annotation[]>('GET', `/api/annotations${qs({ paper })}`),
  createAnnotation: (body: { source_id: string; anchor: Anchor; comment?: string; project_id?: number | null }) =>
    request<{ id: number }>('POST', '/api/annotations', body),
  /** A color change re-creates the annotation server-side; the result carries the new id. */
  updateAnnotation: (id: number, body: { comment?: string; color?: string; source_id?: string }) =>
    request<{ id: number }>('PATCH', `/api/annotations/${id}`, body),
  deleteAnnotation: (id: number) => request('DELETE', `/api/annotations/${id}`),
  graph: (excludeSingleAuthors: boolean) =>
    request<GraphView>('GET', `/api/graph${qs({ exclude_single_authors: excludeSingleAuthors || undefined })}`),
  previewProjectImport: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{
      project_name: string
      description: string
      paper_count: number
      note_count: number
      annotation_count: number
      has_pdfs: boolean
    }>('POST', '/api/projects/import/preview', form)
  },
  importProject: (file: File, onConflict: 'merge' | 'overwrite') => {
    const form = new FormData()
    form.append('file', file)
    form.append('on_conflict', onConflict)
    return request<{ project_id: number; skipped_pdfs?: string[] }>('POST', '/api/projects/import', form)
  },
  orcidBackfill: () =>
    request<{ checked: number; updated: { author_id: number; full_name: string; doi: string }[]; errored: number }>(
      'POST',
      '/api/orcid/backfill',
    ),
  mergeCandidates: (id: number) => request<MergeCandidates>('GET', `/api/authors/${id}/merge-candidates`),
  mergeAuthors: (id: number, duplicateIds: number[]) =>
    request<{ canonical_id: number; merged_ids: number[] }>('POST', `/api/authors/${id}/merge`, {
      duplicate_ids: duplicateIds,
    }),

  projects: (status: 'active' | 'archived') => request<Project[]>('GET', `/api/projects${qs({ status })}`),
  createProject: (body: ProjectInput) =>
    request<{ id: number; name: string; status: string }>('POST', '/api/projects', body),
  updateProject: (id: number, body: Partial<ProjectInput>) => request<Project>('PATCH', `/api/projects/${id}`, body),
  archiveProject: (id: number) => request('POST', `/api/projects/${id}/archive`),
  unarchiveProject: (id: number) => request('POST', `/api/projects/${id}/restore`),
  deleteProject: (id: number) => request('DELETE', `/api/projects/${id}`),
  project: (id: number) => request<Project>('GET', `/api/projects/${id}`),
  projectPapers: (id: number) => request<Paper[]>('GET', `/api/projects/${id}/papers`),
  /** Multi-user: copy papers (with PDFs, notes, highlights) from the shared library into your own. */
  copyFromShared: (sourceIds: string[]) =>
    request<{ copied: string[]; failed: string[]; skipped_pdfs: string[] }>('POST', '/api/shared/copy', {
      source_ids: sourceIds,
    }),
  addProjectPapers: (id: number, sourceIds: string[]) =>
    request<{ ok: boolean; added: string[]; failed: string[] }>('POST', `/api/projects/${id}/papers`, {
      source_ids: sourceIds,
    }),
  removeProjectPaper: (id: number, sourceId: string) =>
    request('DELETE', `/api/projects/${id}/papers/${idPath(sourceId)}`),

  notes: (params: { paper?: string; project?: number }) => request<Note[]>('GET', `/api/notes${qs(params)}`),
  createNote: (body: { source_id: string; title: string; content: string; project_id: number | null }) =>
    request<Note>('POST', '/api/notes', body),
  updateNote: (id: number, body: { title?: string; content?: string }) =>
    request<Note>('PATCH', `/api/notes/${id}`, body),
  deleteNote: (id: number) => request('DELETE', `/api/notes/${id}`),

  newVersions: () => request<{ new_versions: NewVersion[] }>('GET', '/api/versions/new'),
  checkVersions: () => request<{ checked: number; new_versions: NewVersion[] }>('POST', '/api/versions/check'),
  ackVersion: (id: string) => request('POST', `/api/versions/${idPath(id)}/ack`),

  fetchSource: (id: string, force = false) =>
    request<{ source_id: string; indexed: boolean; chars?: number; reason?: string }>(
      'POST',
      `/api/papers/${idPath(id)}/source`,
      { force },
    ),
  fullTextWorker: () =>
    request<{
      enabled: boolean
      current: string | null
      indexed: number
      skipped: number
      failed: number
      parked: number
      last_error: string | null
    }>('GET', '/api/sources/worker'),
  pdfLayoutPreview: (layout: PdfLayout) =>
    request<PdfLayoutPreview>('GET', `/api/pdfs/layout/preview${qs({ layout })}`),
  startPdfLayout: (layout: PdfLayout) => started(request<Job>('POST', '/api/jobs/pdf-layout', { layout })),
  sourcesPending: () =>
    request<{ pending: number; arxiv_papers: number; pdf_pending: number }>('GET', '/api/sources/pending'),
  indexPdfText: (id: string) =>
    request<{ source_id: string; indexed: boolean; chars?: number; truncated: boolean }>(
      'POST',
      `/api/papers/${idPath(id)}/pdf-text`,
    ),
  startIndexPdfText: () => started(request<Job>('POST', '/api/jobs/index-pdf-text')),
  startIndexSources: (limit: number) =>
    started(request<Job>('POST', '/api/jobs/index-sources', { limit })),
  jobs: (kind?: string) => request<Job[]>('GET', `/api/jobs${qs({ kind })}`),
  job: (id: number) => request<Job>('GET', `/api/jobs/${id}`),
  cancelJob: (id: number) => request<Job>('POST', `/api/jobs/${id}/cancel`),
  duplicates: () => request<DuplicatesReport>('GET', '/api/duplicates'),
  mergeDuplicate: (winner: string, loser: string) =>
    request<DuplicatesReport>('POST', '/api/duplicates/merge', { winner, loser }),
  dismissDuplicates: (sourceIds: string[]) =>
    request<DuplicatesReport>('POST', '/api/duplicates/dismiss', { source_ids: sourceIds }),
  metadataReview: () =>
    request<{ papers: { source_id: string; title: string; missing: string[] }[] }>('GET', '/api/metadata-review'),
  removeMetadataReview: (sourceIds: string[]) =>
    request<{ ok: boolean }>('POST', '/api/metadata-review/remove', { source_ids: sourceIds }),
  maintenance: () => request<MaintenanceOverview>('GET', '/api/maintenance'),
  /** Omitted keep_backups / trash_days keep their stored values. */
  setMaintenanceSchedule: (body: MaintenanceScheduleInput) =>
    request<MaintenanceSchedule>('PUT', '/api/maintenance/schedule', body),
  pdfCheck: () => request<{ libraries: PdfCheckReport[] }>('GET', '/api/maintenance/pdf-check'),
  maintenanceBackups: () =>
    request<{ backups: ServerBackup[] }>('GET', '/api/maintenance/backups'),
  deleteMaintenanceBackup: (b: ServerBackup) => request<{ ok: boolean }>('DELETE', serverBackupUrl(b)),
  runMaintenance: (id: string) => started(request<Job>('POST', `/api/maintenance/${encodeURIComponent(id)}/run`)),

  stats: () => request<Stats>('GET', '/api/stats'),
  storage: () => request<{ storage_mb: number; pdf_dir: string }>('GET', '/api/pdfs/storage'),

  settings: () => request<SettingsResponse>('GET', '/api/settings'),
  logs: (window: LogWindow, limit = 1000) => request<LogsResponse>('GET', `/api/logs${qs({ window, limit })}`),
  clearLogs: () => request<{ ok: boolean }>('DELETE', '/api/logs'),
  activity: (limit = 200) => request<{ events: ActivityEvent[] }>('GET', `/api/activity${qs({ limit })}`),
  clearActivity: (confirm: string) => request<{ ok: boolean }>('DELETE', '/api/activity', { confirm }),
  updateSettings: (patch: Partial<UserSettings>) =>
    request<SettingsResponse>('PATCH', '/api/settings', patch),
  aiModels: () => request<{ provider: AiProvider; models: string[] }>('GET', '/api/ai/models'),
  aiTest: () => request<AiTestResult>('POST', '/api/ai/test'),
  aiSchemas: () => request<AiTask[]>('GET', '/api/ai/schemas'),
  mcpStatus: () => request<McpStatus>('GET', '/api/mcp'),
  mcpCreateToken: () => request<{ token: string; hint: string; created: string }>('POST', '/api/mcp/token'),
  mcpRevokeToken: () => request('DELETE', '/api/mcp/token'),
  summarize: (id: string, pdf: boolean) =>
    request<SummaryResult>('POST', `/api/ai/summary/${idPath(id)}${qs({ pdf: pdf || undefined })}`),
  suggestTags: (id: string) =>
    request<{ source_id: string; suggested: TagSuggestion[] }>('POST', `/api/ai/tags/${idPath(id)}`),
}

import type {
  Author,
  Paper,
  PaperVersions,
  Project,
  ProjectInput,
  SavedPdf,
  SearchResult,
  SettingsResponse,
  Source,
  Stats,
  TrashListing,
  UserSettings,
} from './types'

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

export function pdfUrl(sourceId: string): string {
  return `/api/papers/${idPath(sourceId)}/pdf`
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
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
  const res = await fetch(url, { method, headers, body: payload, credentials: 'same-origin' })
  if (res.status === 401 && !url.endsWith('/login')) onUnauthorized()
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    const detail = data?.detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail ?? res.statusText)
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

export const api = {
  me: () => request<{ auth_enabled: boolean; authenticated: boolean }>('GET', '/api/me'),
  login: (password: string) => request('POST', '/api/login', { password }),
  logout: () => request('POST', '/api/logout'),

  search: (q: string, source: Source, max: number) =>
    request<SearchResult[]>('GET', `/api/search${qs({ q, source, max })}`),
  fetch: (id: string, source: Source) =>
    request<Paper>('POST', `/api/papers/${idPath(id)}/fetch${qs({ source })}`),

  papers: (params: {
    q?: string
    tag?: string
    fulltext?: boolean
    limit?: number
    sort?: string
    dir?: 'asc' | 'desc'
    pdf?: 'has' | 'none'
  }) =>
    request<Paper[]>('GET', `/api/papers${qs(params)}`),
  paper: (id: string) => request<Paper>('GET', `/api/papers/${idPath(id)}`),
  versions: (id: string) => request<PaperVersions>('GET', `/api/papers/${idPath(id)}/versions`),
  deletePaper: (id: string) => request('DELETE', `/api/papers/${idPath(id)}`),

  addTags: (id: string, tags: string[]) =>
    request<{ tags: string[] }>('POST', `/api/papers/${idPath(id)}/tags`, { tags }),
  removeTag: (id: string, tag: string) =>
    request<{ tags: string[] }>('DELETE', `/api/papers/${idPath(id)}/tags${qs({ tag })}`),
  allTags: () => request<string[]>('GET', '/api/tags'),

  downloadPdf: (id: string, url?: string) =>
    request('POST', `/api/papers/${idPath(id)}/pdf`, url ? { url } : {}),
  deletePdf: (id: string) => request('DELETE', `/api/papers/${idPath(id)}/pdf`),
  pdfs: () => request<{ pdfs: SavedPdf[] }>('GET', '/api/pdfs'),
  importPdf: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ source_id: string; title: string }>('POST', '/api/pdfs/import', form)
  },

  add: (input: string) =>
    request<{ kind: 'arxiv' | 'doi' | 'pdf'; paper: Partial<Paper> & { source_id: string } }>(
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

  projects: (status: 'active' | 'archived') => request<Project[]>('GET', `/api/projects${qs({ status })}`),
  createProject: (body: ProjectInput) =>
    request<{ id: number; name: string; status: string }>('POST', '/api/projects', body),
  updateProject: (id: number, body: Partial<ProjectInput>) => request<Project>('PATCH', `/api/projects/${id}`, body),
  archiveProject: (id: number) => request('POST', `/api/projects/${id}/archive`),
  unarchiveProject: (id: number) => request('POST', `/api/projects/${id}/restore`),
  deleteProject: (id: number) => request('DELETE', `/api/projects/${id}`),
  project: (id: number) => request<Project>('GET', `/api/projects/${id}`),
  projectPapers: (id: number) => request<Paper[]>('GET', `/api/projects/${id}/papers`),
  addProjectPapers: (id: number, sourceIds: string[]) =>
    request<{ ok: boolean; added: string[]; failed: string[] }>('POST', `/api/projects/${id}/papers`, {
      source_ids: sourceIds,
    }),
  removeProjectPaper: (id: number, sourceId: string) =>
    request('DELETE', `/api/projects/${id}/papers/${idPath(sourceId)}`),

  stats: () => request<Stats>('GET', '/api/stats'),
  storage: () => request<{ storage_mb: number; pdf_dir: string }>('GET', '/api/pdfs/storage'),

  settings: () => request<SettingsResponse>('GET', '/api/settings'),
  updateSettings: (patch: Partial<UserSettings>) =>
    request<SettingsResponse>('PATCH', '/api/settings', patch),
}

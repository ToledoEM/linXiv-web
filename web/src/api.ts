import type {
  Paper,
  PaperVersions,
  SavedPdf,
  SearchResult,
  SettingsResponse,
  Source,
  Stats,
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

  papers: (params: { q?: string; tag?: string; fulltext?: boolean; limit?: number; sort?: string }) =>
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

  stats: () => request<Stats>('GET', '/api/stats'),
  storage: () => request<{ storage_mb: number; pdf_dir: string }>('GET', '/api/pdfs/storage'),

  settings: () => request<SettingsResponse>('GET', '/api/settings'),
  updateSettings: (patch: Partial<UserSettings>) =>
    request<SettingsResponse>('PATCH', '/api/settings', patch),
}

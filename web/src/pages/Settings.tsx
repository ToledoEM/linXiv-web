import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import AiSettings from '../AiSettings'
import McpSettings from '../McpSettings'
import { setAiEnabled } from '../aiEnabled'
import { api } from '../api'
import Backup from '../Backup'
import DisplayControls from '../DisplayControls'
import { ErrorText } from '../components'
import FeedRules from '../FeedRules'
import FullTextIndex from '../FullTextIndex'
import OrcidBackfill from '../OrcidBackfill'
import PdfLayout from '../PdfLayout'
import ThemePicker from '../ThemePicker'
import VersionMonitor from '../VersionMonitor'
import { clearHistory, historySize } from '../searchHistory'
import { SHORTCUTS } from '../shortcuts'
import { PAGE_OPTIONS, setSidebarPage, useSidebarPages } from '../sidebarPages'
import type { AiKeyName, NcbiKeyStatus, SettingsResponse, UserSettings } from '../types'
import { setTexEnabled } from '../texStore'
import { formSubmitOnCtrlEnter } from '../submitShortcut'

const CONTACTS: { key: 'ARXIV_MAILTO' | 'CROSSREF_MAILTO' | 'OPENALEX_MAILTO'; label: string; hint: string }[] = [
  { key: 'ARXIV_MAILTO', label: 'arXiv', hint: 'Sent in the User-Agent of arXiv requests.' },
  { key: 'CROSSREF_MAILTO', label: 'Crossref', hint: 'Crossref polite pool.' },
  { key: 'OPENALEX_MAILTO', label: 'OpenAlex', hint: 'OpenAlex polite pool.' },
]

// Each card saves on its own: only that card's keys go in its PATCH.
type SectionId = 'contacts' | 'ai' | 'mcp' | 'storage' | 'feed' | 'display' | 'search'
const SECTIONS: Record<SectionId, (keyof UserSettings)[]> = {
  contacts: ['ARXIV_MAILTO', 'CROSSREF_MAILTO', 'OPENALEX_MAILTO', 'NCBI_API_KEY'],
  ai: [
    'ai_enabled',
    'genai_provider',
    'genai_model',
    'genai_base_url',
    'GEMINI_API_KEY',
    'OPENAI_API_KEY',
    'ANTHROPIC_API_KEY',
    'GENAI_API_KEY_TAG_GEN',
  ],
  mcp: ['mcp_enabled', 'mcp_profile'],
  storage: ['pdf_save_limit_mb'],
  feed: ['home_feed_url', 'rss_cache_retention_days'],
  display: ['tex_rendering_enabled'],
  search: ['search_history_enabled', 'search_history_max'],
}

export default function Settings() {
  const [saved, setSaved] = useState<UserSettings | null>(null)
  const [draft, setDraft] = useState<UserSettings | null>(null)
  const [envOverrides, setEnvOverrides] = useState<string[]>([])
  const [ncbi, setNcbi] = useState<NcbiKeyStatus | null>(null)
  const [aiKeys, setAiKeys] = useState<Record<AiKeyName, NcbiKeyStatus> | null>(null)
  const [storageMb, setStorageMb] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState<Partial<Record<SectionId, string>>>({})
  const [errors, setErrors] = useState<Partial<Record<SectionId, string>>>({})
  const [busy, setBusy] = useState<SectionId | null>(null)
  const [historyCount, setHistoryCount] = useState(historySize)
  const pages = useSidebarPages()

  useEffect(() => {
    api
      .settings()
      .then((r) => {
        setSaved(r.settings)
        setDraft(r.settings)
        setEnvOverrides(r.env_overrides)
        setNcbi(r.ncbi_api_key)
        setAiKeys(r.ai_keys)
      })
      .catch((err) => setError((err as Error).message))
    api
      .storage()
      .then((s) => setStorageMb(s.storage_mb))
      .catch(() => setStorageMb(null))
  }, [])

  if (!draft || !saved) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  const set = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    // Functional update: one change may set several keys in a row (AI provider + model).
    setDraft((d) => d && { ...d, [key]: value })
    setStatus({})
  }

  const changed = (id: SectionId) => SECTIONS[id].filter((k) => draft[k] !== saved[k])
  const pick = (from: UserSettings, id: SectionId) => Object.fromEntries(SECTIONS[id].map((k) => [k, from[k]]))

  const apply = (id: SectionId, r: SettingsResponse) => {
    setSaved(r.settings)
    // Keep unsaved edits in the other cards.
    setDraft((d) => d && ({ ...d, ...pick(r.settings, id) } as UserSettings))
    setEnvOverrides(r.env_overrides)
    setNcbi(r.ncbi_api_key)
    setAiKeys(r.ai_keys)
    setAiEnabled(r.settings.ai_enabled)
    setTexEnabled(r.settings.tex_rendering_enabled)
  }

  const run = async (id: SectionId, fn: () => Promise<SettingsResponse>, done: string) => {
    setBusy(id)
    setErrors((e) => ({ ...e, [id]: '' }))
    setStatus({})
    try {
      apply(id, await fn())
      setStatus({ [id]: done })
    } catch (err) {
      setErrors((e) => ({ ...e, [id]: (err as Error).message }))
    } finally {
      setBusy(null)
    }
  }

  const save = (id: SectionId) => (e: FormEvent) => {
    e.preventDefault()
    const keys = changed(id)
    if (!keys.length) return
    run(id, () => api.updateSettings(Object.fromEntries(keys.map((k) => [k, draft[k]]))), 'Saved.')
  }

  const saveBar = (id: SectionId): ReactNode => {
    const dirty = changed(id).length > 0
    return (
      <>
        <div className="actions">
          <button disabled={busy !== null || !dirty}>{busy === id ? 'Saving…' : 'Save'}</button>
          {dirty && (
            <button
              type="button"
              className="link"
              onClick={() => setDraft((d) => d && ({ ...d, ...pick(saved, id) } as UserSettings))}
            >
              Discard changes
            </button>
          )}
          {status[id] && <span className="muted small">{status[id]}</span>}
        </div>
        <ErrorText error={errors[id]} />
      </>
    )
  }

  return (
    <section className="settings">
      <h2>Settings</h2>

      <div className="card settings-section">
        <h3>Appearance</h3>
        <p className="muted small">Theme, mode, zoom and density are stored in this browser.</p>
        <div className="settings-theme">
          <ThemePicker />
        </div>
        <DisplayControls />
      </div>

      <form onSubmit={save('contacts')} onKeyDown={formSubmitOnCtrlEnter}>
        <div className="card settings-section">
          <h3>Contacts &amp; API keys</h3>
          <p className="muted small">Email addresses linXiv sends to metadata services. Leave empty to send none.</p>
          {CONTACTS.map((c) => (
            <label key={c.key} className="field">
              <span>{c.label}</span>
              <input
                type="email"
                value={draft[c.key]}
                placeholder="you@example.org"
                onChange={(e) => set(c.key, e.target.value.trim())}
              />
              <span className="muted small">
                {c.hint}
                {envOverrides.includes(c.key) && (
                  <strong> The server sets {c.key} in its environment, which takes precedence.</strong>
                )}
              </span>
            </label>
          ))}
          <label className="field">
            <span>NCBI API key (PubMed)</span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft.NCBI_API_KEY}
              placeholder={ncbi?.set ? 'Enter a new key to replace it' : 'Paste your NCBI API key'}
              onChange={(e) => set('NCBI_API_KEY', e.target.value.trim())}
            />
            <span className="muted small">
              {ncbi?.source === 'env'
                ? `Set by the server environment (…${ncbi.last4}); it takes precedence.`
                : ncbi?.set
                  ? `Key saved (…${ncbi.last4}).`
                  : 'Not set.'}{' '}
              Raises PubMed lookups from 3 to 10 per second.{' '}
              <a href="https://support.nlm.nih.gov/kbArticle/?pn=KA-05317" target="_blank" rel="noreferrer">
                How to get one
              </a>
            </span>
          </label>
          {ncbi?.source === 'settings' && (
            <div className="actions">
              <button
                type="button"
                className="link danger-link"
                disabled={busy !== null}
                onClick={() => run('contacts', () => api.updateSettings({ NCBI_API_KEY: '' }), 'NCBI API key removed.')}
              >
                Remove NCBI API key
              </button>
            </div>
          )}
          {saveBar('contacts')}
        </div>
      </form>

      <form onSubmit={save('ai')} onKeyDown={formSubmitOnCtrlEnter}>
        <AiSettings
          draft={draft}
          saved={saved}
          keys={aiKeys}
          envOverrides={envOverrides}
          set={set}
          onKeys={setAiKeys}
          footer={saveBar('ai')}
        />
      </form>

      <form onSubmit={save('mcp')} onKeyDown={formSubmitOnCtrlEnter}>
        <McpSettings draft={draft} saved={saved} set={set} footer={saveBar('mcp')} />
      </form>

      <form onSubmit={save('storage')} onKeyDown={formSubmitOnCtrlEnter}>
        <div className="card settings-section">
          <h3>Storage</h3>
          <label className="field">
            <span>Total PDF storage limit (MB)</span>
            <input
              type="number"
              min={1}
              step={1}
              required
              value={draft.pdf_save_limit_mb}
              onChange={(e) => set('pdf_save_limit_mb', Math.trunc(Number(e.target.value)))}
            />
            <span className="muted small">
              Downloads and imports stop once saved PDFs reach this total.
              {storageMb !== null && ` Currently using ${storageMb.toFixed(1)} MB.`}
            </span>
          </label>
          {saveBar('storage')}
        </div>
      </form>

      <form onSubmit={save('feed')} onKeyDown={formSubmitOnCtrlEnter}>
        <div className="card settings-section">
          <h3>Home feed</h3>
          <label className="field">
            <span>Feed URL</span>
            <input
              type="url"
              pattern="https?://.+"
              maxLength={512}
              value={draft.home_feed_url}
              placeholder="https://rss.arxiv.org/rss/cs.LG"
              onChange={(e) => set('home_feed_url', e.target.value.trim())}
            />
            <span className="muted small">
              RSS or Atom feed shown on Home, e.g. https://rss.arxiv.org/rss/cs.LG. Leave empty for no feed.
            </span>
          </label>
          <label className="field">
            <span>Cache retention (days)</span>
            <input
              type="number"
              min={1}
              max={3650}
              step={1}
              required
              value={draft.rss_cache_retention_days}
              onChange={(e) => set('rss_cache_retention_days', Math.trunc(Number(e.target.value)))}
            />
            <span className="muted small">
              Days of feed entries kept locally before pruning; permanently dismissed papers are always kept.
            </span>
          </label>
          {saveBar('feed')}
        </div>
      </form>

      <form onSubmit={save('display')} onKeyDown={formSubmitOnCtrlEnter}>
        <div className="card settings-section">
          <h3>Display</h3>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.tex_rendering_enabled}
              onChange={(e) => set('tex_rendering_enabled', e.target.checked)}
            />
            Render TeX ($…$) in titles and abstracts
          </label>
          {saveBar('display')}
        </div>
      </form>

      <form onSubmit={save('search')} onKeyDown={formSubmitOnCtrlEnter}>
        <div className="card settings-section">
          <h3>Search</h3>
          <label className="check">
            <input
              type="checkbox"
              checked={draft.search_history_enabled}
              onChange={(e) => set('search_history_enabled', e.target.checked)}
            />
            Save search terms for autocomplete suggestions
          </label>
          <label className="field">
            <span>Max history entries</span>
            <input
              type="number"
              min={1}
              max={10000}
              step={1}
              required
              disabled={!draft.search_history_enabled}
              value={draft.search_history_max}
              onChange={(e) => set('search_history_max', Math.trunc(Number(e.target.value)))}
            />
            <span className="muted small">
              Oldest terms are pruned when the limit is reached. Terms are kept in this browser ({historyCount} saved).
            </span>
          </label>
          <div className="actions">
            <button
              type="button"
              className="link"
              disabled={historyCount === 0}
              onClick={() => {
                clearHistory()
                setHistoryCount(0)
              }}
            >
              Clear search history
            </button>
          </div>
          {saveBar('search')}
        </div>
      </form>
      <div className="card settings-section">
        <h3>Sidebar</h3>
        <p className="muted small">
          Choose which pages appear in the sidebar. Home, Library, Projects, Authors and Settings always do. Stored in
          this browser.
        </p>
        <div className="sidebar-toggles">
          {PAGE_OPTIONS.map((o) => (
            <label key={o.key} className="check">
              <input type="checkbox" checked={pages[o.key]} onChange={(e) => setSidebarPage(o.key, e.target.checked)} />
              <span>
                {o.label} <span className="muted small">· {o.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="card settings-section">
        <h3>Keyboard shortcuts</h3>
        <table className="shortcut-table">
          <tbody>
            {SHORTCUTS.map((s) => (
              <tr key={s.id}>
                <td className="nowrap">
                  {s.keys.map((k) => (
                    <kbd key={k}>{k}</kbd>
                  ))}
                </td>
                <td>{s.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <FeedRules />
      <Backup />
      <PdfLayout />
      <VersionMonitor />
      <FullTextIndex />
      <OrcidBackfill />
    </section>
  )
}

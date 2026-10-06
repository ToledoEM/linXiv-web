import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { ErrorText } from '../components'
import FullTextIndex from '../FullTextIndex'
import OrcidBackfill from '../OrcidBackfill'
import ThemePicker from '../ThemePicker'
import VersionMonitor from '../VersionMonitor'
import type { UserSettings } from '../types'
import { setTexEnabled } from '../texStore'

const CONTACTS: { key: 'ARXIV_MAILTO' | 'CROSSREF_MAILTO' | 'OPENALEX_MAILTO'; label: string; hint: string }[] = [
  { key: 'ARXIV_MAILTO', label: 'arXiv', hint: 'Sent in the User-Agent of arXiv requests.' },
  { key: 'CROSSREF_MAILTO', label: 'Crossref', hint: 'Crossref polite pool.' },
  { key: 'OPENALEX_MAILTO', label: 'OpenAlex', hint: 'OpenAlex polite pool.' },
]

export default function Settings() {
  const [saved, setSaved] = useState<UserSettings | null>(null)
  const [draft, setDraft] = useState<UserSettings | null>(null)
  const [envOverrides, setEnvOverrides] = useState<string[]>([])
  const [storageMb, setStorageMb] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .settings()
      .then((r) => {
        setSaved(r.settings)
        setDraft(r.settings)
        setEnvOverrides(r.env_overrides)
      })
      .catch((err) => setError((err as Error).message))
    api
      .storage()
      .then((s) => setStorageMb(s.storage_mb))
      .catch(() => setStorageMb(null))
  }, [])

  if (!draft || !saved) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  const set = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setDraft({ ...draft, [key]: value })
    setStatus('')
  }

  const changes = (Object.keys(draft) as (keyof UserSettings)[]).filter((k) => draft[k] !== saved[k])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const patch = Object.fromEntries(changes.map((k) => [k, draft[k]])) as Partial<UserSettings>
      const r = await api.updateSettings(patch)
      setSaved(r.settings)
      setDraft(r.settings)
      setEnvOverrides(r.env_overrides)
      setTexEnabled(r.settings.tex_rendering_enabled)
      setStatus('Saved.')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="settings">
      <h2>Settings</h2>

      <div className="card settings-section">
        <h3>Appearance</h3>
        <p className="muted small">Theme and mode are stored in this browser.</p>
        <div className="settings-theme">
          <ThemePicker />
        </div>
      </div>

      <form onSubmit={submit}>
        <div className="card settings-section">
          <h3>Contacts</h3>
          <p className="muted small">
            Email addresses linXiv sends to metadata services. Leave empty to send none.
          </p>
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
        </div>

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
        </div>

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
        </div>

        <div className="toolbar">
          <button disabled={busy || changes.length === 0}>{busy ? 'Saving…' : 'Save'}</button>
          {changes.length > 0 && (
            <button type="button" className="link" onClick={() => setDraft(saved)}>
              Discard changes
            </button>
          )}
          <span className="muted">{status}</span>
        </div>
        <ErrorText error={error} />
      </form>
      <VersionMonitor />
      <FullTextIndex />
      <OrcidBackfill />
    </section>
  )
}

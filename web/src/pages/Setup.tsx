import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import AiSettings from '../AiSettings'
import { setAiEnabled } from '../aiEnabled'
import { api } from '../api'
import { ErrorText } from '../components'
import { CONTACTS } from '../contacts'
import PdfLayout from '../PdfLayout'
import ThemePicker from '../ThemePicker'
import type { AiKeyName, NcbiKeyStatus, SettingsResponse, UserSettings } from '../types'

const STEPS = ['Admin password', 'Contacts & API keys', 'Appearance', 'AI', 'Home feed & PDF folders']

/** First-run setup: the first visitor creates the admin password, then optional configuration steps. */
export default function Setup({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0)
  const [saved, setSaved] = useState<UserSettings | null>(null)
  const [draft, setDraft] = useState<UserSettings | null>(null)
  const [envOverrides, setEnvOverrides] = useState<string[]>([])
  const [aiKeys, setAiKeys] = useState<Record<AiKeyName, NcbiKeyStatus> | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = (r: SettingsResponse) => {
    setSaved(r.settings)
    setDraft(r.settings)
    setEnvOverrides(r.env_overrides)
    setAiKeys(r.ai_keys)
    setAiEnabled(r.settings.ai_enabled)
  }

  // Logged in once the password exists: load the settings the later steps edit.
  useEffect(() => {
    if (step === 0 || saved) return
    api
      .settings()
      .then((r) => {
        setSaved(r.settings)
        setDraft(r.settings)
        setEnvOverrides(r.env_overrides)
        setAiKeys(r.ai_keys)
      })
      .catch((err) => setError((err as Error).message))
  }, [step, saved])

  const set = <K extends keyof UserSettings>(key: K, value: UserSettings[K]) =>
    setDraft((d) => d && { ...d, [key]: value })

  const next = () => {
    setError('')
    if (step === STEPS.length - 1) onDone()
    else setStep(step + 1)
  }

  // Saves whatever this step changed, then moves on.
  const saveAndNext = async (e: FormEvent) => {
    e.preventDefault()
    if (!draft || !saved) return next()
    const patch = Object.fromEntries(
      (Object.keys(draft) as (keyof UserSettings)[]).filter((k) => draft[k] !== saved[k]).map((k) => [k, draft[k]]),
    )
    if (!Object.keys(patch).length) return next()
    setBusy(true)
    setError('')
    try {
      load(await api.updateSettings(patch))
      next()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const nav = (
    <div className="actions">
      <button disabled={busy}>{step === STEPS.length - 1 ? 'Save & finish' : 'Save & continue'}</button>
      <button
        type="button"
        className="link"
        disabled={busy}
        onClick={() => {
          if (saved) setDraft(saved)
          next()
        }}
      >
        {step === STEPS.length - 1 ? 'Skip & finish' : 'Skip'}
      </button>
    </div>
  )

  let body: ReactNode
  if (step === 0) {
    body = <AdminPassword onCreated={next} />
  } else if (!draft || !saved) {
    body = error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>
  } else if (step === 1) {
    body = (
      <form onSubmit={saveAndNext} className="card settings-section">
        <p className="muted small">
          Email addresses linXiv sends to metadata services, and a PubMed key. All optional; Settings → AI &amp; sources
          has them too.
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
            <span className="muted small">{c.hint}</span>
          </label>
        ))}
        <label className="field">
          <span>NCBI API key (PubMed)</span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={draft.NCBI_API_KEY}
            placeholder="Paste your NCBI API key"
            onChange={(e) => set('NCBI_API_KEY', e.target.value.trim())}
          />
          <span className="muted small">Raises PubMed lookups from 3 to 10 per second.</span>
        </label>
        <ErrorText error={error} />
        {nav}
      </form>
    )
  } else if (step === 2) {
    body = (
      <form onSubmit={saveAndNext} className="card settings-section">
        <p className="muted small">
          Theme and light/dark mode, stored in this browser. Settings → Appearance has more.
        </p>
        <div className="settings-theme">
          <ThemePicker />
        </div>
        {nav}
      </form>
    )
  } else if (step === 3) {
    body = (
      <form onSubmit={saveAndNext}>
        <AiSettings
          draft={draft}
          saved={saved}
          keys={aiKeys}
          envOverrides={envOverrides}
          set={set}
          onKeys={setAiKeys}
          footer={
            <>
              <ErrorText error={error} />
              {nav}
            </>
          }
        />
      </form>
    )
  } else {
    body = (
      <>
        <PdfLayout />
        <form onSubmit={saveAndNext} className="card settings-section">
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
            <span className="muted small">RSS or Atom feed shown on Home. Leave empty for no feed.</span>
          </label>
          <ErrorText error={error} />
          {nav}
        </form>
      </>
    )
  }

  return (
    <div className="setup">
      <div className="setup-head">
        <h1>
          linXiv<span className="brand-web">-web</span>
        </h1>
        <p className="muted">
          First-run setup · step {step + 1} of {STEPS.length}: <strong>{STEPS[step]}</strong>
        </p>
      </div>
      <div className="setup-body">{body}</div>
    </div>
  )
}

function AdminPassword({ onCreated }: { onCreated: () => void }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (password !== confirm) return setError('The passwords do not match.')
    setBusy(true)
    setError('')
    try {
      await api.setup(password)
      onCreated()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="card settings-section">
      <p className="muted small">
        No password is set yet. Choose the admin password for this linXiv-web server; you will be logged in right away.
      </p>
      <label className="field">
        <span>Password</span>
        <input
          type="password"
          autoFocus
          autoComplete="new-password"
          minLength={8}
          maxLength={256}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <span className="muted small">At least 8 characters.</span>
      </label>
      <label className="field">
        <span>Confirm password</span>
        <input
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </label>
      <ErrorText error={error} />
      <div className="actions">
        <button disabled={busy || password.length < 8 || !confirm}>{busy ? 'Creating…' : 'Create password'}</button>
      </div>
    </form>
  )
}

import { useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { AiKeyName, AiProvider, AiTask, AiTestResult, NcbiKeyStatus, UserSettings } from './types'

const PROVIDERS: { value: AiProvider; label: string; key: AiKeyName; help: string }[] = [
  { value: 'gemini', label: 'Gemini', key: 'GEMINI_API_KEY', help: 'https://aistudio.google.com/apikey' },
  { value: 'openai', label: 'OpenAI', key: 'OPENAI_API_KEY', help: 'https://platform.openai.com/api-keys' },
  {
    value: 'anthropic',
    label: 'Anthropic',
    key: 'ANTHROPIC_API_KEY',
    help: 'https://console.anthropic.com/settings/keys',
  },
  { value: 'generic', label: 'OpenAI-compatible endpoint', key: 'GENAI_API_KEY_TAG_GEN', help: '' },
]

// Settings that change which provider/model/key the server uses.
const AI_FIELDS: (keyof UserSettings)[] = [
  'ai_enabled',
  'genai_provider',
  'genai_model',
  'genai_base_url',
  ...PROVIDERS.map((p) => p.key),
]

/** Settings → AI: opt-in switch, provider, key, model list and a connection test. Part of the Settings form. */
export default function AiSettings({
  draft,
  saved,
  keys,
  envOverrides,
  set,
  onKeys,
  footer,
}: {
  draft: UserSettings
  saved: UserSettings
  keys: Record<AiKeyName, NcbiKeyStatus> | null
  envOverrides: string[]
  set: <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => void
  onKeys: (keys: Record<AiKeyName, NcbiKeyStatus>) => void
  /** Save / discard controls for this card. */
  footer?: ReactNode
}) {
  const [models, setModels] = useState<string[] | null>(null)
  const [test, setTest] = useState<AiTestResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [tasks, setTasks] = useState<AiTask[] | null>(null)

  useEffect(() => {
    api
      .aiSchemas()
      .then(setTasks)
      .catch(() => setTasks(null))
  }, [])

  const provider = PROVIDERS.find((p) => p.value === draft.genai_provider) ?? PROVIDERS[0]
  const status = keys?.[provider.key]
  const unsaved = AI_FIELDS.some((k) => draft[k] !== saved[k])
  const canCall = saved.ai_enabled && !unsaved && !busy

  const call = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError('')
    setNote('')
    try {
      await fn()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const modelOptions = [...new Set([...(draft.genai_model ? [draft.genai_model] : []), ...(models ?? [])])]

  return (
    <div className="card settings-section">
      <h3>AI</h3>
      <label className="check">
        <input type="checkbox" checked={draft.ai_enabled} onChange={(e) => set('ai_enabled', e.target.checked)} />
        Enable AI features (tag suggestions, summaries, metadata cleanup)
      </label>
      <p className="muted small">
        Off by default. When on, the titles, abstracts and text of the papers you run an AI action on are sent to the
        provider below. Nothing is sent until you ask.
      </p>
      {draft.ai_enabled && (
        <>
          <label className="field">
            <span>Provider</span>
            <select
              value={provider.value}
              onChange={(e) => {
                set('genai_provider', e.target.value as AiProvider)
                set('genai_model', '')
                setModels(null)
                setTest(null)
              }}
            >
              {PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          {provider.value === 'generic' && (
            <label className="field">
              <span>Base URL</span>
              <input
                type="url"
                pattern="https?://.+"
                maxLength={512}
                value={draft.genai_base_url}
                placeholder="http://localhost:11434/v1"
                onChange={(e) => set('genai_base_url', e.target.value.trim())}
              />
              <span className="muted small">
                Any server with an OpenAI-style <span className="mono">/chat/completions</span> and{' '}
                <span className="mono">/models</span>: Ollama, LM Studio, vLLM, OpenRouter…
              </span>
            </label>
          )}
          <label className="field">
            <span>
              {provider.label} API key{provider.value === 'generic' && ' (optional)'}
            </span>
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft[provider.key]}
              placeholder={status?.set ? 'Enter a new key to replace it' : 'Paste your API key'}
              onChange={(e) => set(provider.key, e.target.value.trim())}
            />
            <span className="muted small">
              {status?.source === 'env' || envOverrides.includes(provider.key)
                ? `Set by the server environment (…${status?.last4 ?? ''}); it takes precedence.`
                : status?.set
                  ? `Key saved (…${status.last4}).`
                  : 'Not set.'}{' '}
              {provider.help && (
                <a href={provider.help} target="_blank" rel="noreferrer">
                  Get a key
                </a>
              )}
            </span>
          </label>
          {status?.source === 'settings' && (
            <div className="actions">
              <button
                type="button"
                className="link danger-link"
                disabled={busy}
                onClick={() =>
                  call(async () => {
                    const r = await api.updateSettings({ [provider.key]: '' })
                    onKeys(r.ai_keys)
                    setNote(`${provider.label} API key removed.`)
                  })
                }
              >
                Remove {provider.label} API key
              </button>
            </div>
          )}
          <label className="field">
            <span>Model</span>
            <span className="actions-inline">
              <select
                value={draft.genai_model}
                onChange={(e) => {
                  set('genai_model', e.target.value)
                  setTest(null)
                }}
              >
                <option value="">{models ? 'Choose a model…' : 'Load models to choose…'}</option>
                {modelOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={!canCall}
                onClick={() =>
                  call(async () => {
                    const r = await api.aiModels()
                    setModels(r.models)
                    if (!r.models.length) setNote('The provider returned no models.')
                  })
                }
              >
                {busy && !models ? 'Loading…' : 'Load models'}
              </button>
            </span>
          </label>
          <div className="actions">
            <button
              type="button"
              disabled={!canCall || !saved.genai_model}
              onClick={() =>
                call(async () => {
                  setTest(null)
                  setTest(await api.aiTest())
                })
              }
            >
              Test connection
            </button>
            {test && (
              <span className={test.ok ? 'success small' : 'muted small'}>
                {test.ok ? 'Connected' : 'Reply received, but not the expected answer'} · {test.model} · {test.ms} ms
              </span>
            )}
            {unsaved && <span className="muted small">Save to load models or test.</span>}
            {note && <span className="muted small">{note}</span>}
          </div>
          <ErrorText error={error} />
          {tasks && (
            <details className="ai-schemas">
              <summary>Output format the model must return</summary>
              <p className="muted small">
                Each AI function puts this JSON Schema and a valid example reply in its prompt, so the model answers in
                that shape.{' '}
                <a href="https://json-schema.org/learn/miscellaneous-examples" target="_blank" rel="noreferrer">
                  JSON Schema examples
                </a>
              </p>
              {tasks.map((t) => (
                <div key={t.id} className="ai-schema">
                  <strong className="small">{t.label}</strong>
                  <span className="muted small">JSON Schema</span>
                  <pre className="mono small">{JSON.stringify(t.schema, null, 2)}</pre>
                  <span className="muted small">Example reply</span>
                  <pre className="mono small">{JSON.stringify(t.example, null, 2)}</pre>
                </div>
              ))}
            </details>
          )}
        </>
      )}
      {footer}
    </div>
  )
}

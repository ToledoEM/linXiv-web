import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { McpProfile, McpStatus, UserSettings } from './types'

const PROFILES: { value: McpProfile; label: string; hint: string }[] = [
  { value: 'read', label: 'Read only', hint: 'Search, read papers, notes, projects, tags, annotations.' },
  {
    value: 'write',
    label: 'Read + edit library',
    hint: 'Also add papers, notes, tags, projects, highlights; soft-delete (to the trash).',
  },
  {
    value: 'full',
    label: 'Full',
    hint: 'Also permanent changes: hard deletes, merging papers or authors, overwriting metadata.',
  },
]

/** Copyable command / config block; the clipboard needs a secure context, so the text stays selectable. */
function Snippet({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="mcp-snippet">
      <pre className="mono small">{text}</pre>
      <button
        type="button"
        className="link"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(text)
            setCopied(true)
          } catch {
            setCopied(false)
          }
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

/** Settings → MCP: serve linXiv's MCP tools at /mcp for Claude Code / Codex. Part of the Settings form. */
export default function McpSettings({
  draft,
  saved,
  set,
  footer,
}: {
  draft: UserSettings
  saved: UserSettings
  set: <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => void
  footer?: ReactNode
}) {
  const [status, setStatus] = useState<McpStatus | null>(null)
  const [token, setToken] = useState('')
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(
    () =>
      api
        .mcpStatus()
        .then(setStatus)
        .catch((err) => setError((err as Error).message)),
    [],
  )

  useEffect(() => {
    load()
  }, [load, saved.mcp_enabled, saved.mcp_profile])

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const url = `${window.location.origin}/mcp`
  const shown = token || '<token>'

  return (
    <div className="card settings-section">
      <h3>MCP server (Claude Code / Codex)</h3>
      <label className="check">
        <input type="checkbox" checked={draft.mcp_enabled} onChange={(e) => set('mcp_enabled', e.target.checked)} />
        Serve linXiv&apos;s MCP tools at <span className="mono">/mcp</span>
      </label>
      <p className="muted small">
        Off by default. Lets an AI agent with the token below search and work on this library. Settings, backup, restore
        and server-file import/export tools are never exposed.
      </p>
      <label className="field">
        <span>Tools the agent gets</span>
        <select value={draft.mcp_profile} onChange={(e) => set('mcp_profile', e.target.value as McpProfile)}>
          {PROFILES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
              {status ? ` (${status.tool_counts[p.value]} tools)` : ''}
            </option>
          ))}
        </select>
        <span className="muted small">{PROFILES.find((p) => p.value === draft.mcp_profile)?.hint}</span>
      </label>

      <div className="field">
        <span>Access token</span>
        <span className="muted small">
          {status?.token.set
            ? `Token set (…${status.token.hint}, created ${status.token.created?.slice(0, 10)}).`
            : 'No token yet: the endpoint refuses every request.'}
          {status && saved.mcp_enabled && ` ${status.sessions} open session${status.sessions === 1 ? '' : 's'}.`}
        </span>
        <div className="actions">
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                setToken((await api.mcpCreateToken()).token)
              })
            }
          >
            {status?.token.set ? 'Replace token' : 'Create token'}
          </button>
          {status?.token.set && (
            <button
              type="button"
              className={armed ? 'danger armed' : 'link danger-link'}
              disabled={busy}
              onBlur={() => setArmed(false)}
              onClick={() => {
                if (!armed) return setArmed(true)
                setArmed(false)
                run(async () => {
                  await api.mcpRevokeToken()
                  setToken('')
                })
              }}
            >
              {armed ? 'Revoke now?' : 'Revoke token'}
            </button>
          )}
        </div>
        {token && (
          <p className="success small">
            Copy the token now: it is shown only once. Replacing or revoking it disconnects open sessions.
          </p>
        )}
      </div>

      {(token || status?.token.set) && (
        <details className="mcp-setup" open={!!token}>
          <summary>Connect Claude Code or Codex</summary>
          <span className="muted small">Claude Code:</span>
          <Snippet text={`claude mcp add --transport http linxiv ${url} --header "Authorization: Bearer ${shown}"`} />
          <span className="muted small">Codex (token from an environment variable):</span>
          <Snippet
            text={`export LINXIV_MCP_TOKEN=${shown}\ncodex mcp add linxiv --url ${url} --bearer-token-env-var LINXIV_MCP_TOKEN`}
          />
          <span className="muted small">
            or in <span className="mono">~/.codex/config.toml</span>:
          </span>
          <Snippet text={`[mcp_servers.linxiv]\nurl = "${url}"\nbearer_token_env_var = "LINXIV_MCP_TOKEN"`} />
          {!token && <span className="muted small">Replace the token to see it in these commands.</span>}
          {!saved.mcp_enabled && <span className="muted small">Turn the server on and save first.</span>}
        </details>
      )}
      <ErrorText error={error} />
      {footer}
    </div>
  )
}

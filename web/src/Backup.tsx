import { useState } from 'react'
import { api, backupUrl, settingsExportUrl } from './api'
import ConfirmDialog from './ConfirmDialog'
import type { SettingsResponse } from './types'

type Msg = { ok: boolean; text: string } | null
const ACCEPT = '.db,.sqlite,.sqlite3,application/vnd.sqlite3,application/x-sqlite3'

function Status({ msg }: { msg: Msg }) {
  return msg ? <p className={msg.ok ? 'success' : 'error'}>{msg.text}</p> : null
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Database backup, import and restore (desktop Settings → StorageSection), plus
 *  settings export / import. */
export default function Backup({ onSettingsImported }: { onSettingsImported: (r: SettingsResponse) => void }) {
  const [importFile, setImportFile] = useState<File | null>(null)
  const [restoreFile, setRestoreFile] = useState<File | null>(null)
  const [settingsFile, setSettingsFile] = useState<File | null>(null)
  const [importKey, setImportKey] = useState(0)
  const [restoreKey, setRestoreKey] = useState(0)
  const [settingsKey, setSettingsKey] = useState(0)
  const [busy, setBusy] = useState<'' | 'import' | 'restore' | 'settings'>('')
  const [settingsMsg, setSettingsMsg] = useState<Msg>(null)

  const runSettingsImport = async () => {
    if (!settingsFile) return
    setBusy('settings')
    setSettingsMsg(null)
    try {
      let parsed: unknown
      try {
        parsed = JSON.parse(await settingsFile.text())
      } catch {
        throw new Error('not a JSON file')
      }
      const r = await api.importSettings(parsed)
      onSettingsImported(r)
      setSettingsMsg({ ok: true, text: 'Settings imported.' })
      setSettingsFile(null)
      setSettingsKey((k) => k + 1)
    } catch (err) {
      setSettingsMsg({ ok: false, text: `Import failed: ${(err as Error).message}` })
    } finally {
      setBusy('')
    }
  }
  const [armed, setArmed] = useState(false)
  const [importMsg, setImportMsg] = useState<Msg>(null)
  const [restoreMsg, setRestoreMsg] = useState<Msg>(null)

  const runImport = async () => {
    if (!importFile) return
    setBusy('import')
    setImportMsg(null)
    try {
      const r = await api.importBackup(importFile)
      setImportMsg({
        ok: true,
        text: `Imported ${plural(r.papers, 'paper')}, ${plural(r.notes, 'note')}, ${plural(r.projects, 'project')}.`,
      })
      setImportFile(null)
      setImportKey((k) => k + 1)
    } catch (err) {
      setImportMsg({ ok: false, text: `Import failed: ${(err as Error).message}` })
    } finally {
      setBusy('')
    }
  }

  const runRestore = async () => {
    if (!restoreFile) return
    setArmed(false)
    setBusy('restore')
    setRestoreMsg(null)
    try {
      await api.restoreBackup(restoreFile)
      setRestoreMsg({
        ok: true,
        text: 'Library restored. The previous database was kept on the server as papers.pre-restore.',
      })
      setRestoreFile(null)
      setRestoreKey((k) => k + 1)
    } catch (err) {
      setRestoreMsg({ ok: false, text: `Restore failed: ${(err as Error).message}` })
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="card settings-section">
      <h3>Backup</h3>
      <p className="muted small">
        Backups hold the database: papers, metadata, tags, projects, notes and authors. Saved PDF files are not included.
      </p>

      <div className="field">
        <span>Back up database</span>
        <div className="actions">
          <a className="button" href={backupUrl()} download>
            Download backup
          </a>
        </div>
        <span className="muted small">A consistent snapshot of the library database (.db).</span>
      </div>

      <div className="field">
        <span>Import from backup</span>
        <div className="actions">
          <input
            key={importKey}
            type="file"
            accept={ACCEPT}
            aria-label="Backup file to import"
            onChange={(e) => {
              setImportFile(e.target.files?.[0] ?? null)
              setImportMsg(null)
            }}
          />
          <button type="button" disabled={!importFile || busy !== ''} onClick={runImport}>
            {busy === 'import' ? 'Importing…' : 'Import'}
          </button>
        </div>
        <span className="muted small">
          Merges the backup's papers, notes and projects into your library without replacing anything.
        </span>
        <Status msg={importMsg} />
      </div>

      <div className="field">
        <span>Restore database</span>
        <div className="actions">
          <input
            key={restoreKey}
            type="file"
            accept={ACCEPT}
            aria-label="Backup file to restore"
            onChange={(e) => {
              setRestoreFile(e.target.files?.[0] ?? null)
              setRestoreMsg(null)
              setArmed(false)
            }}
          />
          <button
            type="button"
            className="danger"
            disabled={!restoreFile || busy !== ''}
            onClick={() => setArmed(true)}
          >
            {busy === 'restore' ? 'Restoring…' : 'Restore'}
          </button>
        </div>
        <ConfirmDialog
          open={armed}
          title="Replace the whole library?"
          phrase="replace library"
          confirmLabel="Replace library"
          onConfirm={() => void runRestore()}
          onCancel={() => setArmed(false)}
        >
          <p>
            Every paper, note and project is replaced by <span className="mono">{restoreFile?.name}</span>. The current
            database is kept on the server as papers.pre-restore.
          </p>
        </ConfirmDialog>
        <span className="muted small">
          Replaces the whole library with the backup. The current database is kept on the server as papers.pre-restore.
        </span>
        <Status msg={restoreMsg} />
      </div>

      <div className="field">
        <span>Settings</span>
        <div className="actions">
          <a className="button" href={settingsExportUrl()} download>
            Download settings
          </a>
          <input
            key={settingsKey}
            type="file"
            accept=".json,application/json"
            aria-label="Settings file to import"
            onChange={(e) => {
              setSettingsFile(e.target.files?.[0] ?? null)
              setSettingsMsg(null)
            }}
          />
          <button type="button" disabled={!settingsFile || busy !== ''} onClick={runSettingsImport}>
            {busy === 'settings' ? 'Importing…' : 'Import settings'}
          </button>
        </div>
        <span className="muted small">
          Every setting a Save changes, as a JSON file. API keys and tokens are left out and stay as they are on import.
        </span>
        <Status msg={settingsMsg} />
      </div>
    </div>
  )
}

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import Backup from './Backup'
import type { SettingsResponse } from './types'

const choose = (text: string) => {
  const file = new File([text], 'settings.json', { type: 'application/json' })
  fireEvent.change(screen.getByLabelText('Settings file to import'), { target: { files: [file] } })
}

describe('Backup settings import', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends the parsed file and hands back the result', async () => {
    const reply = { settings: { web_lookup_source: 'pubmed' } } as unknown as SettingsResponse
    const send = vi.spyOn(api, 'importSettings').mockResolvedValue(reply)
    const done = vi.fn()
    render(<Backup onSettingsImported={done} />)
    expect(screen.getByRole('link', { name: 'Download settings' }).getAttribute('href')).toBe('/api/settings/export')
    choose('{"linxiv_web_settings": 1, "settings": {"web_lookup_source": "pubmed"}}')
    fireEvent.click(screen.getByRole('button', { name: 'Import settings' }))
    expect(await screen.findByText('Settings imported.')).toBeTruthy()
    expect(send).toHaveBeenCalledWith({ linxiv_web_settings: 1, settings: { web_lookup_source: 'pubmed' } })
    expect(done).toHaveBeenCalledWith(reply)
  })

  it('reports a file that is not JSON', async () => {
    const send = vi.spyOn(api, 'importSettings')
    render(<Backup onSettingsImported={() => {}} />)
    choose('not json')
    fireEvent.click(screen.getByRole('button', { name: 'Import settings' }))
    expect(await screen.findByText('Import failed: not a JSON file')).toBeTruthy()
    await waitFor(() => expect(send).not.toHaveBeenCalled())
  })
})

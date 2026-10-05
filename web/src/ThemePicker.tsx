import { useEffect, useRef, useState } from 'react'
import {
  loadTheme,
  onThemeChange,
  saveTheme,
  watchSystemMode,
  PRESET_NAMES,
  type ModePref,
  type PresetName,
  type ThemePref,
} from './theme'

const MODES: { value: ModePref; label: string; icon: string }[] = [
  { value: 'system', label: 'System', icon: '◐' },
  { value: 'light', label: 'Light', icon: '☀' },
  { value: 'dark', label: 'Dark', icon: '☾' },
]

export default function ThemePicker({ compact = false }: { compact?: boolean }) {
  const [pref, setLocal] = useState(loadTheme)
  const prefRef = useRef(pref)

  useEffect(() => {
    prefRef.current = pref
  }, [pref])

  useEffect(() => watchSystemMode(() => prefRef.current), [])
  useEffect(() => onThemeChange(setLocal), [])

  const setPref = (next: ThemePref) => saveTheme(next)

  const cycleMode = () => {
    const i = MODES.findIndex((m) => m.value === pref.mode)
    setPref({ ...pref, mode: MODES[(i + 1) % MODES.length].value })
  }

  const current = MODES.find((m) => m.value === pref.mode) ?? MODES[0]

  if (compact) {
    return (
      <button className="link theme-mode" onClick={cycleMode} title={`Mode: ${current.label}`} aria-label={`Mode: ${current.label}`}>
        {current.icon}
      </button>
    )
  }

  return (
    <div className="theme-picker">
      <select
        aria-label="Theme"
        value={pref.preset}
        onChange={(e) => setPref({ ...pref, preset: e.target.value as PresetName })}
      >
        {PRESET_NAMES.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </select>
      <div className="segmented" role="group" aria-label="Mode">
        {MODES.map((m) => (
          <button
            key={m.value}
            className={m.value === pref.mode ? 'active' : ''}
            aria-pressed={m.value === pref.mode}
            title={m.label}
            onClick={() => setPref({ ...pref, mode: m.value })}
          >
            {m.icon}
          </button>
        ))}
      </div>
    </div>
  )
}

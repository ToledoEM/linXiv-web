// Theme presets ported from linXiv desktop v0.6.0 (src/lib/theme.ts).

export type ThemeMode = 'dark' | 'light'
export type ModePref = ThemeMode | 'system'

type Palette = {
  bg: string
  panel: string
  border: string
  accent: string
  text: string
  muted: string
  success: string
  danger: string
  surface2: string
}

export const PRESETS = {
  Navy: {
    dark: { bg: '#0f0f1a', panel: '#1a1a2e', border: '#2e2e50', accent: '#5b8dee', text: '#ccccdd', muted: '#7777aa', success: '#4caf88', danger: '#e05c6c', surface2: 'rgba(21,21,36,0.25)' },
    light: { bg: '#f0f4ff', panel: '#ffffff', border: '#c8d4f0', accent: '#4a7de0', text: '#1a1a3e', muted: '#6677aa', success: '#3d9e76', danger: '#d64e5d', surface2: '#eef2fb' },
  },
  Slate: {
    dark: { bg: '#1a1b1e', panel: '#25262b', border: '#373a40', accent: '#748ffc', text: '#c1c2c5', muted: '#868e96', success: '#51cf66', danger: '#ff6b6b', surface2: '#1f2024' },
    light: { bg: '#f5f5f7', panel: '#ffffff', border: '#e0e1e5', accent: '#5a7cf8', text: '#1a1b1e', muted: '#6b7280', success: '#40c057', danger: '#fa5252', surface2: '#eeeef1' },
  },
  Charcoal: {
    dark: { bg: '#1c1c1c', panel: '#252525', border: '#333333', accent: '#e8912d', text: '#d4d4d4', muted: '#888888', success: '#6abf69', danger: '#e57373', surface2: '#1f1f1f' },
    light: { bg: '#f6f6f6', panel: '#ffffff', border: '#dedede', accent: '#d4811f', text: '#1c1c1c', muted: '#666666', success: '#57a85a', danger: '#cc5252', surface2: '#efefef' },
  },
  Forest: {
    dark: { bg: '#0d1b12', panel: '#162318', border: '#243d2c', accent: '#4caf88', text: '#c8d8cc', muted: '#6b8f72', success: '#81c784', danger: '#ef9a9a', surface2: '#101d14' },
    light: { bg: '#f0f5f2', panel: '#ffffff', border: '#c4d9cc', accent: '#3a9a72', text: '#0d1b12', muted: '#527a5a', success: '#5aad5c', danger: '#e06060', surface2: '#e8efea' },
  },
  Ember: {
    dark: { bg: '#1a1009', panel: '#261a0e', border: '#3d2b18', accent: '#e8912d', text: '#ddd0c4', muted: '#a0897a', success: '#a5d6a7', danger: '#ef5350', surface2: '#1f1409' },
    light: { bg: '#fdf5ee', panel: '#ffffff', border: '#eed8be', accent: '#cc7a1e', text: '#2a1a09', muted: '#8a6a50', success: '#7ab87c', danger: '#d94040', surface2: '#f6ece1' },
  },
  Cupertino: {
    dark: { bg: '#1c1c1e', panel: 'rgba(44,44,46,0.80)', border: 'rgba(58,58,60,0.9)', accent: '#0a84ff', text: '#ffffff', muted: '#8e8e93', success: '#34c759', danger: '#ff3b30', surface2: 'rgba(118,118,128,0.24)' },
    light: { bg: '#eef1f6', panel: 'rgba(255,255,255,0.72)', border: 'rgba(209,209,214,0.6)', accent: '#007aff', text: '#1c1c1e', muted: '#8e8e93', success: '#34c759', danger: '#ff3b30', surface2: 'rgba(120,120,128,0.12)' },
  },
  'Reading Room': {
    dark: { bg: '#1a140d', panel: '#241b11', border: '#3a2c1c', accent: '#cf5a2c', text: '#ece4d6', muted: '#9c8a72', success: '#81c784', danger: '#ef5350', surface2: '#1f160d' },
    light: { bg: '#ece4d6', panel: '#faf6ee', border: '#e2d9c7', accent: '#b0451f', text: '#221d16', muted: '#8a7c66', success: '#5c9a5e', danger: '#c0442a', surface2: '#f3ecdf' },
  },
} satisfies Record<string, Record<ThemeMode, Palette>>

export type PresetName = keyof typeof PRESETS
export const PRESET_NAMES = Object.keys(PRESETS) as PresetName[]

export type ThemePref = { preset: PresetName; mode: ModePref }

const STORAGE_KEY = 'lxw.theme'
const DEFAULT: ThemePref = { preset: 'Navy', mode: 'system' }
const darkQuery = () => window.matchMedia('(prefers-color-scheme: dark)')

export function loadTheme(): ThemePref {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<ThemePref> | null
    if (!raw) return DEFAULT
    return {
      preset: raw.preset && raw.preset in PRESETS ? raw.preset : DEFAULT.preset,
      mode: raw.mode === 'dark' || raw.mode === 'light' ? raw.mode : 'system',
    }
  } catch {
    return DEFAULT
  }
}

export function resolveMode(mode: ModePref): ThemeMode {
  if (mode !== 'system') return mode
  return darkQuery().matches ? 'dark' : 'light'
}

export function applyTheme(pref: ThemePref): void {
  const mode = resolveMode(pref.mode)
  const c = PRESETS[pref.preset][mode]
  const root = document.documentElement
  root.dataset.theme = pref.preset.toLowerCase().replace(' ', '-')
  root.dataset.mode = mode
  root.style.colorScheme = mode
  const vars: Record<string, string> = {
    '--bg': c.bg,
    '--surface': c.panel,
    '--surface-2': c.surface2,
    '--border': c.border,
    '--accent': c.accent,
    '--text': c.text,
    '--muted': c.muted,
    '--success': c.success,
    '--danger': c.danger,
  }
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v)
}

export function saveTheme(pref: ThemePref): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pref))
  } catch {
    // storage unavailable: theme lasts for this page load only
  }
  applyTheme(pref)
  window.dispatchEvent(new CustomEvent<ThemePref>(CHANGE_EVENT, { detail: pref }))
}

const CHANGE_EVENT = 'lxw-theme-change'

// Keeps every mounted picker (sidebar, Settings page) in step.
export function onThemeChange(fn: (pref: ThemePref) => void): () => void {
  const handler = (e: Event) => fn((e as CustomEvent<ThemePref>).detail)
  window.addEventListener(CHANGE_EVENT, handler)
  return () => window.removeEventListener(CHANGE_EVENT, handler)
}

// Re-apply when the OS scheme flips and the user follows the system.
export function watchSystemMode(getPref: () => ThemePref): () => void {
  const q = darkQuery()
  const onChange = () => {
    const pref = getPref()
    if (pref.mode === 'system') applyTheme(pref)
  }
  q.addEventListener('change', onChange)
  return () => q.removeEventListener('change', onChange)
}

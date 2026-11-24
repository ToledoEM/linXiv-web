import type { TagMode } from './types'

/** AI tag modes (server app/tag_pipeline.py TAG_MODES), as offered in Settings and per run. */
export const TAG_MODES: { value: TagMode; label: string; hint: string }[] = [
  { value: 'free', label: 'Free', hint: 'any new tag; only spelling variants and aliases are merged' },
  { value: 'soft', label: 'Soft', hint: 'near-identical tags merge, up to 4 new tags per paper' },
  { value: 'mild', label: 'Mild', hint: 'close tags merge, the model decides the rest, up to 2 new tags' },
  { value: 'hard', label: 'Hard', hint: 'existing tags only, no new tags' },
]

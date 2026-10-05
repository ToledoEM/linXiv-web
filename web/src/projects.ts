// linXiv desktop src/components/projects/constants.ts
export const PRESET_COLORS = ['#5b8dee', '#4caf88', '#e8912d', '#748ffc', '#e05c6c', '#51cf66']
// Reserved tag that turns a project into a reading list (desktop lib/readingStatus.ts).
export const READING_LIST_TAG = 'reading-list'

export const hasTag = (tags: string[], t: string) => tags.some((x) => x.toLowerCase() === t.toLowerCase())

/** A copy of `set` with `id` added or removed. */
export const toggled = (set: Set<string>, id: string) => {
  const next = new Set(set)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  return next
}

// Desktop lib/paperMutations.ts partialFailureMessage.
export const failedMessage = (failed: number, total: number) =>
  `${failed} of ${total} paper${total === 1 ? '' : 's'} could not be added`

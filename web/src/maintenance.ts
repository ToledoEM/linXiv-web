import type { MaintenanceRun } from './types'

/** Totals over every library, e.g. "4 checked · 1 merged"; failed libraries listed after. */
export function runSummary(run: MaintenanceRun): string {
  const totals: Record<string, number> = {}
  const failed: string[] = []
  for (const [key, out] of Object.entries(run.libraries)) {
    if (typeof out.error === 'string') failed.push(`${key}: ${out.error}`)
    for (const [k, v] of Object.entries(out)) {
      if (typeof v === 'number') totals[k] = (totals[k] ?? 0) + v
    }
  }
  const parts = Object.entries(totals).map(([k, v]) => `${v} ${k.replaceAll('_', ' ')}`)
  if (failed.length) parts.push(`failed in ${failed.join('; ')}`)
  return parts.join(' · ') || 'nothing to report'
}

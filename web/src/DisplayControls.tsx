import { useState } from 'react'
import {
  DEFAULT_ZOOM,
  MAX_ZOOM,
  MIN_ZOOM,
  ZOOM_STEP,
  loadDensity,
  loadZoom,
  saveDensity,
  saveZoom,
  type Density,
} from './display'

const DENSITIES: { value: Density; label: string }[] = [
  { value: 'comfortable', label: 'Comfortable' },
  { value: 'compact', label: 'Compact' },
]

/** Zoom −/100%/+ and density (desktop Settings → Appearance). */
export default function DisplayControls() {
  const [zoom, setZoom] = useState(loadZoom)
  const [density, setDensity] = useState(loadDensity)
  const step = (z: number) => setZoom(saveZoom(z))

  return (
    <>
      <div className="field">
        <span>Zoom</span>
        <div className="zoom-control">
          <button type="button" aria-label="Decrease zoom" disabled={zoom <= MIN_ZOOM} onClick={() => step(zoom - ZOOM_STEP)}>
            −
          </button>
          <span className="zoom-value" aria-live="polite">
            {Math.round(zoom * 100)}%
          </span>
          <button type="button" aria-label="Increase zoom" disabled={zoom >= MAX_ZOOM} onClick={() => step(zoom + ZOOM_STEP)}>
            +
          </button>
          <button type="button" className="link" disabled={zoom === DEFAULT_ZOOM} onClick={() => step(DEFAULT_ZOOM)}>
            Reset
          </button>
        </div>
        <span className="muted small">Scale the entire interface up or down.</span>
      </div>
      <div className="field">
        <span>Density</span>
        <div className="segmented density-picker" role="group" aria-label="Interface density">
          {DENSITIES.map((d) => (
            <button
              key={d.value}
              type="button"
              className={density === d.value ? 'active' : ''}
              aria-pressed={density === d.value}
              onClick={() => setDensity(saveDensity(d.value))}
            >
              {d.label}
            </button>
          ))}
        </div>
        <span className="muted small">Controls card and row spacing.</span>
      </div>
    </>
  )
}

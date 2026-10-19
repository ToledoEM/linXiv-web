import { lazy, Suspense, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, graphExportUrl, paperPath } from '../api'
import { ErrorText } from '../components'
import { EMPTY_FILTER, joinTypes, matchGraph, noMatchCause, type GraphFilterState } from '../graph/filter'
import GraphPanels from '../graph/GraphPanels'
import { DEFAULT_FORCES, type ForceSettings } from '../graph/layout'
import { indexView, type GraphView } from '../graph/model'
import type { ThemeColors } from '../graph/style'
import type { GraphCanvasHandle } from '../graph/GraphCanvas'
import { AddToProjectBar } from '../projectParts'
import { loadTheme, onThemeChange, PRESETS, resolveMode, type ThemePref } from '../theme'

// cytoscape + d3-force are only needed here: load the canvas on first visit.
const GraphCanvas = lazy(() => import('../graph/GraphCanvas'))

// Shared with the Authors page, as on desktop (one "hide single-paper authors" switch).
const HIDE_KEY = 'lxw.authors.hideSingle'

function loadHide(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) === '1'
  } catch {
    return false
  }
}

const colorsFor = (pref: ThemePref): ThemeColors => PRESETS[pref.preset][resolveMode(pref.mode)]

/** Knowledge Graph (desktop GraphPage): papers, authors and tags as one force layout. */
export default function Graph() {
  const navigate = useNavigate()
  const canvasRef = useRef<GraphCanvasHandle>(null)
  const [view, setView] = useState<GraphView | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [hideSingle, setHideSingle] = useState(loadHide)
  const [filter, setFilter] = useState<GraphFilterState>(EMPTY_FILTER)
  const [forces, setForces] = useState<ForceSettings>(DEFAULT_FORCES)
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(() => new Set())
  const [pref, setPref] = useState(loadTheme)

  useEffect(() => onThemeChange(setPref), [])
  // Re-resolve "system" mode when the OS scheme flips.
  useEffect(() => {
    const q = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setPref((p) => ({ ...p }))
    q.addEventListener('change', onChange)
    return () => q.removeEventListener('change', onChange)
  }, [])
  const theme = useMemo(() => colorsFor(pref), [pref])

  // `loading` starts set; the checkbox and Refresh set it again before reloading.
  const load = useCallback(
    (hide: boolean) =>
      api
        .graph(hide)
        .then(
          (v) => {
            setView(v)
            setError('')
          },
          (err: Error) => setError(err.message),
        )
        .finally(() => setLoading(false)),
    [],
  )

  useEffect(() => {
    try {
      localStorage.setItem(HIDE_KEY, hideSingle ? '1' : '0')
    } catch {
      // storage unavailable: preference lasts for this page load only
    }
    void load(hideSingle)
  }, [hideSingle, load])

  const index = useMemo(() => (view ? indexView(view) : null), [view])
  // Typing in a filter box re-matches every paper; deferring keeps keystrokes responsive.
  const deferredFilter = useDeferredValue(filter)
  const match = useMemo(
    () => (view && index ? matchGraph(view, index, deferredFilter) : null),
    [view, index, deferredFilter],
  )

  const hiddenSelectedCount = useMemo(() => {
    if (!match || selectedIds.size === 0) return 0
    if (match.hiddenTypes.has('paper')) return selectedIds.size
    if (!match.isolate) return 0
    let n = 0
    for (const id of selectedIds) if (!match.papers.has(id)) n++
    return n
  }, [match, selectedIds])

  // The project bar speaks source_ids; the canvas speaks node ids.
  const selectedSourceIds = useMemo(() => {
    const out = new Set<string>()
    for (const id of selectedIds) {
      const sid = index?.paperById.get(id)?.source_id
      if (sid) out.add(sid)
    }
    return out
  }, [index, selectedIds])
  const selectBySourceIds = (sids: Set<string>) => {
    const next = new Set<string>()
    for (const [id, p] of index?.paperById ?? []) if (sids.has(p.source_id)) next.add(id)
    setSelectedIds(next)
  }

  // The panel column floats over the canvas's right edge; fits frame the strip left of it.
  const panelsRef = useRef<HTMLDivElement>(null)
  const [gutter, setGutter] = useState(0)
  const measureGutter = useCallback(() => panelsRef.current?.getBoundingClientRect().width ?? 0, [])
  useEffect(() => {
    const el = panelsRef.current
    if (!el) return
    const measure = () => setGutter(el.getBoundingClientRect().width)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [view])

  const onPaperTap = useCallback(
    (id: string, additive: boolean) => {
      if (additive) {
        setSelectedIds((prev) => {
          const next = new Set(prev)
          if (!next.delete(id)) next.add(id)
          return next
        })
        return
      }
      const sid = index?.paperById.get(id)?.source_id
      if (sid) void navigate(paperPath(sid))
    },
    [index, navigate],
  )
  const onAuthorTap = useCallback((authorId: number) => navigate(`/authors/${authorId}`), [navigate])
  const onTagTap = useCallback((label: string) => navigate(`/library?tag=${encodeURIComponent(label)}`), [navigate])
  const onBackgroundTap = useCallback(() => {}, [])

  const ready = view && index && match
  const empty = ready && view.papers.length + view.authors.length + view.tags.length === 0
  const cause = ready && !empty && match.drawnCount === 0 ? noMatchCause(match) : null

  return (
    <section className="graph-page">
      <div className="page-head">
        <h2>Knowledge Graph</h2>
        <span className="muted small">
          {selectedIds.size > 0
            ? `${selectedIds.size} paper${selectedIds.size === 1 ? '' : 's'} selected; Ctrl/Cmd+click to add more`
            : 'Click a node to open · Ctrl/Cmd+click to select papers'}
        </span>
        <span className="page-head-action graph-head-actions">
          <label
            className="check"
            title="Drop authors linked to only one paper. They leave the graph entirely, so the Author filter can't match them either."
          >
            <input
              type="checkbox"
              checked={hideSingle}
              onChange={(e) => {
                setLoading(true)
                setHideSingle(e.target.checked)
              }}
            />
            Hide single-paper authors
          </label>
          <button
            type="button"
            className="link"
            disabled={loading}
            onClick={() => {
              setLoading(true)
              void load(hideSingle)
            }}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
          <a
            href={graphExportUrl('graphml', hideSingle)}
            download
            title="Whole graph (filters not applied) for Gephi, Cytoscape, yEd, igraph or NetworkX"
          >
            Export GraphML
          </a>
          <a
            href={graphExportUrl('csv', hideSingle)}
            download
            title="Whole graph (filters not applied) as nodes.csv and edges.csv in a zip"
          >
            Export CSV
          </a>
        </span>
      </div>
      {selectedSourceIds.size > 0 && <AddToProjectBar selected={selectedSourceIds} onSelect={selectBySourceIds} />}
      {error && !view ? (
        <ErrorText error={error} />
      ) : !ready ? (
        <p className="muted">Loading graph…</p>
      ) : empty ? (
        <p className="card muted center">No papers yet. Add some and they appear here with their authors and tags.</p>
      ) : (
        <div className="graph-stage">
          <Suspense fallback={<p className="muted center graph-loading">Loading graph engine…</p>}>
            <GraphCanvas
              ref={canvasRef}
              view={view}
              index={index}
              theme={theme}
              forces={forces}
              match={match}
              selectedIds={selectedIds}
              gutter={gutter}
              measureGutter={measureGutter}
              onPaperTap={onPaperTap}
              onAuthorTap={onAuthorTap}
              onTagTap={onTagTap}
              onBackgroundTap={onBackgroundTap}
            />
          </Suspense>
          {cause && (
            <div className="graph-nomatch card" style={{ right: gutter + 16 }}>
              {cause.kind === 'filters'
                ? 'No papers match the current filters.'
                : `${joinTypes(cause.types)} hidden by the Visibility checkboxes.`}{' '}
              <button type="button" className="link" onClick={() => setFilter(EMPTY_FILTER)}>
                Clear filters
              </button>
            </div>
          )}
          <GraphPanels
            columnRef={panelsRef}
            view={view}
            filter={filter}
            onFilterChange={setFilter}
            onClearFilters={() => setFilter(EMPTY_FILTER)}
            forces={forces}
            onForcesChange={setForces}
            onRelayout={() => canvasRef.current?.relayout()}
            selectedCount={selectedIds.size}
            hiddenSelectedCount={hiddenSelectedCount}
            onSelectAllVisible={() => {
              if (match && !match.hiddenTypes.has('paper')) setSelectedIds(new Set(match.papers))
            }}
            onClearSelection={() => setSelectedIds(new Set())}
          />
          {error && <p className="error graph-refresh-error">Refresh failed: {error}</p>}
        </div>
      )}
    </section>
  )
}

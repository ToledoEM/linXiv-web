import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type UIEvent,
} from 'react'
import { Document, Page, pdfjs, type DocumentProps } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import { api } from './api'
import ColorSwatches from './ColorSwatches'
import { loadZoom, onZoomChange } from './display'
import { HIGHLIGHT_COLORS, parseAnchor, selectionToAnchor, type Anchor } from './pdfAnchor'
import {
  buildPageIndex,
  escapeHtml,
  estPageHeight,
  findMatches,
  highlightHtml,
  PAGE_INSET,
  PDF_FIND_EVENT,
  pdfDocumentOptions,
  rangesForItem,
  type HighlightRange,
  type PageIndex,
} from './pdfFind'
import { registerPdfReader } from './shortcuts'
import { submitOnCtrlEnter } from './submitShortcut'
import type { Annotation } from './types'

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

// Pages this far from the current one render; the rest are fixed-height spacers.
const PAGE_WINDOW = 4
// Quiet time after the last resize tick before pages re-render at the new width.
const RESIZE_SETTLE_MS = 120
// CSS zoom (A3) scales the finished raster, so the canvas backing grows with it;
// capped so HiDPI × max zoom can't exceed browser canvas limits.
const MAX_CANVAS_DPR = 3

type LoadedPdf = Parameters<NonNullable<DocumentProps['onLoadSuccess']>>[0]

type PageHighlight = { id: number; anchor: Anchor }
type SelBar = { top: number; left: number; anchor: Anchor }
type Popup = { id: number; top: number; left: number; anchor: Anchor; comment: string }

interface Props {
  file: string
  errorUrl?: string
  sourceId: string
  /** Paper version the rendered PDF belongs to; anchors are scoped to it. */
  version: number
  /** New highlights are scoped to this project (null = library-wide). */
  projectId?: number | null
  annotations: Annotation[]
  onAnnotationsChanged: () => Promise<unknown> | void
  /** The PDF could not be fetched or parsed (e.g. file missing on disk). */
  onLoadError?: () => void
}

/** In-page PDF reader (desktop PdfReader): fit-width pages, a page indicator, a
 * find bar (Ctrl/Cmd+F inside the reader) and text highlights with comments. */
export default function PdfReader({
  file,
  errorUrl,
  sourceId,
  version,
  projectId = null,
  annotations,
  onAnnotationsChanged,
  onLoadError,
}: Props) {
  const [numPages, setNumPages] = useState(0)
  const [page, setPage] = useState(1)
  const [pageInput, setPageInput] = useState('1')
  const [width, setWidth] = useState(0)
  const [findOpen, setFindOpen] = useState(false)
  const [findQuery, setFindQuery] = useState('')
  const [findCur, setFindCur] = useState(0)
  // One PageIndex per page, extracted lazily the first time the bar opens.
  const [pageIndexes, setPageIndexes] = useState<PageIndex[] | null>(null)

  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const pdfDocRef = useRef<LoadedPdf | null>(null)
  const rafRef = useRef<number | null>(null)
  const findInputRef = useRef<HTMLInputElement | null>(null)
  // Armed on a find jump; the target page's text-layer render completes it.
  const findScrollPendingRef = useRef(false)
  const [zoom, setZoomState] = useState(loadZoom)
  useEffect(() => onZoomChange(setZoomState), [])
  // Ctrl/Cmd+F and "/" open this reader's find bar while it is mounted (shortcuts.ts).
  useEffect(() => registerPdfReader(), [])
  const dpr = Math.min(MAX_CANVAS_DPR, (window.devicePixelRatio || 1) * zoom)
  const [selBar, setSelBar] = useState<SelBar | null>(null)
  const [popup, setPopup] = useState<Popup | null>(null)
  const [draft, setDraft] = useState('')
  const [draftColor, setDraftColor] = useState<string>(HIGHLIGHT_COLORS[0])
  const [hlBusy, setHlBusy] = useState(false)
  const [hlError, setHlError] = useState('')

  // This version's highlights per page: layout (and so coords) differ per version.
  const byPage = useMemo(() => {
    const m = new Map<number, PageHighlight[]>()
    for (const a of annotations) {
      const anchor = parseAnchor(a.anchor)
      if (!anchor || anchor.version !== version) continue
      m.set(anchor.page, [...(m.get(anchor.page) ?? []), { id: a.id, anchor }])
    }
    return m
  }, [annotations, version])

  // Stable ref callback: the observer is built once per scroller element.
  const obsRef = useRef<ResizeObserver | null>(null)
  const timerRef = useRef<number | null>(null)
  const attachScroller = useCallback((el: HTMLDivElement | null) => {
    obsRef.current?.disconnect()
    if (timerRef.current !== null) clearTimeout(timerRef.current)
    scrollerRef.current = el
    if (!el) return
    let first = true
    const obs = new ResizeObserver((entries) => {
      const w = entries[0].contentRect.width
      if (first) {
        first = false
        setWidth(w)
        return
      }
      if (timerRef.current !== null) clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => setWidth(w), RESIZE_SETTLE_MS)
    })
    obs.observe(el)
    obsRef.current = obs
  }, [])

  useEffect(
    () => () => {
      obsRef.current?.disconnect()
      if (timerRef.current !== null) clearTimeout(timerRef.current)
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    },
    [],
  )

  const slots = () => scrollerRef.current?.querySelectorAll<HTMLElement>('.pdf-page-slot')

  // DOM only: the scroll handler then tracks the page that comes into view.
  const scrollToPage = (target: number) => {
    const scroller = scrollerRef.current
    const el = slots()?.[target - 1]
    if (scroller && el) scroller.scrollTop = el.offsetTop
  }

  const goToPage = (target: number) => {
    if (numPages <= 0) return
    const next = Math.min(Math.max(target, 1), numPages)
    setPage(next)
    setPageInput(String(next))
    scrollToPage(next)
  }

  const onScroll = (e: UIEvent<HTMLDivElement>) => {
    const scroller = e.currentTarget
    if (selBar) setSelBar(null)
    if (popup) setPopup(null)
    if (rafRef.current !== null) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      const pages = slots()
      if (!pages?.length) return
      let nearest = 1
      let best = Infinity
      pages.forEach((el, i) => {
        const d = Math.abs(el.offsetTop - scroller.scrollTop)
        if (d < best) {
          best = d
          nearest = i + 1
        }
      })
      setPage(nearest)
      setPageInput(String(nearest))
    })
  }

  const onLoad = (pdf: LoadedPdf) => {
    pdfDocRef.current = pdf
    setPageIndexes(null)
    setNumPages(pdf.numPages)
  }

  // --- Find ---------------------------------------------------------------
  const matches = useMemo(
    () => (findOpen && pageIndexes ? findMatches(findQuery, pageIndexes) : []),
    [findOpen, findQuery, pageIndexes],
  )
  // Clamped: a query edit can shrink the match list under findCur.
  const cur = Math.min(findCur, Math.max(matches.length - 1, 0))

  // Bumped on every open request; the effect focuses once the bar is committed
  // (a rAF can run before React renders a bar opened from a window key listener).
  const [findFocusTick, setFindFocusTick] = useState(0)
  const openFind = useCallback(() => {
    setFindOpen(true)
    setFindFocusTick((t) => t + 1)
  }, [])

  useEffect(() => {
    if (!findFocusTick) return
    findInputRef.current?.focus()
    findInputRef.current?.select()
  }, [findFocusTick])

  useEffect(() => {
    window.addEventListener(PDF_FIND_EVENT, openFind)
    return () => window.removeEventListener(PDF_FIND_EVENT, openFind)
  }, [openFind])

  // Extract every page's text once per document, on first open.
  useEffect(() => {
    const pdf = pdfDocRef.current
    if (!findOpen || pageIndexes || !pdf) return
    let cancelled = false
    void (async () => {
      const idx: PageIndex[] = []
      try {
        for (let i = 1; i <= pdf.numPages; i++) {
          const content = await (await pdf.getPage(i)).getTextContent()
          idx.push(buildPageIndex(content.items.map((it) => ('str' in it ? it.str : ''))))
        }
      } catch {
        // keep the partial index; find covers the pages that extracted
      }
      if (!cancelled && pdfDocRef.current === pdf) setPageIndexes(idx)
    })()
    return () => {
      cancelled = true
    }
  }, [findOpen, pageIndexes, numPages])

  const scrollToCurrentMark = useCallback(() => {
    const el = scrollerRef.current?.querySelector('.pdf-find-current')
    if (!el) return false
    el.scrollIntoView({ block: 'center' })
    findScrollPendingRef.current = false
    return true
  }, [])

  // A jump mounts the target page; its text-layer render finishes the scroll.
  useEffect(() => {
    if (!findOpen || matches.length === 0) return
    findScrollPendingRef.current = true
    const m = matches[cur]
    const slot = slots()?.[m.page - 1]
    if (!slot?.querySelector('.react-pdf__Page') || !scrollToCurrentMark()) scrollToPage(m.page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [findOpen, matches, cur])

  const gotoMatch = (i: number) => {
    if (matches.length === 0) return
    const next = ((i % matches.length) + matches.length) % matches.length
    if (next === cur) {
      findScrollPendingRef.current = true
      if (!scrollToCurrentMark()) goToPage(matches[cur].page)
      return
    }
    setFindCur(next)
  }

  const rangesByPage = useMemo(() => {
    const byPage = new Map<number, HighlightRange[]>()
    matches.forEach((m, i) => {
      const list = byPage.get(m.page) ?? []
      list.push({ start: m.start, end: m.end, current: i === cur })
      byPage.set(m.page, list)
    })
    return byPage
  }, [matches, cur])

  // Wraps matched slices of each text item in <mark>; undefined when idle so
  // the text layer renders plainly.
  const textRenderer = useMemo(() => {
    if (!findOpen || !pageIndexes || rangesByPage.size === 0) return undefined
    return ({ pageNumber, itemIndex, str }: { pageNumber: number; itemIndex: number; str: string }) => {
      const ranges = rangesByPage.get(pageNumber)
      const start = pageIndexes[pageNumber - 1]?.starts[itemIndex]
      if (!ranges || start === undefined) return escapeHtml(str)
      return highlightHtml(str, rangesForItem(start, str.length, ranges))
    }
  }, [findOpen, pageIndexes, rangesByPage])

  // Stable per-page callbacks: react-pdf rebuilds a page's text layer whenever
  // its callback props change identity.
  const latest = useRef({ matches, cur, scrollToCurrentMark })
  useLayoutEffect(() => {
    latest.current = { matches, cur, scrollToCurrentMark }
  })
  const textLayerCbs = useMemo(
    () =>
      Array.from({ length: numPages }, (_, i) => () => {
        const l = latest.current
        if (findScrollPendingRef.current && l.matches[l.cur]?.page === i + 1) l.scrollToCurrentMark()
      }),
    [numPages],
  )

  // --- Highlights -----------------------------------------------------------
  // Floaters are position:fixed inside the CSS-zoomed root, so viewport px are
  // divided by the zoom factor; the clamp keeps them on screen.
  const place = (left: number, top: number, w: number, h: number) => ({
    left: Math.max(8, Math.min(left, window.innerWidth - w)) / zoom,
    top: Math.max(8, Math.min(top, window.innerHeight - h)) / zoom,
  })

  const openPopup = (id: number, anchor: Anchor, comment: string, x: number, y: number) => {
    setDraft(comment)
    setDraftColor(anchor.color)
    setPopup({ id, anchor, comment, ...place(x, y + 6, 300, 240) })
  }

  // A real text selection inside a page: show the color toolbar at its end.
  const onMouseUp = () => {
    const sel = window.getSelection()
    if (!sel || sel.isCollapsed || sel.rangeCount === 0 || !sel.toString().trim()) return
    const range = sel.getRangeAt(0)
    const node = range.startContainer
    const el = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement
    if (!el?.closest('.react-pdf__Page')) return
    const rects = range.getClientRects()
    const last = rects[rects.length - 1]
    if (!last) return
    // Captured now: the selection may collapse before the toolbar click.
    const anchor = selectionToAnchor(version, HIGHLIGHT_COLORS[0])
    if (!anchor) {
      setHlError("Couldn't capture that selection (it may span two pages). Select the text again.")
      return
    }
    setHlError('')
    setSelBar({ anchor, ...place(last.left, last.bottom + 6, 170, 40) })
  }

  const createHighlight = async (color: string) => {
    const bar = selBar
    if (!bar) return
    setSelBar(null)
    window.getSelection()?.removeAllRanges()
    const anchor = { ...bar.anchor, color }
    setHlBusy(true)
    setHlError('')
    try {
      const r = await api.createAnnotation({ source_id: sourceId, anchor, comment: '', project_id: projectId })
      await onAnnotationsChanged()
      // Comment box opens on the new highlight; dismissing it keeps the highlight.
      setDraft('')
      setDraftColor(color)
      setPopup({ id: r.id, anchor, comment: '', left: bar.left, top: bar.top })
    } catch (err) {
      setHlError(`Couldn't save highlight: ${(err as Error).message}`)
    } finally {
      setHlBusy(false)
    }
  }

  // Plain clicks hit-test the page's highlight rects (the overlay ignores the
  // pointer so text under a highlight stays selectable).
  const onClick = (e: MouseEvent<HTMLDivElement>) => {
    const sel = window.getSelection()
    if (sel && !sel.isCollapsed && sel.toString().trim()) return
    const pageEl = (e.target as Element).closest?.<HTMLElement>('.react-pdf__Page')
    if (!pageEl) return
    const list = byPage.get(Number(pageEl.getAttribute('data-page-number')))
    if (!list?.length) return
    const box = pageEl.getBoundingClientRect()
    if (!box.width || !box.height) return
    const nx = (e.clientX - box.left) / box.width
    const ny = (e.clientY - box.top) / box.height
    const hit = list.find(({ anchor }) =>
      anchor.rects.some((r) => nx >= r.x && nx <= r.x + r.w && ny >= r.y && ny <= r.y + r.h),
    )
    if (!hit) return
    const comment = annotations.find((a) => a.id === hit.id)?.comment ?? ''
    openPopup(hit.id, hit.anchor, comment, e.clientX, e.clientY)
  }

  const canSave = !!popup && !hlBusy && (draft !== popup.comment || draftColor !== popup.anchor.color)

  const savePopup = async () => {
    if (!popup || !canSave) return
    setHlBusy(true)
    setHlError('')
    try {
      await api.updateAnnotation(
        popup.id,
        draftColor !== popup.anchor.color
          ? { comment: draft, color: draftColor, source_id: sourceId }
          : { comment: draft },
      )
      await onAnnotationsChanged()
      setPopup(null)
    } catch (err) {
      setHlError(`Couldn't save annotation: ${(err as Error).message}`)
    } finally {
      setHlBusy(false)
    }
  }

  const deletePopup = async () => {
    if (!popup) return
    setHlBusy(true)
    setHlError('')
    try {
      await api.deleteAnnotation(popup.id)
      await onAnnotationsChanged()
      setPopup(null)
    } catch (err) {
      setHlError(`Couldn't delete highlight: ${(err as Error).message}`)
    } finally {
      setHlBusy(false)
    }
  }

  const pageWidth = width ? width - PAGE_INSET : undefined
  return (
    <div className="pdf-reader">
      <div className="pdf-toolbar">
        <form
          className="pdf-page-pill"
          onSubmit={(e) => {
            e.preventDefault()
            goToPage(Number(pageInput) || page)
          }}
        >
          <button
            type="button"
            className="link"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => goToPage(page - 1)}
          >
            ‹
          </button>
          <span className="muted small">Page</span>
          <input
            aria-label="Page number"
            inputMode="numeric"
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ''))}
            onBlur={() => setPageInput(String(page))}
          />
          <span className="muted small">/ {numPages || '–'}</span>
          <button
            type="button"
            className="link"
            aria-label="Next page"
            disabled={page >= numPages}
            onClick={() => goToPage(page + 1)}
          >
            ›
          </button>
        </form>
        {findOpen ? (
          <div
            className="pdf-find"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation()
                setFindOpen(false)
              } else if (e.key === 'Enter') {
                e.preventDefault()
                gotoMatch(cur + (e.shiftKey ? -1 : 1))
              }
            }}
          >
            <input
              ref={findInputRef}
              aria-label="Find in PDF"
              placeholder="Find in PDF"
              value={findQuery}
              onChange={(e) => {
                setFindQuery(e.target.value)
                setFindCur(0)
              }}
            />
            <span className="muted small mono pdf-find-count">
              {findQuery === ''
                ? ''
                : pageIndexes === null
                  ? '…'
                  : `${matches.length === 0 ? 0 : cur + 1}/${matches.length}`}
            </span>
            <button type="button" className="link" aria-label="Previous match" disabled={!matches.length} onClick={() => gotoMatch(cur - 1)}>
              ▲
            </button>
            <button type="button" className="link" aria-label="Next match" disabled={!matches.length} onClick={() => gotoMatch(cur + 1)}>
              ▼
            </button>
            <button type="button" className="link" aria-label="Close find bar" onClick={() => setFindOpen(false)}>
              ✕
            </button>
          </div>
        ) : (
          <button type="button" className="link" onClick={openFind} title="Find in PDF (Ctrl/Cmd+F)">
            Find
          </button>
        )}
      </div>
      <div
        className="pdf-scroller"
        ref={attachScroller}
        onScroll={onScroll}
        tabIndex={0}
        onMouseDown={() => {
          if (selBar) setSelBar(null)
          if (popup) setPopup(null)
        }}
        onMouseUp={onMouseUp}
        onClick={onClick}
      >
        <Document
          file={file}
          options={pdfDocumentOptions}
          onLoadSuccess={onLoad}
          onLoadError={onLoadError}
          loading={<p className="muted center pdf-status">Loading PDF…</p>}
          error={
            <p className="center pdf-status">
              <span className="error">Failed to load PDF.</span>{' '}
              {errorUrl && (
                <a href={errorUrl} target="_blank" rel="noreferrer">
                  Open in new tab
                </a>
              )}
            </p>
          }
        >
          {Array.from({ length: numPages }, (_, i) => {
            const pn = i + 1
            if (Math.abs(pn - page) > PAGE_WINDOW) {
              return <div key={pn} className="pdf-page-slot" style={{ width: pageWidth, height: estPageHeight(width) }} />
            }
            return (
              <div key={pn} className="pdf-page-slot">
                <Page
                  pageNumber={pn}
                  width={pageWidth}
                  devicePixelRatio={dpr}
                  customTextRenderer={textRenderer}
                  onRenderTextLayerSuccess={textLayerCbs[i]}
                  loading={<div className="pdf-page-loading" style={{ width: pageWidth, height: estPageHeight(width) }} />}
                  renderTextLayer
                  renderAnnotationLayer
                >
                  {byPage.has(pn) && (
                    <div className="pdf-highlights" aria-hidden>
                      {byPage.get(pn)!.map(({ id, anchor }) =>
                        anchor.rects.map((r, k) => (
                          <div
                            key={`${id}-${k}`}
                            className="pdf-highlight"
                            data-annotation-id={id}
                            style={{
                              left: `${r.x * 100}%`,
                              top: `${r.y * 100}%`,
                              width: `${r.w * 100}%`,
                              height: `${r.h * 100}%`,
                              backgroundColor: anchor.color,
                            }}
                          />
                        )),
                      )}
                    </div>
                  )}
                </Page>
              </div>
            )
          })}
        </Document>
      </div>
      {selBar && (
        <div
          className="pdf-floater pdf-selbar"
          style={{ top: selBar.top, left: selBar.left }}
          // keep the selection alive and the scroller from re-handling the click
          onMouseDown={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
          onMouseUp={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
        >
          <span className="small">Highlight</span>
          <ColorSwatches onChange={createHighlight} label="Highlight in" />
        </div>
      )}
      {popup && (
        <div
          className="pdf-floater pdf-popup"
          style={{ top: popup.top, left: popup.left }}
          role="dialog"
          aria-label="Highlight"
          onMouseDown={(e) => e.stopPropagation()}
          onMouseUp={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setPopup(null)
            else submitOnCtrlEnter(() => void savePopup())(e)
          }}
        >
          {popup.anchor.quote && <p className="pdf-quote small">“{popup.anchor.quote}”</p>}
          <textarea
            rows={3}
            autoFocus
            placeholder="Add a comment…"
            aria-label="Highlight comment"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="pdf-popup-actions">
            <ColorSwatches value={draftColor} onChange={setDraftColor} />
            <span>
              <button type="button" className="link danger-link" disabled={hlBusy} onClick={deletePopup}>
                Delete
              </button>{' '}
              <button type="button" disabled={!canSave} onClick={savePopup}>
                {hlBusy ? 'Saving…' : 'Save'}
              </button>
            </span>
          </div>
        </div>
      )}
      {hlError && (
        <p className="error pdf-hl-error" role="alert">
          {hlError}
        </p>
      )}
    </div>
  )
}

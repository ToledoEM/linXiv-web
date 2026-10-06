import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type UIEvent } from 'react'
import { Document, Page, pdfjs, type DocumentProps } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import { loadZoom } from './display'
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

pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

// Pages this far from the current one render; the rest are fixed-height spacers.
const PAGE_WINDOW = 4
// Quiet time after the last resize tick before pages re-render at the new width.
const RESIZE_SETTLE_MS = 120
// CSS zoom (A3) scales the finished raster, so the canvas backing grows with it;
// capped so HiDPI × max zoom can't exceed browser canvas limits.
const MAX_CANVAS_DPR = 3

type LoadedPdf = Parameters<NonNullable<DocumentProps['onLoadSuccess']>>[0]

/** In-page PDF reader (desktop PdfReader without highlights): fit-width pages,
 * a page indicator, and a find bar (Ctrl/Cmd+F inside the reader). */
export default function PdfReader({ file, errorUrl }: { file: string; errorUrl?: string }) {
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
  const dpr = useMemo(() => Math.min(MAX_CANVAS_DPR, (window.devicePixelRatio || 1) * loadZoom()), [])

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

  const goToPage = (target: number) => {
    if (numPages <= 0) return
    const next = Math.min(Math.max(target, 1), numPages)
    setPage(next)
    setPageInput(String(next))
    const scroller = scrollerRef.current
    const el = slots()?.[next - 1]
    if (scroller && el) scroller.scrollTop = el.offsetTop
  }

  const onScroll = (e: UIEvent<HTMLDivElement>) => {
    const scroller = e.currentTarget
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

  const openFind = useCallback(() => {
    setFindOpen(true)
    requestAnimationFrame(() => {
      findInputRef.current?.focus()
      findInputRef.current?.select()
    })
  }, [])

  useEffect(() => {
    window.addEventListener(PDF_FIND_EVENT, openFind)
    return () => window.removeEventListener(PDF_FIND_EVENT, openFind)
  }, [openFind])

  // Extract every page's text once per document, on first open.
  useEffect(() => {
    const pdf = pdfDocRef.current
    if (!findOpen || pageIndexes || !pdf) return
    let cancelled = false
    ;(async () => {
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
    if (!slot?.querySelector('.react-pdf__Page')) goToPage(m.page)
    else if (!scrollToCurrentMark()) goToPage(m.page)
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
  latest.current = { matches, cur, scrollToCurrentMark }
  const pageCbs = useRef(new Map<number, () => void>())
  const onTextLayer = (pn: number) => {
    let cb = pageCbs.current.get(pn)
    if (!cb) {
      cb = () => {
        const l = latest.current
        if (findScrollPendingRef.current && l.matches[l.cur]?.page === pn) l.scrollToCurrentMark()
      }
      pageCbs.current.set(pn, cb)
    }
    return cb
  }

  const onReaderKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
      e.preventDefault()
      openFind()
    }
  }

  const pageWidth = width ? width - PAGE_INSET : undefined
  return (
    <div className="pdf-reader" onKeyDown={onReaderKey}>
      <div className="pdf-toolbar">
        <form
          className="pdf-page-pill"
          onSubmit={(e) => {
            e.preventDefault()
            goToPage(Number(pageInput) || page)
          }}
        >
          <span className="muted small">Page</span>
          <input
            aria-label="Page number"
            inputMode="numeric"
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ''))}
            onBlur={() => setPageInput(String(page))}
          />
          <span className="muted small">/ {numPages || '–'}</span>
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
      <div className="pdf-scroller" ref={attachScroller} onScroll={onScroll} tabIndex={0}>
        <Document
          file={file}
          options={pdfDocumentOptions}
          onLoadSuccess={onLoad}
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
                  onRenderTextLayerSuccess={onTextLayer(pn)}
                  loading={<div className="pdf-page-loading" style={{ width: pageWidth, height: estPageHeight(width) }} />}
                  renderTextLayer
                  renderAnnotationLayer
                />
              </div>
            )
          })}
        </Document>
      </div>
    </div>
  )
}

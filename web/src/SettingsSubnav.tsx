import { useEffect, useRef, useState, type RefObject } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { sectionSlug } from './settingsHash'

type Item = { id: string; slug: string; title: string }

const CARD_HEADINGS = '.settings-section > h3'

/** The cards of the open Settings group, read from the rendered panel (every card
 *  is `.settings-section` with an `<h3>`), so a new card shows up here on its own.
 *  Click scrolls to the card and sets `#<group>/<section>`; `section` (from the
 *  hash) scrolls there once the card exists. Nothing for a group of one card. */
export default function SettingsSubnav({
  group,
  panel,
  section,
}: {
  group: string
  panel: RefObject<HTMLElement | null>
  section: string | null
}) {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const [items, setItems] = useState<Item[]>([])
  const [current, setCurrent] = useState<string | null>(null)
  const scrolledTo = useRef<string | null>(null)

  // Collect the cards now and whenever the panel's content changes.
  useEffect(() => {
    const root = panel.current
    if (!root) return
    const scan = () => {
      const seen = new Map<string, number>()
      const next: Item[] = []
      for (const h of root.querySelectorAll<HTMLElement>(CARD_HEADINGS)) {
        const title = h.textContent?.trim() ?? ''
        const card = h.parentElement
        if (!title || !card) continue
        const base = sectionSlug(title)
        const n = (seen.get(base) ?? 0) + 1
        seen.set(base, n)
        const slug = n > 1 ? `${base}-${n}` : base
        const id = `${group}-${slug}`
        if (card.id !== id) card.id = id
        next.push({ id, slug, title })
      }
      setItems((old) =>
        old.length === next.length && old.every((o, i) => o.id === next[i].id && o.title === next[i].title)
          ? old
          : next,
      )
    }
    scan()
    const watch = new MutationObserver(scan)
    watch.observe(root, { childList: true, subtree: true, characterData: true })
    return () => watch.disconnect()
  }, [group, panel])

  // Highlight the topmost card in view while scrolling.
  useEffect(() => {
    if (items.length < 2 || typeof IntersectionObserver === 'undefined') return
    const visible = new Set<string>()
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) visible.add(e.target.id)
          else visible.delete(e.target.id)
        }
        const top = items.find((i) => visible.has(i.id))
        if (top) setCurrent(top.id)
      },
      { rootMargin: '0px 0px -60% 0px' },
    )
    for (const i of items) {
      const el = document.getElementById(i.id)
      if (el) io.observe(el)
    }
    return () => io.disconnect()
  }, [items])

  // Deep link: scroll to the section from the hash once its card is there.
  useEffect(() => {
    if (!section || scrolledTo.current === `${group}/${section}`) return
    const item = items.find((i) => i.slug === section)
    if (!item) return
    scrolledTo.current = `${group}/${section}`
    document.getElementById(item.id)?.scrollIntoView({ block: 'start' })
  }, [group, section, items])

  if (items.length < 2) return null
  // Until a click or scroll picks one, the section from the hash is current.
  const active = current ?? items.find((i) => i.slug === section)?.id ?? null

  const go = (item: Item) => {
    scrolledTo.current = `${group}/${item.slug}`
    document.getElementById(item.id)?.scrollIntoView({ block: 'start', behavior: 'smooth' })
    setCurrent(item.id)
    void navigate({ pathname, search, hash: `${group}/${item.slug}` }, { replace: true })
  }

  return (
    <ul className="settings-subnav" aria-label="Sections">
      {items.map((i) => (
        <li key={i.id}>
          <button
            type="button"
            className={active === i.id ? 'current' : ''}
            aria-current={active === i.id ? 'location' : undefined}
            onClick={() => go(i)}
          >
            {i.title}
          </button>
        </li>
      ))}
    </ul>
  )
}

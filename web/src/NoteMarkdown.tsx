// Note body as Markdown with TeX, ported from linXiv desktop
// (src/components/notes/NoteMarkdown.tsx, v0.7.0). Basic CommonMark (headings,
// lists, emphasis, code, blockquotes, links), no tables or strikethrough; math
// goes through MathText (KaTeX here, MathJax on desktop). react-markdown renders
// no raw HTML, so note text can't inject markup.

import { Children, cloneElement, isValidElement, type JSXElementConstructor, type ReactNode } from 'react'
import Markdown, { type Components } from 'react-markdown'
import { extractMath, restoreMath } from './noteMath'
import { MathText } from './tex'

type LeafType = string | JSXElementConstructor<never>

// code/pre keep literal text; the MATH_TAGS components already walk their own children.
function skipMathWalk(element: { type: unknown }, mathComponents: Set<unknown>): boolean {
  return element.type === 'code' || element.type === 'pre' || mathComponents.has(element.type)
}

// Route every raw text string through MathText (placeholders restored first);
// recursion into inline elements (strong/em/a) reaches their text too.
function withMath(children: ReactNode, math: string[], mathComponents: Set<unknown>, forceInline: boolean): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === 'string') {
      return <MathText forceInline={forceInline}>{restoreMath(child, math)}</MathText>
    }
    if (isValidElement(child)) {
      if (skipMathWalk(child, mathComponents)) return child
      const kids = (child.props as { children?: ReactNode }).children
      if (kids == null) return child
      return cloneElement(child, undefined, withMath(kids, math, mathComponents, forceInline))
    }
    return child
  })
}

const MATH_TAGS = ['p', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'] as const

function createComponents(math: string[], forceInline: boolean): Components {
  const mathComponents = new Set<unknown>()
  const components: Components = Object.fromEntries(
    MATH_TAGS.map((Tag) => [
      Tag,
      // eslint-disable-next-line @typescript-eslint/no-unused-vars -- `node` must not reach the DOM
      ({ node, children, ...rest }: { node?: unknown; children?: ReactNode }) => (
        <Tag {...rest}>{withMath(children, math, mathComponents, forceInline)}</Tag>
      ),
    ]),
  )
  for (const c of Object.values(components)) mathComponents.add(c as LeafType)
  return components
}

/** `forceInline` keeps $$…$$ inline, for the collapsed (line-clamped) note card. */
export function NoteMarkdown({ content, forceInline = false }: { content: string; forceInline?: boolean }) {
  const { text, math } = extractMath(content)
  return (
    <div className="note-markdown">
      <Markdown components={createComponents(math, forceInline)}>{text}</Markdown>
    </div>
  )
}

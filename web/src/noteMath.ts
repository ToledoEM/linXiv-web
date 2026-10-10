// Math placeholders for the note Markdown view, ported from linXiv desktop
// (src/components/notes/noteMath.ts, v0.7.0): $…$ / $$…$$ spans are pulled out
// before react-markdown parses the text, so `_` and `*` inside TeX never turn
// into emphasis, then restored in each rendered text leaf.

// In priority order: fenced code blocks, inline code spans, display math $$...$$,
// inline math $...$. Backtick matches pass through unchanged.
const MATH_OR_CODE_RE = /```[\s\S]*?```|`[^`\n]*`|\$\$[\s\S]+?\$\$|\$(?!\s)[^$\n]*?[^$\s]\$/g

// Private Use Area sentinels (U+E000 open, U+E001 close) bracket a math[] index.
// They don't occur in normal note text, so the restore regex matches only our
// placeholders; a bare "\d+" token would clobber any real digit.
const MATH_OPEN = String.fromCharCode(0xe000)
const MATH_CLOSE = String.fromCharCode(0xe001)
const MATH_TOKEN_RE = new RegExp(MATH_OPEN + '(\\d+)' + MATH_CLOSE, 'g')

/** Swap every $…$ / $$…$$ span for a placeholder token. */
export function extractMath(raw: string): { text: string; math: string[] } {
  const math: string[] = []
  const text = raw.replace(MATH_OR_CODE_RE, (m) => {
    if (m[0] === '`') return m
    const token = `${MATH_OPEN}${math.length}${MATH_CLOSE}`
    math.push(m)
    return token
  })
  return { text, math }
}

/** Put the original math source back into a rendered text leaf. */
export function restoreMath(text: string, math: string[]): string {
  if (math.length === 0) return text
  return text.replace(MATH_TOKEN_RE, (_m, i: string) => math[Number(i)] ?? '')
}

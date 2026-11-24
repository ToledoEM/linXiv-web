"""Tag normalisation key and the no-merge rules for AI tagging.

Ported unchanged from the offline tag consolidation of this library
(linXiv-tags-semantic `tm_common.norm_key`, `tm_singletons.sibling` and
`symbol_like`), so tags added here group the same way the consolidated
vocabulary was built.

- `norm_key`: one key per spelling variant. Case, hyphens, punctuation, plurals,
  British to American spelling and `sequencing` to `seq` fold together
  (`RNA-seq` = `rna sequencing`, `Wnt signalling` = `wnt signaling`).
- `sibling`: two different members of one identifier family (`stat1`/`stat5`,
  `foxa1`/`foxc1`). String similarity rates them close; they must never merge.
- `symbol_like`: a short gene-symbol-like tag (`En1`, `NONO`), matched only by
  key or alias, never by fuzzy similarity.
"""

from __future__ import annotations

import re
import unicodedata

_KEEP = ("ss", "us", "is", "ics")
# British -> American spelling and sequencing -> seq, applied to the joined key.
_SPELLING = (
    (r"sequencing", "seq"),
    (r"isation", "ization"),
    (r"ise$", "ize"),
    (r"ised$", "ized"),
    (r"ising$", "izing"),
    (r"our", "or"),
    (r"ae", "e"),
    (r"oe", "e"),
    (r"lling", "ling"),
    (r"lled", "led"),
    (r"tre$", "ter"),
)
ID_TAIL = re.compile(r"^(.*?[a-z])(\d+[a-z]?|alpha|beta|gamma|delta|epsilon|kappa)$")
TAIL = re.compile(r"^(\d+)([a-z]?)$")
# Underscore and the Unicode hyphens and dashes (U+2010 to U+2015).
_DASHES = re.compile("[_" + "".join(chr(c) for c in range(0x2010, 0x2016)) + "]+")


def _singular(w: str) -> str:
    if len(w) <= 3 or w.endswith(_KEEP):
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    return w[:-1] if w.endswith("s") else w


def norm_key(tag: str) -> str:
    """Matching key of a tag: '' when nothing word-like is left."""
    t = unicodedata.normalize("NFKC", tag).casefold()
    t = re.sub(r"[-_/]+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    k = "".join(_singular(w) for w in t.split())
    for old, new in _SPELLING:
        k = re.sub(old, new, k)
    return k


def display(tag: str) -> str:
    """Tag as shown and stored: NFKC, no leading '#', single spaces, dashes as '-'."""
    t = unicodedata.normalize("NFKC", tag).strip().lstrip("#")
    t = _DASHES.sub("-", t)
    return re.sub(r"\s+", " ", t).strip()


def id_split(key: str) -> tuple[str | None, str | None]:
    m = ID_TAIL.match(key)
    return (m.group(1), m.group(2)) if m else (None, None)


def sibling(a: str, b: str) -> bool:
    """Identifier siblings (keys): different members of one family.

    Same stem with a different tail (stat1/stat5, il6/il10, srebp1a/srebp1c), or
    stems of equal length that differ in one letter (foxa1/foxc1). Not siblings:
    the same number where only one tail carries a letter (gsk3/gsk3b).
    """
    sa, ia = id_split(a)
    sb, ib = id_split(b)
    if sa is None or sb is None or (sa == sb and ia == ib):
        return False
    if sa != sb:
        return len(sa) == len(sb) >= 2 and sum(p != q for p, q in zip(sa, sb, strict=True)) == 1
    ta, tb = TAIL.match(ia or ""), TAIL.match(ib or "")
    return not (ta and tb and ta.group(1) == tb.group(1) and "" in (ta.group(2), tb.group(2)))


def symbol_like(label: str, key: str) -> bool:
    """Gene-symbol-like tag: one token, at most 6 characters, with a digit, a
    capital, or 3 characters or fewer (En1, NONO, Helt, er)."""
    return (
        " " not in label.strip()
        and len(key) <= 6
        and (any(ch.isdigit() for ch in key) or any(ch.isupper() for ch in label) or len(key) <= 3)
    )

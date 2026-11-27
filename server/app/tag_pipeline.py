"""AI tag suggestions checked against the library's vocabulary.

Stage 1 (routes/ai.py) asks the model for free candidate tags without showing
it the vocabulary. This module then:

1. matches each candidate by normalisation key (`tag_norm.norm_key`) against the
   vocabulary (library tags + CSV tags), then the alias table, then the
   candidate's own `also_known_as` forms;
2. for the rest, finds the 5 nearest vocabulary tags by string similarity
   (rapidfuzz), never an identifier sibling (stat1/stat5), and never for a
   gene-symbol-like candidate;
3. adds a frequency boost so tags on more papers win ties and can cross the
   auto-merge line;
4. applies the mode: auto-merge, send to stage 2 (the model picks map / alias /
   new from the short list), keep as a new tag, or drop.

Modes trade new tags for consolidation:

| mode | auto-merge | stage 2 | new tags |
|---|---|---|---|
| free | key / alias only | never | up to 6 |
| soft | >= 95 | 85 to 95 | up to 4 |
| mild | >= 90 | every unresolved candidate with a neighbour | up to 2, stage 2 verdict only |
| hard | >= 85 | 60 to 85 | none |
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from .tag_norm import display, norm_key, plural_term, sibling, symbol_like

MAX_SUGGESTED = 6
MAX_TAG_LEN = 64
NEIGHBOURS = 5
# Neighbours below this similarity are noise, even as context for stage 2.
MIN_NEIGHBOUR = 50.0
# Candidates looked at per scorer before siblings are removed.
_SCAN = 20
RESERVED = {norm_key("reading-list")}


@dataclass(frozen=True)
class Mode:
    # Score (similarity + frequency boost) at or above which a candidate merges
    # into its nearest tag. None: no similarity matching at all.
    auto: float | None
    # Similarity at or above which an unmerged candidate goes to stage 2.
    floor: float
    max_new: int
    # Candidates below `floor` still go to stage 2 when they have neighbours.
    review_all: bool = False
    # New tags are not allowed: unmatched candidates are dropped.
    drop_new: bool = False


TAG_MODES: dict[str, Mode] = {
    "free": Mode(auto=None, floor=0, max_new=MAX_SUGGESTED),
    "soft": Mode(auto=95, floor=85, max_new=4),
    "mild": Mode(auto=90, floor=75, max_new=2, review_all=True),
    "hard": Mode(auto=85, floor=60, max_new=0, drop_new=True),
}
DEFAULT_MODE = "soft"
DEFAULT_FREQ_WEIGHT = 10
MAX_FREQ_WEIGHT = 30


@dataclass(frozen=True)
class Options:
    mode: str
    freq_weight: float
    max_new: int


def options(stored: dict, mode: str | None = None) -> Options:
    """Tagging options from the saved settings; `mode` overrides the saved mode."""
    name = mode if mode in TAG_MODES else stored.get("web_tag_mode")
    name = name if name in TAG_MODES else DEFAULT_MODE
    weight = stored.get("web_tag_freq_weight")
    if not isinstance(weight, int) or isinstance(weight, bool):
        weight = DEFAULT_FREQ_WEIGHT
    cap = stored.get("web_tag_max_new")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
        cap = TAG_MODES[name].max_new
    if TAG_MODES[name].drop_new:
        cap = 0
    return Options(name, float(min(max(weight, 0), MAX_FREQ_WEIGHT)), min(cap, MAX_SUGGESTED))


@dataclass(frozen=True)
class Entry:
    tag: str
    weight: float
    known: bool  # used in the library
    in_vocab: bool  # listed in the CSV vocabulary


@dataclass
class Vocabulary:
    entries: dict[str, Entry] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._keys = list(self.entries)
        self._labels = [self.entries[k].tag.casefold() for k in self._keys]
        self._max = max((e.weight for e in self.entries.values()), default=0.0)

    @classmethod
    def build(
        cls,
        library_tags: list[str],
        counts: dict[str, int],
        csv_rows: list[dict],
        aliases: dict[str, str],
    ) -> Vocabulary:
        """Library tags (spelling of the most used variant per key) joined with the
        CSV vocabulary; a CSV weight replaces the paper count."""
        best: dict[str, tuple[str, int]] = {}
        total: dict[str, int] = {}
        for tag in library_tags:
            if not isinstance(tag, str):
                continue
            key = norm_key(tag)
            if not key or key in RESERVED:
                continue
            n = counts.get(tag, 0)
            total[key] = total.get(key, 0) + n
            if key not in best or n > best[key][1]:
                best[key] = (tag, n)
        entries = {k: Entry(tag, float(total[k]), True, False) for k, (tag, _) in best.items()}
        for row in csv_rows:
            key, tag, weight = row.get("tag_key"), row.get("tag"), row.get("weight")
            if not key or not tag or key in RESERVED:
                continue
            seen = entries.get(key)
            w = float(weight) if weight is not None else (seen.weight if seen else 0.0)
            if seen:
                entries[key] = Entry(seen.tag, w, True, True)
            else:
                entries[key] = Entry(tag, w, False, True)
        return cls(entries, dict(aliases))

    def boost(self, entry: Entry, alpha: float) -> float:
        if alpha <= 0 or self._max <= 0:
            return 0.0
        return alpha * math.log1p(entry.weight) / math.log1p(self._max)

    def lookup(self, key: str) -> tuple[Entry, str] | None:
        """(entry, "exact" | "alias") for a key, or None."""
        if not key:
            return None
        if key in self.entries:
            return self.entries[key], "exact"
        canonical = self.aliases.get(key)
        if canonical:
            ckey = norm_key(canonical)
            return self.entries.get(ckey) or Entry(canonical, 0.0, False, False), "alias"
        return None

    def neighbours(self, label: str, key: str, alpha: float, floor: float) -> list[Neighbour]:
        """Nearest vocabulary tags, best first; no identifier siblings."""
        if not self._keys:
            return []
        raw: dict[int, float] = {}
        for _, score, i in process.extract(key, self._keys, scorer=fuzz.ratio, limit=_SCAN):
            raw[i] = max(raw.get(i, 0.0), float(score))
        for _, score, i in process.extract(
            label.casefold(), self._labels, scorer=fuzz.token_sort_ratio, limit=_SCAN
        ):
            raw[i] = max(raw.get(i, 0.0), float(score))
        out = []
        for i, sim in raw.items():
            k = self._keys[i]
            if sim < MIN_NEIGHBOUR or sibling(key, k):
                continue
            entry = self.entries[k]
            score = sim + self.boost(entry, alpha) if sim >= floor else sim
            out.append(Neighbour(entry, k, sim, score))
        out.sort(key=lambda n: (-n.score, -n.entry.weight, n.entry.tag))
        return out[:NEIGHBOURS]


@dataclass(frozen=True)
class Neighbour:
    entry: Entry
    key: str
    similarity: float
    score: float


@dataclass
class Candidate:
    label: str
    also_known_as: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return norm_key(self.label)


def candidates(raw: object) -> list[Candidate] | None:
    """Stage 1 reply -> candidates (plain strings accepted too); None when the
    reply has no tag list."""
    if not isinstance(raw, dict) or not isinstance(raw.get("tags"), list):
        return None
    out = []
    for item in raw["tags"]:
        if isinstance(item, str):
            label, aka = item, []
        elif isinstance(item, dict) and isinstance(item.get("tag"), str):
            label = item["tag"]
            aka = [a for a in item.get("also_known_as") or [] if isinstance(a, str)]
        else:
            continue
        label = display(label)
        if (
            not label
            or len(label) > MAX_TAG_LEN
            or any(ord(c) < 32 or ord(c) == 127 for c in label)
        ):
            continue
        out.append(Candidate(label, [display(a) for a in aka if display(a)][:4]))
    return out


@dataclass
class Result:
    suggested: list[dict] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    # (alias, canonical) proposed by stage 2, for the review queue.
    proposals: list[tuple[str, str]] = field(default_factory=list)


# Stage 2: [{candidate, neighbours: [{tag, papers}]}] -> [{candidate, action, tag}]
Resolver = Callable[[list[dict]], Awaitable[list[dict]]]


def _picked(entry: Entry, how: str, label: str) -> dict:
    out = {"tag": entry.tag, "known": entry.known, "in_vocab": entry.in_vocab, "how": how}
    if label.casefold() != entry.tag.casefold():
        out["from"] = label
    return out


def unslug(label: str) -> str:
    """'fiber-optic-sensors' -> 'fiber optic sensors': some models write every tag
    as a slug. One hyphen (RNA-seq, single-cell) is kept."""
    if " " not in label and label.count("-") >= 2:
        return " ".join(w for w in label.split("-") if w)
    return label


def _new(label: str) -> dict:
    return {"tag": plural_term(unslug(label)), "known": False, "in_vocab": False, "how": "new"}


async def run(
    found: list[Candidate],
    vocab: Vocabulary,
    opts: Options,
    current: list[str],
    resolve: Resolver,
) -> Result:
    """Match candidates to the vocabulary; `resolve` is stage 2, called at most
    once and only when some candidate needs it."""
    mode = TAG_MODES[opts.mode]
    result = Result()
    # Per candidate, in the model's order: a pick, "review", or None (dropped).
    slots: list[dict | str | None] = []
    review: dict[int, list[Neighbour]] = {}

    for i, cand in enumerate(found):
        key = cand.key
        hit = vocab.lookup(key)
        if hit is None:
            for aka in cand.also_known_as:
                hit = vocab.lookup(norm_key(aka))
                if hit:
                    hit = (hit[0], "alias")
                    break
        if hit is not None:
            slots.append(_picked(hit[0], hit[1], cand.label))
            continue
        if mode.auto is None:
            slots.append(_new(cand.label))
            continue
        near = (
            []
            if symbol_like(cand.label, key)
            else vocab.neighbours(cand.label, key, opts.freq_weight, mode.floor)
        )
        best = near[0] if near else None
        if best and best.score >= mode.auto:
            slots.append(_picked(best.entry, "fuzzy", cand.label))
        elif near and (best.similarity >= mode.floor or mode.review_all):
            review[i] = near
            slots.append("review")
        elif mode.drop_new:
            result.dropped.append({"candidate": cand.label, "reason": "no close tag"})
            slots.append(None)
        else:
            slots.append(_new(cand.label))

    if review:
        asked = [
            {
                "candidate": found[i].label,
                "neighbours": [{"tag": n.entry.tag, "papers": int(n.entry.weight)} for n in near],
            }
            for i, near in review.items()
        ]
        decisions = {}
        for d in await resolve(asked):
            if isinstance(d, dict) and isinstance(d.get("candidate"), str):
                decisions.setdefault(d["candidate"].strip().casefold(), d)
        for i, near in review.items():
            cand = found[i]
            d = decisions.get(cand.label.casefold()) or {}
            action, target = d.get("action"), d.get("tag")
            target = display(target) if isinstance(target, str) else ""
            pick = None
            if action in ("map", "alias") and target:
                tkey = norm_key(target)
                match = next((n for n in near if n.key == tkey), None)
                if match and not sibling(cand.key, tkey):
                    pick = _picked(match.entry, f"llm-{action}", cand.label)
                    if action == "alias":
                        result.proposals.append((cand.label, match.entry.tag))
                else:
                    # Off the short list, or a sibling: the candidate stays as it is.
                    action, target = "new", ""
            if pick is None and action == "new":
                label = target if target and len(target) <= MAX_TAG_LEN else cand.label
                hit = vocab.lookup(norm_key(label))
                pick = _picked(hit[0], "llm-map", cand.label) if hit else _new(label)
            if pick is None and not mode.review_all and not mode.drop_new:
                # No verdict: soft keeps the candidate as a new tag.
                pick = _new(cand.label)
            if pick is None:
                result.dropped.append({"candidate": cand.label, "reason": "no decision"})
            slots[i] = pick

    taken = {norm_key(t) for t in current if isinstance(t, str)} | RESERVED
    new_count = 0
    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            continue
        key = norm_key(slot["tag"])
        if not key or key in taken:
            continue
        if slot["how"] == "new":
            if new_count >= opts.max_new:
                reason = "new tags not allowed" if opts.max_new == 0 else "new-tag limit"
                result.dropped.append({"candidate": found[i].label, "reason": reason})
                continue
            new_count += 1
        taken.add(key)
        result.suggested.append(slot)
        if len(result.suggested) == MAX_SUGGESTED:
            break
    return result

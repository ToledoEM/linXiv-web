from __future__ import annotations

import asyncio

from app import tag_pipeline as tp
from app.tag_norm import norm_key


def _vocab(tags: dict[str, int], aliases: dict[str, str] | None = None, csv=None):
    return tp.Vocabulary.build(list(tags), tags, csv or [], aliases or {})


class Stage2:
    """Records what stage 2 is asked and answers from a {candidate: (action, tag)} table."""

    def __init__(self, answers: dict[str, tuple[str, str]] | None = None) -> None:
        self.answers = answers or {}
        self.asked: list[list[dict]] = []

    async def __call__(self, asked: list[dict]) -> list[dict]:
        self.asked.append(asked)
        return [
            {"candidate": a["candidate"], "action": act, "tag": tag}
            for a in asked
            if (hit := self.answers.get(a["candidate"]))
            for act, tag in [hit]
        ]


def _fixed(vocab: tp.Vocabulary, sims: dict[str, float]) -> None:
    """Neighbours with fixed similarities, for band tests."""

    def near(label, key, alpha, floor):
        out = [tp.Neighbour(vocab.entries[norm_key(t)], norm_key(t), s, s) for t, s in sims.items()]
        return sorted(out, key=lambda n: -n.score)

    vocab.neighbours = near  # type: ignore[method-assign]


def _run(found, vocab, mode="soft", current=(), stage2=None, **opts):
    o = tp.options({"web_tag_mode": mode, **opts})
    return asyncio.run(tp.run(found, vocab, o, list(current), stage2 or Stage2()))


def C(label, *aka):
    return tp.Candidate(label, list(aka))


def tags(result):
    return [(s["tag"], s["how"]) for s in result.suggested]


# ---- options + stage 1 reply ----


def test_options_defaults_and_overrides():
    o = tp.options({})
    assert (o.mode, o.freq_weight, o.max_new) == ("soft", 10.0, 4)
    assert tp.options({"web_tag_mode": "mild"}, "hard").mode == "hard"
    assert tp.options({"web_tag_mode": "bogus"}).mode == "soft"
    assert tp.options({"web_tag_max_new": 1}).max_new == 1
    assert tp.options({"web_tag_mode": "hard", "web_tag_max_new": 3}).max_new == 0
    assert tp.options({"web_tag_freq_weight": 99}).freq_weight == 30
    assert tp.options({"web_tag_freq_weight": True}).freq_weight == 10


def test_candidates_from_reply():
    got = tp.candidates(
        {
            "tags": [
                {"tag": " #Deep  learning ", "also_known_as": ["DL", 3, ""]},
                "graph neural network",
                {"tag": "x" * 65, "also_known_as": []},
                {"nope": 1},
                7,
            ]
        }
    )
    assert [(c.label, c.also_known_as) for c in got] == [
        ("Deep learning", ["DL"]),
        ("graph neural network", []),
    ]
    assert tp.candidates({"x": 1}) is None
    assert tp.candidates("tags") is None


# ---- deterministic matches ----


def test_exact_key_alias_and_also_known_as():
    vocab = _vocab(
        {"RNA-seq": 40, "microRNA": 12, "CRISPR": 5}, aliases={norm_key("miRNA"): "microRNA"}
    )
    stage2 = Stage2()
    r = _run(
        [
            C("RNA sequencing"),
            C("miRNA"),
            C("clustered regularly interspaced short palindromic repeats", "CRISPR"),
        ],
        vocab,
        stage2=stage2,
    )
    assert tags(r) == [("RNA-seq", "exact"), ("microRNA", "alias"), ("CRISPR", "alias")]
    assert r.suggested[0]["from"] == "RNA sequencing"
    assert r.suggested[0]["known"] is True
    assert not stage2.asked


def test_most_used_spelling_is_the_tag():
    vocab = _vocab({"rna-seq": 3, "RNA-seq": 30})
    assert tags(_run([C("RNA sequencing")], vocab)) == [("RNA-seq", "exact")]
    assert vocab.entries[norm_key("RNA-seq")].weight == 33


def test_csv_vocabulary_joins_library():
    csv = [
        {"tag_key": norm_key("Organoid"), "tag": "Organoid", "weight": 50.0},
        {"tag_key": norm_key("rna seq"), "tag": "rna seq", "weight": None},
    ]
    vocab = _vocab({"RNA-seq": 4}, csv=csv)
    r = _run([C("organoids"), C("RNA sequencing")], vocab)
    assert r.suggested == [
        {"tag": "Organoid", "known": False, "in_vocab": True, "how": "exact", "from": "organoids"},
        {
            "tag": "RNA-seq",
            "known": True,
            "in_vocab": True,
            "how": "exact",
            "from": "RNA sequencing",
        },
    ]


def test_current_and_reserved_tags_and_duplicates_are_skipped():
    vocab = _vocab({"RNA-seq": 4, "reading-list": 9})
    r = _run(
        [C("rna sequencing"), C("Reading list"), C("RNA-seq"), C("autophagy")],
        vocab,
        mode="free",
        current=["Autophagy"],
    )
    assert tags(r) == [("RNA-seq", "exact")]


# ---- similarity ----


def test_typo_merges_by_similarity():
    vocab = _vocab({"convolutional neural network": 9})
    r = _run([C("convolutional neural netwrk")], vocab)
    assert tags(r) == [("convolutional neural network", "fuzzy")]


def test_free_mode_never_uses_similarity():
    vocab = _vocab({"convolutional neural network": 9})
    r = _run([C("convolutional neural netwrk")], vocab, mode="free")
    assert tags(r) == [("convolutional neural netwrk", "new")]


def test_siblings_are_never_neighbours():
    vocab = _vocab({"interleukin 10": 50, "interleukin signaling": 2})
    near = vocab.neighbours("interleukin 6", norm_key("interleukin 6"), 10, 85)
    assert [n.entry.tag for n in near] == ["interleukin signaling"]


def test_gene_symbols_only_match_by_key():
    vocab = _vocab({"STAT1": 80})
    stage2 = Stage2()
    r = _run([C("STAT5")], vocab, mode="mild", stage2=stage2)
    assert tags(r) == [("STAT5", "new")]
    assert not stage2.asked
    r = _run([C("STAT5")], vocab, mode="hard")
    assert r.suggested == [] and r.dropped == [{"candidate": "STAT5", "reason": "no close tag"}]


def test_frequency_breaks_ties_and_lifts_over_the_line():
    vocab = _vocab({"abcdefghik": 1, "abcdefghil": 100})
    near = vocab.neighbours("abcdefghij", "abcdefghij", 10, 85)
    assert [n.entry.tag for n in near[:2]] == ["abcdefghil", "abcdefghik"]
    assert near[0].similarity == near[1].similarity == 90
    # +10 points for the most used tag: 90 -> 100, over soft's 95.
    assert tags(_run([C("abcdefghij")], vocab)) == [("abcdefghil", "fuzzy")]
    stage2 = Stage2()
    r = _run([C("abcdefghij")], vocab, stage2=stage2, web_tag_freq_weight=0)
    assert stage2.asked and tags(r) == [("abcdefghij", "new")]


# ---- modes and stage 2 ----


def test_soft_band_goes_to_stage2():
    vocab = _vocab({"neural network": 30, "graph theory": 2})
    _fixed(vocab, {"neural network": 90, "graph theory": 60})
    stage2 = Stage2({"neural nets": ("map", "neural network")})
    r = _run([C("neural nets")], vocab, stage2=stage2)
    assert tags(r) == [("neural network", "llm-map")]
    assert stage2.asked == [
        [
            {
                "candidate": "neural nets",
                "neighbours": [
                    {"tag": "neural network", "papers": 30},
                    {"tag": "graph theory", "papers": 2},
                ],
            }
        ]
    ]
    assert r.proposals == []


def test_alias_verdict_is_proposed():
    vocab = _vocab({"Alzheimer's disease": 30})
    _fixed(vocab, {"Alzheimer's disease": 88})
    stage2 = Stage2({"alzheimer dementia": ("alias", "alzheimer's disease")})
    r = _run([C("alzheimer dementia")], vocab, stage2=stage2)
    assert tags(r) == [("Alzheimer's disease", "llm-alias")]
    assert r.proposals == [("alzheimer dementia", "Alzheimer's disease")]


def test_new_verdict_keeps_fixed_spelling():
    vocab = _vocab({"tumor microenvironment": 3})
    _fixed(vocab, {"tumor microenvironment": 86})
    stage2 = Stage2({"tumour immunology": ("new", "tumor immunology")})
    r = _run([C("tumour immunology")], vocab, stage2=stage2)
    assert tags(r) == [("tumor immunology", "new")]


def test_target_off_the_short_list_or_a_sibling_is_new():
    vocab = _vocab({"cell signaling": 3, "apoptosis": 50})
    _fixed(vocab, {"cell signaling": 86})
    stage2 = Stage2({"cell signalling network": ("map", "apoptosis")})
    r = _run([C("cell signalling network")], vocab, stage2=stage2)
    assert tags(r) == [("cell signalling network", "new")]

    vocab = _vocab({"protein foxc1": 9})
    _fixed(vocab, {"protein foxc1": 90})
    stage2 = Stage2({"protein foxa1": ("map", "protein foxc1")})
    assert tags(_run([C("protein foxa1")], vocab, stage2=stage2)) == [("protein foxa1", "new")]


def test_no_verdict():
    vocab = _vocab({"neural network": 30})
    _fixed(vocab, {"neural network": 85})
    assert tags(_run([C("neural nets")], vocab)) == [("neural nets", "new")]
    r = _run([C("neural nets")], vocab, mode="mild")
    assert r.suggested == [] and r.dropped == [
        {"candidate": "neural nets", "reason": "no decision"}
    ]


def test_mild_reviews_below_the_band():
    vocab = _vocab({"neural network": 30})
    _fixed(vocab, {"neural network": 55})
    stage2 = Stage2({"perceptron": ("new", "perceptron")})
    assert tags(_run([C("perceptron")], vocab, mode="mild", stage2=stage2)) == [
        ("perceptron", "new")
    ]
    assert stage2.asked
    # Soft: below its band, a new tag without asking.
    stage2 = Stage2()
    assert tags(_run([C("perceptron")], vocab, stage2=stage2)) == [("perceptron", "new")]
    assert not stage2.asked


def test_hard_mode_allows_no_new_tags():
    vocab = _vocab({"neural network": 30, "proteomics": 4})
    _fixed(vocab, {"neural network": 70})
    stage2 = Stage2({"perceptron": ("new", "perceptron"), "deep nets": ("map", "neural network")})
    r = _run([C("deep nets"), C("perceptron")], vocab, mode="hard", stage2=stage2)
    assert tags(r) == [("neural network", "llm-map")]
    assert r.dropped == [{"candidate": "perceptron", "reason": "new tags not allowed"}]

    _fixed(vocab, {"neural network": 52})
    r = _run([C("perceptron")], vocab, mode="hard")
    assert r.dropped == [{"candidate": "perceptron", "reason": "no close tag"}]


def test_new_tag_cap_and_total_cap():
    found = [C(f"topic {c}") for c in "abcdefgh"]
    r = _run(found, _vocab({}), mode="free", web_tag_max_new=2)
    assert [t for t, _ in tags(r)] == ["topic a", "topic b"]
    assert {d["reason"] for d in r.dropped} == {"new-tag limit"}
    r = _run(found, _vocab({}), mode="free")
    assert len(r.suggested) == tp.MAX_SUGGESTED


def test_stage2_called_once_for_all_band_candidates():
    vocab = _vocab({"neural network": 30})
    _fixed(vocab, {"neural network": 90})
    stage2 = Stage2()
    _run([C("neural nets"), C("deep nets"), C("neural network")], vocab, stage2=stage2)
    assert len(stage2.asked) == 1
    assert [a["candidate"] for a in stage2.asked[0]] == ["neural nets", "deep nets"]


def test_new_slug_tags_get_spaces():
    assert tp.unslug("fiber-optic-sensors") == "fiber optic sensors"
    assert tp.unslug("RNA-seq") == "RNA-seq"
    assert tp.unslug("single-cell RNA-seq") == "single-cell RNA-seq"
    r = _run([C("diffusion-models"), C("fiber-optic-sensors")], _vocab({}), mode="free")
    assert tags(r) == [("diffusion-models", "new"), ("fiber optic sensors", "new")]

from __future__ import annotations

import pytest

from app.tag_norm import display, norm_key, sibling, symbol_like


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("RNA-seq", "rna sequencing"),
        ("RNA-seq", "RNAseq"),
        ("Wnt signalling", "wnt signaling"),
        ("tumour", "tumor"),
        ("haematopoiesis", "hematopoiesis"),
        ("randomisation", "randomization"),
        ("Neural Networks", "neural network"),
        ("single_cell", "single-cell"),
        ("T/B cells", "t b cell"),
        ("ＲＮＡ", "rna"),  # NFKC: full-width letters
        ("studies", "study"),
    ],
)
def test_same_key(a, b):
    assert norm_key(a) == norm_key(b) != ""


@pytest.mark.parametrize("word", ["analysis", "genomics", "mass", "virus", "dna", "gas"])
def test_words_kept_singular(word):
    assert norm_key(word) == word


def test_keys_that_differ_stay_apart():
    assert norm_key("scRNA-seq") != norm_key("RNA-seq")
    assert norm_key("proteomics") != norm_key("transcriptomics")
    assert norm_key("!!!") == ""


def test_display():
    assert display("  #Deep   learning ") == "Deep learning"
    assert display("single_cell") == "single-cell"
    assert display("x" + chr(0x2013) + "ray") == "x-ray"


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("stat1", "stat5", True),
        ("il6", "il10", True),
        ("foxa1", "foxc1", True),
        ("srebp1a", "srebp1c", True),
        ("pparalpha", "ppargamma", True),
        ("gsk3", "gsk3b", False),
        ("stat1", "stat1", False),
        ("wntsignaling", "wntpathway", False),
    ],
)
def test_sibling(a, b, expected):
    assert sibling(a, b) is expected


def test_symbol_like():
    assert symbol_like("En1", norm_key("En1"))
    assert symbol_like("NONO", norm_key("NONO"))
    assert symbol_like("er", "er")
    assert not symbol_like("autophagy", norm_key("autophagy"))
    assert not symbol_like("deep learning", norm_key("deep learning"))

from __future__ import annotations

from app.tsv import cell, tsv


def test_cells_have_no_breaks_and_no_formulas():
    assert cell("a\tb\r\nc") == "a b c"
    assert cell(None) == ""
    assert cell(12) == "12"
    for lead in "=+-@":
        assert cell(f"{lead}SUM(A1)") == f"'{lead}SUM(A1)"
    assert tsv(["a", "b"], [("x", 1), ("=y", None)]) == "a\tb\nx\t1\n'=y\t\n"

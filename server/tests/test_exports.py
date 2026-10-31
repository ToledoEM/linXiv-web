from __future__ import annotations

from app import bibtex


def _paper(**kw):
    base = {
        "source_id": "doi:10.1/x",
        "title": "A Study of Things",
        "authors": ["Jane Q. Smith", "Bo Li"],
        "published": "2024-05-01",
        "doi": "10.1000/x",
        "category": "Cell",
        "journal_ref": None,
    }
    return {**base, **kw}


def test_article_fields_and_author_join():
    out = bibtex.render([_paper()])
    assert out.startswith("@article{smith2024study,\n")
    assert "  author = {Jane Q. Smith and Bo Li}" in out
    assert "  journal = {Cell}" in out
    assert "  url = {https://doi.org/10.1000/x}" in out


def test_arxiv_is_misc_with_eprint():
    p = _paper(source_id="arxiv:1706.03762", doi=None, category="cs.CL", title="Attention")
    out = bibtex.render([p])
    assert out.startswith("@misc{smith2024attention,")
    assert "eprint = {1706.03762}" in out and "primaryClass = {cs.CL}" in out
    assert "journal" not in out
    assert "@article" in bibtex.render([{**p, "journal_ref": "NeurIPS 2017"}])


def test_escaping_keeps_math_and_balances_braces():
    assert bibtex.escape("R&D 50% #1 a_b $x_1$") == r"R\&D 50\% \#1 a\_b $x_1$"
    assert bibtex.escape(r"already \& done") == r"already \& done"
    assert bibtex.escape("bad {brace") == "bad brace"
    assert bibtex.escape("ok {DNA}") == "ok {DNA}"


def test_keys_dedupe_and_missing_fields():
    out = bibtex.render([_paper(), _paper(), {"source_id": "local:k", "title": ""}])
    assert "{smith2024study," in out and "{smith2024studya," in out
    assert "@article{anon," in out
    assert bibtex._suffix(27) == "aa"


def test_export_route_order_and_404(client, fake):
    fake.on(
        "list", result=[_paper(source_id="a", title="Alpha"), _paper(source_id="b", title="Beta")]
    )
    r = client.post("/api/export/bibtex", json={"ids": ["b", "a", "b", "zzz"]})
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.text.index("Beta") < r.text.index("Alpha") and r.text.count("@article") == 2
    assert client.post("/api/export/bibtex", json={"ids": ["zzz"]}).status_code == 404
    assert client.post("/api/export/bibtex", json={"ids": []}).status_code == 422

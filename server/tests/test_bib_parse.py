from __future__ import annotations

from app import bib_parse

BIB = r"""
@comment{ignored}
@string{jx = "Journal X"}
@Article{doe2020,
  title = {{Deep} Learning of \{Things\}},
  author = "Doe, Jane and Roe, R.",
  journal = jx,
  volume = 12, number = {3},
  pages = {1--10},
  month = may,
  publisher = {ACM},
  doi = {10.1000/abc},
}
@inproceedings(conf21,
  title = "A {"}quoted{"} title",
  booktitle = {Proc. of {CONF}},
  eprint = {2101.00001v2}, archivePrefix = {arXiv}, primaryClass = {cs.LG}
)
@misc{broken, title = {Unclosed
"""


def test_entries_and_fields():
    got = bib_parse.entries(BIB)
    assert [e["entry_type"] for e in got] == ["article", "inproceedings", "misc"]
    first = got[0]["fields"]
    assert first["title"] == "Deep Learning of \\Things\\"
    assert first["author"] == "Doe, Jane and Roe, R."
    assert (first["volume"], first["number"], first["month"]) == ("12", "3", "may")
    assert bib_parse.bib_fields(got[0]) == {
        "entry_type": "article",
        "volume": "12",
        "number": "3",
        "pages": "1--10",
        "month": "may",
        "publisher": "ACM",
    }
    second = bib_parse.bib_fields(got[1])
    assert second["booktitle"] == "Proc. of CONF"
    assert (second["archive_prefix"], second["primary_class"]) == ("arXiv", "cs.LG")
    assert got[2]["fields"]["title"] == "Unclosed"


def test_entry_without_fields_and_norm_title():
    assert bib_parse.entries("@misc{onlykey}") == [{"entry_type": "misc", "fields": {}}]
    assert bib_parse.entries("@misc{k, = junk, title = {T}}")[0]["fields"] == {"title": "T"}
    assert bib_parse.norm_title("  Deep: Learning!  ") == "deep learning"
    assert bib_parse.norm_title(None) == ""

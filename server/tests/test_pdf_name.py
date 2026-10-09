from __future__ import annotations

import pytest

from app.pdf_name import pdf_file, title_from_file, title_suspect, year_from_file

BASES = ["/data/pdfs", "/pdfs"]


def test_pdf_file_relative_to_pdf_folder():
    assert pdf_file("/data/pdfs/Mendeley/1995/A_b_c.pdf", BASES) == "Mendeley/1995/A_b_c.pdf"
    assert pdf_file("/pdfs/x.pdf", BASES) == "x.pdf"
    assert pdf_file("/elsewhere/x.pdf", BASES) is None
    assert pdf_file("/data/pdfsX/x.pdf", BASES) is None
    assert pdf_file("", BASES) is None
    assert pdf_file(None, BASES) is None


@pytest.mark.parametrize(
    ("rel", "title"),
    [
        (
            "Mendelay_database/1995/Controlling_the_false_discovery_rate_a_practical_and_powe.pdf",
            "Controlling the false discovery rate a practical and powe",
        ),
        (
            "phd/Progress_and_problems_in_the_biology_Diagnostics_2.pdf",
            "Progress and problems in the biology Diagnostics",
        ),
        ("pdfs/Ciechanover 2003 ubiquitin review.pdf", "Ciechanover 2003 ubiquitin review"),
        # no title in these names
        ("doi_10.1016_j.cell.2026.08.035v1.pdf", None),
        ("arxiv_1706.03762v7.pdf", None),
        ("pdfs/13059_2020_Article_2046.pdf", None),
        ("pdfs/2022.05.06.490859v3.full.pdf", None),
        ("pdfs/review1.pdf", None),
        ("pdfs/South_JCB-1999.pdf", None),
        ("pdfs/12_34_5678_9.pdf", None),
        (None, None),
    ],
)
def test_title_from_file(rel, title):
    assert title_from_file(rel) == title


def test_year_from_file():
    assert year_from_file("Mendelay_database/1995/x_y_z.pdf") == 1995
    assert year_from_file("2017/sub/x.pdf") == 2017  # innermost year folder wins
    assert year_from_file("1995.pdf") is None  # the file name is not a folder
    assert year_from_file("1850/x.pdf") is None
    assert year_from_file("9999/x.pdf") is None
    assert year_from_file(None) is None


@pytest.mark.parametrize(
    "title",
    [
        "",
        None,
        "   ",
        "Abstract",
        "253",
        "1654",
        "© 1995 NaturePublishingGroup",
        "dev4172.q",
        "sigmod.dvi",
        "genesdev_1009-1019.TIF",
        "949_1.tif",
        "Figure S1: Figure S1",
        "Supplemental Information 1: Supplemental Results",
        "Ghostscript wrapper for C:\\WINDOWS\\Escritorio\\vol1.pdf",
        '! "#!%$&\' ( )"*,+- #.0/1(. 23',
        "Microsoft Word - manuscript_final",
    ],
)
def test_junk_titles_are_suspect(title):
    assert title_suspect(title, None) is True


def test_title_against_file_name():
    file_title = title_from_file("1960/Cerebellar_and_Midbrain_Lesions_in_Scrapie.pdf")
    assert title_suspect("Nature Publishing Group supports PubChem", file_title) is True
    assert title_suspect("Cerebellar and Midbrain Lesions in Scrapie", file_title) is False
    # a file name cut short still matches the full title
    long = "Controlling the false discovery rate: a practical and powerful approach to testing"
    cut = title_from_file("1995/Controlling_the_false_discovery_rate_a_practical_and_powe.pdf")
    assert title_suspect(long, cut) is False
    # no file title to compare: only the junk rules apply
    assert title_suspect("Attention Is All You Need", None) is False

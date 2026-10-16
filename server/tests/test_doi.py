from __future__ import annotations

import pytest

from app.doi import clean_doi


@pytest.mark.parametrize(
    ("raw", "doi"),
    [
        ("10.1234/x", "10.1234/x"),
        ("10.1234/x;", "10.1234/x"),
        (" 10.1234/x ", "10.1234/x"),
        ("; 10.1234/x ;", "10.1234/x"),
        ("10.1234/x.,;:", "10.1234/x"),
        ("doi: 10.1234/x.", "10.1234/x"),
        ("DOI:10.1234/x", "10.1234/x"),
        ("https://doi.org/10.1234/x;", "10.1234/x"),
        ("(10.1234/x)", "10.1234/x"),
        ("[10.1234/x]", "10.1234/x"),
        ('"10.1234/x"', "10.1234/x"),
        ("<10.1234/x>", "10.1234/x"),
        # Brackets and `;` inside the DOI stay; a closing bracket it opened stays.
        ("10.1002/(SICI)1097-4636;2-x", "10.1002/(SICI)1097-4636;2-x"),
        ("10.1002/(SICI)1097-4636(199)", "10.1002/(SICI)1097-4636(199)"),
        ("10.1002/(SICI)1097-4636(199));", "10.1002/(SICI)1097-4636(199)"),
        ("", ""),
        (None, ""),
        (" ; ", ""),
    ],
)
def test_clean_doi(raw, doi):
    assert clean_doi(raw) == doi

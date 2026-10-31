from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.doi import clean_doi, doi_or_none, is_valid_doi

# Shared with web/src/format.test.ts: both sides must agree on every vector.
VECTORS = json.loads((Path(__file__).parent / "fixtures" / "doi-vectors.json").read_text())


@pytest.mark.parametrize("v", VECTORS, ids=[v["in"] or "<empty>" for v in VECTORS])
def test_doi_vectors(v):
    assert clean_doi(v["in"]) == v["clean"]
    assert is_valid_doi(v["clean"]) is v["valid"]
    assert doi_or_none(v["in"]) == (v["clean"] if v["valid"] else None)


def test_clean_doi_none():
    assert clean_doi(None) == ""
    assert doi_or_none(None) is None

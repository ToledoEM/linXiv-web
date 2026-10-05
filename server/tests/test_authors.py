from __future__ import annotations

from .conftest import fixture


def test_list_authors(client, fake):
    fake.on("author", "list", result=fixture("author-list.json"))
    r = client.get("/api/authors")
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert fake.calls[-1] == ["author", "list"]


def test_hide_single_paper_authors(client, fake):
    fake.on("author", "list", result=fixture("author-list.json"))
    r = client.get("/api/authors", params={"hide_single": "true"})
    assert [a["full_name"] for a in r.json()] == ["Ashish Vaswani"]

from __future__ import annotations

from app.cli import CLIError

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


def test_get_author(client, fake):
    fake.on("author", "get", result=fixture("author-get.json"))
    r = client.get("/api/authors/1")
    assert r.status_code == 200
    assert len(r.json()["papers"]) == 2
    assert fake.calls[-1] == ["author", "get", "--", "1"]
    assert client.get("/api/authors/abc").status_code == 422


def test_get_author_not_found(client, fake):
    fake.on("author", "get", result=CLIError(404, "Author 9 not found"))
    assert client.get("/api/authors/9").status_code == 404


def test_update_author(client, fake):
    fake.on("author", "update", result={"updated_author_id": 2})
    r = client.patch(
        "/api/authors/2",
        json={
            "full_name": " -Noam Shazeer ",
            "first_name": "",
            "orcid": "https://orcid.org/0000000218250097",
        },
    )
    assert r.status_code == 200, r.text
    assert fake.calls[-1] == [
        "author",
        "update",
        "--full-name=-Noam Shazeer",
        "--orcid=0000-0002-1825-0097",
        "--",
        "2",
    ]


def test_update_author_validation(client, fake):
    bad = [
        {},
        {"full_name": " ", "orcid": ""},
        {"orcid": "0000-0002-1825-0098"},
        {"orcid": "garbage"},
        {"full_name": "a\x01b"},
        {"full_name": 5},
        {"nickname": "x"},
    ]
    for body in bad:
        assert client.patch("/api/authors/2", json=body).status_code == 422, body
    assert fake.calls == []


def test_orcid_x_check_digit(client, fake):
    fake.on("author", "update", result={"updated_author_id": 2})
    r = client.patch("/api/authors/2", json={"orcid": "0000-0002-9079-593x"})
    assert r.status_code == 200, r.text
    assert fake.calls[-1][2] == "--orcid=0000-0002-9079-593X"


def test_delete_author(client, fake):
    fake.on("author", "delete", result={"deleted_author_id": 4})
    assert client.delete("/api/authors/4").json() == {"deleted_author_id": 4}
    assert fake.calls[-1] == ["author", "delete", "--", "4"]


def test_delete_linked_author_conflict(client, fake):
    msg = "Author is linked to 1 paper(s); unlink before deleting."
    fake.on("author", "delete", result=CLIError(502, msg))
    r = client.delete("/api/authors/4")
    assert r.status_code == 409
    assert r.json()["detail"] == msg


def test_merge_authors(client, fake):
    fake.on("author", "merge", result={"canonical_id": 5, "merged_ids": [6, 9]})
    r = client.post("/api/authors/5/merge", json={"duplicate_ids": [9, 5, 6, 9]})
    assert r.status_code == 200, r.text
    assert fake.calls[-1] == ["author", "merge", "--", "5", "6", "9"]


def test_merge_authors_validation(client, fake):
    for body in ({"duplicate_ids": []}, {"duplicate_ids": ["6"]}, {}):
        assert client.post("/api/authors/5/merge", json=body).status_code == 422, body
    assert client.post("/api/authors/5/merge", json={"duplicate_ids": [5]}).status_code == 400
    assert fake.calls == []


def test_merge_candidates(client, fake):
    fake.on("author", "merge-candidates", result=fixture("author-merge-candidates.json"))
    fake.on("author", "get", result={"author_id": 5, "full_name": "Llion Jones"})
    listed = fixture("author-list.json") + [
        {"author_id": 6, "full_name": "llion jones ", "orcid": None, "paper_count": 1},
        {"author_id": 7, "full_name": "LLION JONES", "orcid": None, "paper_count": 2},
    ]
    fake.on("author", "list", result=listed)
    r = client.get("/api/authors/5/merge-candidates")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["author_id"] for c in body["candidates"]] == [6]
    assert [c["author_id"] for c in body["name_candidates"]] == [7]
    keys = {"author_id", "orcid", "full_name", "first_name", "last_name"}
    assert set(body["name_candidates"][0]) == keys


def test_orcid_backfill(client, fake):
    fake.on("orcid", "backfill", result=fixture("orcid-backfill.json"))
    r = client.post("/api/orcid/backfill")
    assert r.status_code == 200, r.text
    assert len(r.json()["updated"]) == 11
    assert fake.calls[-1] == ["orcid", "backfill", "--limit=20"]
    client.post("/api/orcid/backfill", json={"limit": 100})
    assert fake.calls[-1] == ["orcid", "backfill", "--limit=100"]


def test_orcid_backfill_validation(client, fake):
    for body in ({"limit": 0}, {"limit": 101}, {"limit": "5"}, {"max": 5}):
        assert client.post("/api/orcid/backfill", json=body).status_code == 422, body
    assert fake.calls == []


def test_orcid_backfill_busy(client, fake):
    fake.on("orcid", "backfill", result=CLIError(502, "an ORCID backfill is already in progress"))
    assert client.post("/api/orcid/backfill").status_code == 409

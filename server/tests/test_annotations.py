from __future__ import annotations

import json

from app.cli import CLIError

SID = "arxiv:1706.03762"
ANCHOR = {
    "v": 1,
    "version": 7,
    "page": 2,
    "color": "#ffd400",
    "quote": "Attention",
    "rects": [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.02}, {"x": 0, "y": 0.25, "w": 1, "h": 0.02}],
}


def _row(id_, anchor=ANCHOR, comment="", project_id=None):
    return {
        "id": id_,
        "uuid": "u",
        "source_fk": 1,
        "project_id": project_id,
        "anchor": json.dumps(anchor),
        "comment": comment,
    }


def test_list(client, fake):
    fake.on("annotation", "list", result=[_row(1)])
    assert len(client.get("/api/annotations", params={"paper": SID}).json()) == 1
    assert fake.calls[-1] == ["annotation", "list", f"--paper-id={SID}"]


def test_create_canonical_anchor(client, fake):
    fake.on("annotation", "create", result={"id": 9, "source_fk": 1, "project_id": 4})
    body = {"source_id": SID, "anchor": ANCHOR, "comment": "-note", "project_id": 4}
    r = client.post("/api/annotations", json=body)
    assert r.status_code == 200, r.text
    argv = fake.calls[-1]
    assert argv[:5] == ["annotation", "create", "--comment=-note", "--project-id=4", "--"]
    assert argv[5] == SID
    assert argv[6].startswith('{"v":1,"version":7,"page":2,"color":"#ffd400","quote":"Attention"')
    assert json.loads(argv[6])["rects"][1] == {"x": 0.0, "y": 0.25, "w": 1.0, "h": 0.02}


def test_create_rejects_bad_anchor(client, fake):
    def with_(**kw):
        return {"source_id": SID, "anchor": {**ANCHOR, **kw}}

    bad = [
        with_(v=2),
        with_(v=True),
        with_(page=0),
        with_(version=-1),
        with_(color="red"),
        with_(color="#ffd40"),
        with_(quote="x" * 10_001),
        with_(rects=[]),
        with_(rects=[{"x": 0.9, "y": 0, "w": 0.2, "h": 0.1}]),
        with_(rects=[{"x": 0, "y": 0, "w": 0, "h": 0.1}]),
        with_(rects=[{"x": "0.1", "y": 0, "w": 0.2, "h": 0.1}]),
        with_(rects=[{"x": 0, "y": 0, "w": 0.1, "h": 0.1}] * 501),
        with_(extra=1),
        {"source_id": SID, "anchor": ANCHOR, "comment": "x" * 100_001},
        {"source_id": "", "anchor": ANCHOR},
    ]
    for body in bad:
        assert client.post("/api/annotations", json=body).status_code == 422, body
    assert fake.calls == []


def test_update_comment(client, fake):
    fake.on("annotation", "update", result={"id": 1, "updated": True})
    assert client.patch("/api/annotations/1", json={"comment": ""}).status_code == 200
    assert fake.calls[-1] == ["annotation", "update", "--comment=", "--", "1"]
    assert client.patch("/api/annotations/1", json={}).status_code == 422
    assert client.patch("/api/annotations/1", json={"color": "#7ac34a"}).status_code == 422


def test_update_color_recreates(client, fake):
    fake.on("annotation", "list", result=[_row(1, comment="keep", project_id=4), _row(2)])
    fake.on("annotation", "create", result={"id": 7, "source_fk": 1, "project_id": 4})
    fake.on("annotation", "delete", result={"deleted_annotation_id": 1})
    r = client.patch("/api/annotations/1", json={"color": "#7ac34a", "source_id": SID})
    assert r.json() == {"id": 7, "replaced": 1}
    create = next(c for c in fake.calls if c[:2] == ["annotation", "create"])
    assert create[2:4] == ["--comment=keep", "--project-id=4"]
    assert json.loads(create[-1])["color"] == "#7ac34a"
    assert fake.calls[-1] == ["annotation", "delete", "--", "1"]
    # create happens before delete
    names = [c[1] for c in fake.calls]
    assert names.index("create") < names.index("delete")


def test_update_color_wrong_paper(client, fake):
    fake.on("annotation", "list", result=[_row(2)])
    r = client.patch("/api/annotations/1", json={"color": "#7ac34a", "source_id": SID})
    assert r.status_code == 404
    assert not [c for c in fake.calls if c[1] in ("create", "delete")]


def test_update_color_invalid_stored_anchor(client, fake):
    fake.on("annotation", "list", result=[{**_row(1), "anchor": "not json"}])
    r = client.patch("/api/annotations/1", json={"color": "#7ac34a", "source_id": SID})
    assert r.status_code == 400


def test_delete(client, fake):
    fake.on("annotation", "delete", result=CLIError(404, "Annotation 9 not found"))
    assert client.delete("/api/annotations/9").status_code == 404

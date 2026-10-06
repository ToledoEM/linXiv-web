from __future__ import annotations

from app.cli import CLIError

from .conftest import fixture

URL = "https://rss.arxiv.org/rss/cs.LG"


def _feed_calls(fake):
    return [c for c in fake.calls if c[:2] == ["feed", "get"]]


def test_feed_not_configured(client, fake):
    fake.on("settings", "get", result={"home_feed_url": None})
    assert client.get("/api/feed").json() == {"configured": False}
    fake.on("settings", "get", result={"home_feed_url": "  "})
    assert client.get("/api/feed").json() == {"configured": False}
    assert _feed_calls(fake) == []


def test_feed_uses_stored_url_and_caches(client, fake):
    fake.on("settings", "get", result={"home_feed_url": URL})
    fake.on("feed", "get", result=fixture("feed-get.json"))
    body = client.get("/api/feed").json()
    assert body["configured"] is True and body["url"] == URL
    assert body["title"] == "cs.LG updates on arXiv.org"
    assert len(body["entries"]) == 3
    assert _feed_calls(fake) == [["feed", "get", "--", URL]]
    client.get("/api/feed")
    assert len(_feed_calls(fake)) == 1
    client.get("/api/feed", params={"refresh": "true"})
    assert len(_feed_calls(fake)) == 2


def test_feed_ignores_url_param(client, fake):
    fake.on("settings", "get", result={"home_feed_url": URL})
    fake.on("feed", "get", result=fixture("feed-get.json"))
    client.get("/api/feed", params={"url": "http://169.254.169.254/"})
    assert _feed_calls(fake) == [["feed", "get", "--", URL]]


def test_feed_fetch_error(client, fake):
    fake.on("settings", "get", result={"home_feed_url": URL})
    fake.on("feed", "get", result=CLIError(502, "feed URL resolves to a private address"))
    r = client.get("/api/feed")
    assert r.status_code == 502
    assert "private address" in r.json()["detail"]


def test_dismiss_prunes_cache(client, fake):
    fake.on("settings", "get", result={"home_feed_url": URL})
    fake.on("feed", "get", result=lambda _: fixture("feed-get.json"))
    fake.on("feed", "dismiss", result={"ok": True})
    client.get("/api/feed")
    r = client.post("/api/feed/dismiss", json={"arxiv_id": "2610.03647", "version": 1})
    assert r.status_code == 200, r.text
    assert fake.calls[-1] == ["feed", "dismiss", "--version=1", "--", "2610.03647"]
    client.post(
        "/api/feed/dismiss",
        json={"arxiv_id": "solv-int/9509007", "version": 2, "permanent": True},
    )
    assert fake.calls[-1][2:] == ["--version=2", "--permanent", "--", "solv-int/9509007"]
    body = client.get("/api/feed").json()
    assert len(_feed_calls(fake)) == 1
    assert "2610.03647" not in [e["arxiv_id"] for e in body["entries"]]
    assert len(body["entries"]) == 2


def test_rule_change_clears_cache(client, fake):
    fake.on("settings", "get", result={"home_feed_url": URL})
    fake.on("feed", "get", result=lambda _: fixture("feed-get.json"))
    fake.on("feed", "rules", "add", result={"rule_id": 1})
    client.get("/api/feed")
    client.post("/api/feed/rules", json={"field": "TITLE", "keywords": "x"})
    client.get("/api/feed")
    assert len(_feed_calls(fake)) == 2


def test_dismiss_validation(client, fake):
    for body in (
        {"arxiv_id": "", "version": 1},
        {"arxiv_id": "--permanent", "version": 1},
        {"arxiv_id": "2610.03647", "version": 0},
        {"arxiv_id": "2610.03647", "version": "1"},
        {"arxiv_id": "2610.03647"},
    ):
        assert client.post("/api/feed/dismiss", json=body).status_code == 422, body
    assert fake.calls == []


def test_rules_crud(client, fake):
    fake.on("feed", "rules", "list", result={"rules": []})
    fake.on("feed", "rules", "add", result={"rule_id": 3})
    fake.on("feed", "rules", "delete", result={"ok": True})
    assert client.get("/api/feed/rules").json() == {"rules": []}
    r = client.post("/api/feed/rules", json={"field": "TITLE", "keywords": " quantum , ,graph "})
    assert r.json() == {"rule_id": 3}
    assert fake.calls[-1] == [
        "feed",
        "rules",
        "add",
        "--field=TITLE",
        "--keywords=quantum,graph",
        "--action=DENY",
    ]
    allow = {"field": "AUTHOR", "keywords": "-Smith", "action": "ALLOW"}
    client.post("/api/feed/rules", json=allow)
    assert fake.calls[-1][-2:] == ["--keywords=-Smith", "--action=ALLOW"]
    assert client.delete("/api/feed/rules/3").json() == {"ok": True}
    assert fake.calls[-1] == ["feed", "rules", "delete", "--", "3"]


def test_rules_validation(client, fake):
    for body in (
        {"field": "BODY", "keywords": "x"},
        {"field": "TITLE", "keywords": ""},
        {"field": "TITLE", "keywords": "x", "action": "deny"},
    ):
        assert client.post("/api/feed/rules", json=body).status_code == 422, body
    blank = {"field": "TITLE", "keywords": " , "}
    assert client.post("/api/feed/rules", json=blank).status_code == 400
    assert fake.calls == []


def test_delete_missing_rule(client, fake):
    fake.on("feed", "rules", "delete", result=CLIError(502, "no such rule"))
    assert client.delete("/api/feed/rules/999").status_code == 404

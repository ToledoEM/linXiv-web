from __future__ import annotations

import asyncio

from app import diagnostics

SECRET = "sk-test-SECRET-0123456789"


def _no_network(monkeypatch):
    async def fake_reach(host, port=443):
        return "ok" if host != "ghcr.io" else "DNS failed (gaierror)"

    monkeypatch.setattr(diagnostics, "reach", fake_reach)


def test_report_redacts_secrets_and_addresses(client, fake, monkeypatch):
    _no_network(monkeypatch)
    monkeypatch.setenv("NCBI_API_KEY", "ncbi-env-key-0001")
    stored = {
        "ai_enabled": True,
        "genai_provider": "generic",
        "genai_base_url": "http://192.168.1.5:11434/v1",
        "home_feed_url": "https://example.org/private-feed?token=abc",
        "GENAI_API_KEY_TAG_GEN": SECRET,
    }
    fake.on("settings", "get", result=stored)
    fake.on("stats", result={"paper_count": 12, "pdf_count": 3, "recent_papers": [{"x": 1}]})
    r = client.get("/api/system/diagnostics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    text = r.text
    for leaked in (SECRET, "ncbi-env-key-0001", "192.168.1.5", "private-feed", "token=abc"):
        assert leaked not in text
    assert "- GENAI_API_KEY_TAG_GEN: set (settings)" in text
    assert "- NCBI_API_KEY: set (env)" in text
    assert "- genai_base_url: set" in text
    assert "- paper_count: 12" in text
    assert "recent_papers" not in text
    assert "- ghcr.io: DNS failed (gaierror)" in text
    assert "- linXiv-web: 0.1.0" in text


def test_report_when_cli_down(client, fake, monkeypatch):
    from app.cli import CLIError

    _no_network(monkeypatch)
    fake.on("settings", "get", result=CLIError(502, "boom"))
    fake.on("stats", result=CLIError(502, "boom"))
    text = client.get("/api/system/diagnostics").text
    assert "linxiv CLI did not answer `stats`" in text
    assert "linxiv CLI not responding" in text


def test_reach_reports_failure_type():
    # An unresolvable name (.invalid is reserved) fails at DNS, without the network.
    assert asyncio.run(diagnostics.reach("nothing.invalid")).startswith("DNS failed")

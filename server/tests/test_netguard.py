from __future__ import annotations

import logging
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.__main__ import check
from app.main import create_app
from app.netguard import client_ip, is_private, parse_networks

PROXY = parse_networks(["10.0.0.2", "172.16.0.0/12"])


@pytest.mark.parametrize(
    ("host", "private"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("192.168.1.20", True),
        ("10.8.0.3", True),
        ("172.20.0.1", True),
        ("fd00::5", True),
        ("fe80::1", True),
        ("169.254.10.1", True),
        ("::ffff:192.168.1.2", True),
        ("93.184.216.34", False),
        ("8.8.8.8", False),
        ("2001:4860::8888", False),
        ("::ffff:8.8.8.8", False),
        ("testclient", False),
        ("", False),
    ],
)
def test_is_private(host, private):
    assert is_private(host) is private


def test_client_ip_ignores_header_from_untrusted_peer():
    assert client_ip("93.184.216.34", "127.0.0.1", PROXY) == "93.184.216.34"
    assert client_ip("192.168.1.5", "127.0.0.1", []) == "192.168.1.5"


def test_client_ip_reads_header_from_the_right():
    # Client forged "127.0.0.1"; the proxy appended the real address.
    assert client_ip("10.0.0.2", "127.0.0.1, 93.184.216.34", PROXY) == "93.184.216.34"
    # Chained trusted proxies are skipped.
    assert client_ip("10.0.0.2", "1.1.1.1, 172.18.0.4", PROXY) == "1.1.1.1"
    # Only trusted hops: the leftmost is the best guess.
    assert client_ip("10.0.0.2", "172.18.0.4", PROXY) == "172.18.0.4"
    assert client_ip("10.0.0.2", "", PROXY) == "10.0.0.2"
    # Junk in the header is returned as-is, and junk is never private.
    assert client_ip("10.0.0.2", "nonsense", PROXY) == "nonsense"


def test_parse_networks_rejects_junk():
    with pytest.raises(ValueError, match="'proxy.lan'"):
        parse_networks(["10.0.0.1", "proxy.lan"])


def _client(settings, fake, addr, **kw) -> TestClient:
    s = replace(settings, **{"allow_external": False, **kw})
    return TestClient(create_app(s, fake), client=(addr, 40000))


def test_public_client_refused(settings, fake, caplog):
    c = _client(settings, fake, "93.184.216.34")
    with caplog.at_level(logging.WARNING, logger="app.netguard"):
        for _ in range(3):
            r = c.get("/api/health")
            assert r.status_code == 403
            assert "LINXIV_WEB_ALLOW_EXTERNAL" in r.json()["detail"]
    blocked = [r for r in caplog.records if "blocked external request" in r.getMessage()]
    assert len(blocked) == 1  # rate-limited per address


@pytest.mark.parametrize("addr", ["127.0.0.1", "192.168.1.20", "10.8.0.3"])
def test_private_client_served(settings, fake, addr):
    assert _client(settings, fake, addr).get("/api/health").status_code == 200


def test_allow_external(settings, fake):
    c = _client(settings, fake, "93.184.216.34", allow_external=True)
    assert c.get("/api/health").status_code == 200


def test_forwarded_header_needs_trusted_proxy(settings, fake):
    spoof = {"X-Forwarded-For": "127.0.0.1"}
    assert (
        _client(settings, fake, "93.184.216.34").get("/api/health", headers=spoof).status_code
        == 403
    )
    proxied = _client(settings, fake, "10.0.0.2", trusted_proxies=("10.0.0.2",))
    real = {"X-Forwarded-For": "127.0.0.1, 93.184.216.34"}
    assert proxied.get("/api/health", headers=real).status_code == 403
    lan = {"X-Forwarded-For": "192.168.1.30"}
    assert proxied.get("/api/health", headers=lan).status_code == 200


def test_untrusted_proxy_counts_as_the_client(settings, fake):
    # Proxy on the LAN but not listed: every request looks like the proxy.
    c = _client(settings, fake, "172.17.0.1")
    assert c.get("/api/health", headers={"X-Forwarded-For": "93.184.216.34"}).status_code == 200


def test_bad_trusted_proxy_fails_startup(settings, capsys):
    with pytest.raises(SystemExit):
        check(replace(settings, trusted_proxies=("not-an-ip",)))
    assert "LINXIV_WEB_TRUSTED_PROXIES" in capsys.readouterr().err

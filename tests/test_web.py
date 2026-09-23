import socket
import threading

import pytest

from osint_toolbox_mcp import web


def fake_proxy(*replies: bytes) -> tuple[socket.socket, list[bytes]]:
    """One end of a socket pair for the client; the other answers each read with the next canned reply."""
    client, proxy = socket.socketpair()
    received: list[bytes] = []

    def serve() -> None:
        for reply in replies:
            received.append(proxy.recv(1024))
            proxy.sendall(reply)
        proxy.close()

    threading.Thread(target=serve, daemon=True).start()
    return client, received


def test_socks5_connect_sends_the_host_name():
    client, received = fake_proxy(b"\x05\x00", b"\x05\x00\x00\x01" + bytes(4) + b"\x01\xbb")
    web._socks5_connect(client, "rdap.org", 443)
    client.close()
    assert received[0] == b"\x05\x01\x00"
    assert received[1] == b"\x05\x01\x00\x03\x08rdap.org\x01\xbb"


def test_socks5_username_and_password():
    client, received = fake_proxy(b"\x05\x02", b"\x01\x00", b"\x05\x00\x00\x03\x04host\x00\x50")
    web._socks5_connect(client, "example.com", 80, "user", "secret")
    client.close()
    assert received[1] == b"\x01\x04user\x06secret"


def test_socks5_refused_connection():
    client, _ = fake_proxy(b"\x05\x00", b"\x05\x05\x00\x01" + bytes(6))
    with pytest.raises(OSError, match="could not connect"):
        web._socks5_connect(client, "example.com", 443)
    client.close()


@pytest.mark.parametrize(
    ("variables", "scheme"),
    [
        ({"HTTPS_PROXY": "http://127.0.0.1:8080"}, "http"),
        ({"ALL_PROXY": "socks5h://127.0.0.1:1080"}, "socks5h"),
        ({"HTTPS_PROXY": "127.0.0.1:3128"}, "http"),
    ],
)
def test_proxy_from_the_environment(monkeypatch, variables, scheme):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    assert web.proxy_for("https://rdap.org/domain/example.com").scheme == scheme


def test_no_proxy_is_respected(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8080")
    monkeypatch.setenv("NO_PROXY", "rdap.org")
    monkeypatch.setenv("no_proxy", "rdap.org")
    assert web.proxy_for("https://rdap.org/domain/example.com") is None

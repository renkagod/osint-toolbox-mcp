"""HTTP for the built-in lookups and the installer, with the standard library only.

Honors HTTP_PROXY, HTTPS_PROXY, ALL_PROXY and NO_PROXY, including socks5:// and socks5h:// proxies,
which urllib doesn't support on its own.
"""

from __future__ import annotations

import functools
import http.client
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__

USER_AGENT = f"osint-toolbox-mcp/{__version__} (+https://github.com/renkagod/osint-toolbox-mcp)"


class WebError(Exception):
    """A request that failed: unreachable host, HTTP error status or an unreadable answer."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def fetch(url: str, *, headers: dict[str, str] | None = None, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with _opener(url).open(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise WebError(f"{_site(url)} answered HTTP {error.code}", error.code) from error
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        raise WebError(f"{_site(url)} could not be reached: {getattr(error, 'reason', error)}") from error


def fetch_json(url: str, **options: Any) -> Any:
    try:
        return json.loads(fetch(url, **options))
    except ValueError as error:
        raise WebError(f"{_site(url)} did not answer with JSON") from error


def proxy_for(url: str) -> urllib.parse.SplitResult | None:
    """The proxy the environment sets for this URL, if any."""
    parts = urllib.parse.urlsplit(url)
    proxies = urllib.request.getproxies()
    proxy = proxies.get(parts.scheme) or proxies.get("all")
    if not proxy or urllib.request.proxy_bypass(parts.hostname or ""):
        return None
    if "://" not in proxy:
        proxy = f"http://{proxy}"
    return urllib.parse.urlsplit(proxy)


def open_socket(host: str, port: int, timeout: float) -> socket.socket:
    """A TCP connection, through the SOCKS5 proxy from ALL_PROXY when there is one (WHOIS uses it)."""
    proxy = proxy_for(f"socks://{host}:{port}")
    if proxy and proxy.scheme in ("socks5", "socks5h"):
        return _socks5_socket(proxy, host, port, timeout)
    return socket.create_connection((host, port), timeout)


def _site(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or url


def _opener(url: str) -> urllib.request.OpenerDirector:
    proxy = proxy_for(url)
    if proxy is None:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if proxy.scheme in ("socks5", "socks5h"):
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _SocksHTTPHandler(proxy), _SocksHTTPSHandler(proxy)
        )
    address = proxy.geturl()
    return urllib.request.build_opener(urllib.request.ProxyHandler({"http": address, "https": address}))


def _socks5_socket(proxy: urllib.parse.SplitResult, host: str, port: int, timeout: float | None) -> socket.socket:
    sock = socket.create_connection((proxy.hostname, proxy.port or 1080), timeout)
    try:
        _socks5_connect(
            sock,
            host,
            port,
            urllib.parse.unquote(proxy.username or ""),
            urllib.parse.unquote(proxy.password or ""),
        )
    except BaseException:
        sock.close()
        raise
    return sock


def _socks5_connect(sock: socket.socket, host: str, port: int, username: str = "", password: str = "") -> None:
    """RFC 1928 CONNECT, with the host name resolved by the proxy (socks5h semantics)."""
    methods = b"\x00\x02" if username else b"\x00"
    sock.sendall(b"\x05" + bytes([len(methods)]) + methods)
    version, method = _receive(sock, 2)
    if version != 5:
        raise OSError("the proxy doesn't speak SOCKS5")
    if method == 2:
        user, secret = username.encode(), password.encode()
        sock.sendall(b"\x01" + bytes([len(user)]) + user + bytes([len(secret)]) + secret)
        if _receive(sock, 2)[1] != 0:
            raise OSError("the SOCKS5 proxy rejected the username or password")
    elif method != 0:
        raise OSError("the SOCKS5 proxy wants an authentication method this client doesn't support")

    name = host.encode("idna")
    sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + port.to_bytes(2, "big"))
    reply = _receive(sock, 4)
    if reply[1] != 0:
        raise OSError(f"the SOCKS5 proxy could not connect to {host}:{port} (error {reply[1]})")
    address_length = {1: 4, 4: 16}.get(reply[3])
    if address_length is None:
        address_length = _receive(sock, 1)[0]
    _receive(sock, address_length + 2)


def _receive(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise OSError("the SOCKS5 proxy closed the connection")
        data += chunk
    return data


class _SocksHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args: Any, proxy: urllib.parse.SplitResult, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._proxy = proxy

    def connect(self) -> None:
        self.sock = _socks5_socket(self._proxy, self.host, self.port, self.timeout)


class _SocksHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args: Any, proxy: urllib.parse.SplitResult, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._proxy = proxy

    def connect(self) -> None:
        sock = _socks5_socket(self._proxy, self.host, self.port, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _SocksHTTPHandler(urllib.request.HTTPHandler):
    def __init__(self, proxy: urllib.parse.SplitResult) -> None:
        super().__init__()
        self._proxy = proxy

    def http_open(self, request: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_SocksHTTPConnection, proxy=self._proxy), request)


class _SocksHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, proxy: urllib.parse.SplitResult) -> None:
        super().__init__()
        self._proxy = proxy

    def https_open(self, request: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_SocksHTTPSConnection, proxy=self._proxy), request)

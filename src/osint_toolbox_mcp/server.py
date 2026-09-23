"""MCP over stdio: message framing, protocol versions and request routing."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
import threading
from typing import Any

from . import __version__, check, install
from .tools import TOOLS, TOOLS_BY_NAME, ToolError, available_tools, call_tool

SERVER_INFO = {"name": "osint-toolbox-mcp", "title": "OSINT Toolbox", "version": __version__}

# Stateless revisions: every request carries its protocol version in _meta
MODERN_VERSIONS = ("2026-07-28",)
# Revisions negotiated with the initialize handshake, newest first
HANDSHAKE_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_VERSION = -32022

SHUTDOWN_GRACE = 2.0  # seconds requests still get after the client closes stdin

INSTRUCTIONS = (
    "Each tool runs a local OSINT program against public sources and returns what it found. "
    "Runs take from seconds (Holehe) to many minutes (Maigret with all_sites, SpiderFoot 'all'). "
    "Use them only for lawful, authorized research."
)


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


async def handle(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """The result of one request. Modern requests name their protocol version in _meta; the rest are handshake-era."""
    if method == "initialize":
        return _initialize(params)
    meta = params.get("_meta")
    version = meta.get(VERSION_KEY) if isinstance(meta, dict) else None
    if version is None:
        if method == "server/discover":
            raise RpcError(INVALID_PARAMS, f"server/discover needs {VERSION_KEY} in _meta")
        return await _handshake_era(method, params)

    if version not in MODERN_VERSIONS:
        raise RpcError(
            UNSUPPORTED_VERSION,
            "Unsupported protocol version",
            {"supported": [*MODERN_VERSIONS, *HANDSHAKE_VERSIONS], "requested": version},
        )
    if not isinstance(meta.get(CAPABILITIES_KEY), dict):
        raise RpcError(INVALID_PARAMS, f"_meta must include {CAPABILITIES_KEY}")
    result = await _modern_era(method, params)
    result["resultType"] = "complete"
    result["_meta"] = {SERVER_INFO_KEY: SERVER_INFO}
    return result


def _initialize(params: dict[str, Any]) -> dict[str, Any]:
    requested = params.get("protocolVersion")
    return {
        "protocolVersion": requested if requested in HANDSHAKE_VERSIONS else HANDSHAKE_VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


async def _handshake_era(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [tool.definition() for tool in available_tools()]}
    if method == "tools/call":
        return await _call(params)
    raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")


async def _modern_era(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "server/discover":
        return {
            "supportedVersions": list(MODERN_VERSIONS),
            "capabilities": {"tools": {}},
            "instructions": INSTRUCTIONS,
            "ttlMs": 3_600_000,
            "cacheScope": "public",
        }
    if method == "tools/list":
        # The list follows what is installed right now, so clients shouldn't cache it
        return {"tools": [tool.definition() for tool in available_tools()], "ttlMs": 0, "cacheScope": "public"}
    if method == "tools/call":
        return await _call(params)
    raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")


async def _call(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(name, str) or name not in TOOLS_BY_NAME:
        raise RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise RpcError(INVALID_PARAMS, "Tool arguments must be an object")
    try:
        text, is_error = await call_tool(TOOLS_BY_NAME[name], arguments), False
    except ToolError as error:
        text, is_error = str(error), True
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class Server:
    """JSON-RPC over stdio. Requests run concurrently, so a long scan doesn't hold up the rest."""

    def __init__(self) -> None:
        self.in_flight: dict[Any, asyncio.Task] = {}
        self.batches: set[asyncio.Task] = set()

    def send(self, message: Any) -> None:
        # Only the event loop thread writes, so messages never interleave
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def receive(self, line: str) -> None:
        try:
            message = json.loads(line)
        except ValueError as error:
            self.send(error_response(None, PARSE_ERROR, f"Parse error: {error}"))
            return
        if isinstance(message, list):
            self._receive_batch(message)
            return
        reply = self._accept(message)
        if isinstance(reply, asyncio.Task):
            reply.add_done_callback(self._send_result)
        elif reply is not None:
            self.send(reply)

    def _send_result(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.result() is not None:
            self.send(task.result())

    def _receive_batch(self, messages: list[Any]) -> None:
        """JSON-RPC batches (protocol 2025-03-26): one array of replies once every request in it is done."""
        if not messages:
            self.send(error_response(None, INVALID_REQUEST, "Empty batch"))
            return
        replies = [self._accept(message) for message in messages]

        async def reply_when_done() -> None:
            await asyncio.gather(*(r for r in replies if isinstance(r, asyncio.Task)), return_exceptions=True)
            responses = []
            for reply in replies:
                if isinstance(reply, asyncio.Task):
                    reply = None if reply.cancelled() else reply.result()
                if reply is not None:
                    responses.append(reply)
            if responses:
                self.send(responses)

        task = asyncio.create_task(reply_when_done())
        self.batches.add(task)
        task.add_done_callback(self.batches.discard)

    def _accept(self, message: Any) -> asyncio.Task | dict[str, Any] | None:
        """Start on one message: a task for a request, an error reply if it's malformed, None otherwise."""
        if not isinstance(message, dict):
            return error_response(None, INVALID_REQUEST, "Expected a JSON-RPC object")
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params")
        if params is None:
            params = {}
        if not isinstance(method, str):
            if "result" in message or "error" in message:
                return None  # a reply to a request this server never sends
            return error_response(request_id if _valid_id(request_id) else None, INVALID_REQUEST, "Invalid Request")

        if request_id is None:
            # Notifications never get a reply; a cancel stops the matching request
            if method == "notifications/cancelled" and isinstance(params, dict):
                cancelled = params.get("requestId")
                task = self.in_flight.get(cancelled) if _valid_id(cancelled) else None
                if task:
                    task.cancel()
            return None
        if not _valid_id(request_id):
            return error_response(None, INVALID_REQUEST, "Request id must be a string or a number")
        if not isinstance(params, dict):
            return error_response(request_id, INVALID_PARAMS, "params must be an object")

        task = asyncio.create_task(self._respond(request_id, method, params))
        self.in_flight[request_id] = task
        task.add_done_callback(lambda done: self._forget(request_id, done))
        return task

    def _forget(self, request_id: Any, task: asyncio.Task) -> None:
        if self.in_flight.get(request_id) is task:
            del self.in_flight[request_id]

    async def _respond(self, request_id: Any, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            result = await handle(method, params)
        except asyncio.CancelledError:
            return None  # cancelled by the client: MCP expects no response
        except RpcError as error:
            return error_response(request_id, error.code, error.message, error.data)
        except Exception as error:
            return error_response(request_id, INTERNAL_ERROR, f"Internal error: {error}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    async def serve(self) -> None:
        loop = asyncio.get_running_loop()
        lines: asyncio.Queue[str | None] = asyncio.Queue()
        _read_stdin(loop, lines)
        try:
            loop.add_signal_handler(signal.SIGTERM, lines.put_nowait, None)
        except (NotImplementedError, AttributeError):
            pass  # Windows: the client stops the server by closing stdin or ending the process
        try:
            while (line := await lines.get()) is not None:
                if line.strip():
                    self.receive(line)
        finally:
            # The client went away: let quick requests finish, then stop the scans that are still running
            if self.in_flight:
                await asyncio.wait(list(self.in_flight.values()), timeout=SHUTDOWN_GRACE)
            for task in list(self.in_flight.values()):
                task.cancel()
            await asyncio.gather(*self.in_flight.values(), *self.batches, return_exceptions=True)


def _valid_id(value: Any) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _read_stdin(loop: asyncio.AbstractEventLoop, lines: asyncio.Queue[str | None]) -> None:
    """Feed stdin to the loop from a daemon thread, so a blocked read never holds up shutdown."""

    def pump() -> None:
        try:
            for line in sys.stdin:
                loop.call_soon_threadsafe(lines.put_nowait, line)
            loop.call_soon_threadsafe(lines.put_nowait, None)
        except RuntimeError:
            pass  # the loop has already closed

    threading.Thread(target=pump, name="stdin", daemon=True).start()


def _log_tools() -> None:
    ready = {tool.label for tool in available_tools()}
    missing = [tool.label for tool in TOOLS if tool.label not in ready]
    message = f"osint-toolbox-mcp {__version__}: {len(ready)} of {len(TOOLS)} tools available"
    if missing:
        message += f"; missing: {', '.join(missing)} (install them with `osint-toolbox-mcp --install`)"
    print(message, file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="osint-toolbox-mcp",
        description=(
            "MCP server (stdio) that lets AI agents run OSINT tools: Sherlock, Maigret, Blackbird, Holehe, GHunt, "
            "theHarvester, SpiderFoot, subfinder, dnstwist, dnsrecon, PhoneInfoga, ExifTool, plus built-in WHOIS, "
            "DNS, certificate transparency and Wayback Machine lookups."
        ),
    )
    parser.add_argument("--check", action="store_true", help="show which tools are installed and working, then exit")
    parser.add_argument(
        "--install",
        nargs="*",
        metavar="TOOL",
        help="install the missing tools (all of them, or the ones named, e.g. sherlock maigret), then check them",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.check or args.install is not None:
        sys.stdout.reconfigure(errors="replace")
        if args.install is not None:
            raise SystemExit(asyncio.run(install.run(args.install)))
        raise SystemExit(asyncio.run(check.run()))

    # MCP messages are UTF-8 lines ending in \n, whatever the platform's defaults are
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    _log_tools()
    try:
        asyncio.run(Server().serve())
    except KeyboardInterrupt:
        pass

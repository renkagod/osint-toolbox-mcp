import asyncio

import pytest
from conftest import fake_executable

from osint_toolbox_mcp import __version__, server
from osint_toolbox_mcp.server import HANDSHAKE_VERSIONS, MODERN_VERSIONS, RpcError, Server, handle

MODERN_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
}


def call(method, params=None):
    return asyncio.run(handle(method, params or {}))


def rpc_error(method, params=None) -> RpcError:
    with pytest.raises(RpcError) as caught:
        call(method, params)
    return caught.value


# Handshake era

@pytest.mark.parametrize("version", HANDSHAKE_VERSIONS)
def test_initialize_accepts_every_handshake_version(version):
    assert call("initialize", {"protocolVersion": version})["protocolVersion"] == version


@pytest.mark.parametrize("version", ["2099-01-01", "2026-07-28", None])
def test_initialize_counter_offers_the_newest_handshake_version(version):
    assert call("initialize", {"protocolVersion": version})["protocolVersion"] == HANDSHAKE_VERSIONS[0]


def test_initialize_describes_the_server():
    result = call("initialize", {"protocolVersion": "2025-11-25"})
    assert result["serverInfo"] == {"name": "osint-toolbox-mcp", "title": "OSINT Toolbox", "version": __version__}
    assert "tools" in result["capabilities"]
    assert result["instructions"]


def test_ping():
    assert call("ping") == {}


def test_handshake_era_results_have_no_modern_fields():
    result = call("tools/list")
    assert set(result) == {"tools"}


# Stateless era (2026-07-28)

def test_discover():
    result = call("server/discover", {"_meta": MODERN_META})
    assert result["supportedVersions"] == list(MODERN_VERSIONS)
    assert result["capabilities"] == {"tools": {}}
    assert result["resultType"] == "complete"
    assert result["cacheScope"] == "public"
    assert result["ttlMs"] >= 0
    assert result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "osint-toolbox-mcp"


def test_modern_tools_list():
    result = call("tools/list", {"_meta": MODERN_META})
    assert result["resultType"] == "complete"
    assert result["ttlMs"] == 0
    assert result["tools"] == []


def test_unsupported_version_names_every_supported_one():
    meta = {**MODERN_META, "io.modelcontextprotocol/protocolVersion": "2099-01-01"}
    error = rpc_error("tools/list", {"_meta": meta})
    assert error.code == -32022
    assert error.data == {"supported": [*MODERN_VERSIONS, *HANDSHAKE_VERSIONS], "requested": "2099-01-01"}


def test_modern_request_needs_client_capabilities():
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
    assert rpc_error("tools/list", {"_meta": meta}).code == -32602


def test_discover_needs_a_protocol_version():
    assert rpc_error("server/discover").code == -32602


@pytest.mark.parametrize("params", [{}, {"_meta": MODERN_META}])
def test_unknown_method(params):
    assert rpc_error("resources/list", params).code == -32601


# Tools

def test_tools_list_shows_only_installed_tools(isolated_tools):
    fake_executable(isolated_tools, "holehe")
    names = [tool["name"] for tool in call("tools/list")["tools"]]
    assert names == ["holehe_email_search"]


def test_tool_definition(isolated_tools):
    fake_executable(isolated_tools, "exiftool")
    (tool,) = call("tools/list")["tools"]
    assert tool["inputSchema"]["required"] == ["file_path"]
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["annotations"]["openWorldHint"] is False


def test_unknown_tool():
    assert rpc_error("tools/call", {"name": "nmap"}).code == -32602


def test_arguments_must_be_an_object():
    assert rpc_error("tools/call", {"name": "holehe_email_search", "arguments": ["x"]}).code == -32602


def test_missing_tool_is_a_tool_error():
    result = call("tools/call", {"name": "sherlock_username_search", "arguments": {"username": "alice"}})
    assert result["isError"] is True
    assert "uv tool install sherlock-project" in result["content"][0]["text"]


def test_bad_input_is_a_tool_error(isolated_tools):
    fake_executable(isolated_tools, "sherlock")
    result = call("tools/call", {"name": "sherlock_username_search", "arguments": {"username": "--output=/tmp/x"}})
    assert result["isError"] is True
    assert "must not start with '-'" in result["content"][0]["text"]


# Framing, batches and cancellation

async def settle(srv: Server) -> None:
    await asyncio.gather(*srv.in_flight.values(), *srv.batches, return_exceptions=True)
    await asyncio.sleep(0)


def serve_lines(*lines: str) -> list:
    sent = []

    async def scenario():
        srv = Server()
        srv.send = sent.append
        for line in lines:
            srv.receive(line)
        await settle(srv)

    asyncio.run(scenario())
    return sent


def test_parse_error():
    (reply,) = serve_lines("{not json")
    assert reply["error"]["code"] == -32700
    assert reply["id"] is None


def test_non_object_is_an_invalid_request():
    (reply,) = serve_lines("42")
    assert reply["error"]["code"] == -32600


def test_notifications_and_client_replies_get_no_reply():
    assert serve_lines(
        '{"jsonrpc": "2.0", "method": "notifications/initialized"}',
        '{"jsonrpc": "2.0", "id": 7, "result": {}}',
    ) == []


def test_request_reply():
    (reply,) = serve_lines('{"jsonrpc": "2.0", "id": "a", "method": "ping"}')
    assert reply == {"jsonrpc": "2.0", "id": "a", "result": {}}


def test_invalid_request_id():
    (reply,) = serve_lines('{"jsonrpc": "2.0", "id": [1], "method": "ping"}')
    assert reply["error"]["code"] == -32600


def test_batch():
    (reply,) = serve_lines(
        '[{"jsonrpc": "2.0", "id": 1, "method": "ping"},'
        ' {"jsonrpc": "2.0", "method": "notifications/initialized"},'
        ' {"jsonrpc": "2.0", "id": 2, "method": "nope"}]'
    )
    assert [item["id"] for item in reply] == [1, 2]
    assert reply[1]["error"]["code"] == -32601


def test_empty_batch():
    (reply,) = serve_lines("[]")
    assert reply["error"]["code"] == -32600


def test_cancel_stops_the_request_without_a_reply(monkeypatch):
    started, stopped = asyncio.Event(), []

    async def endless(tool, arguments):
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            stopped.append(tool.name)
            raise

    monkeypatch.setattr(server, "call_tool", endless)
    sent = []

    async def scenario():
        srv = Server()
        srv.send = sent.append
        srv.receive('{"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "holehe_email_search"}}')
        await started.wait()
        srv.receive('{"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 5}}')
        await settle(srv)
        assert srv.in_flight == {}

    asyncio.run(scenario())
    assert stopped == ["holehe_email_search"]
    assert sent == []


def test_end_of_input_cancels_running_requests(monkeypatch):
    stopped = []

    async def endless(tool, arguments):
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            stopped.append(tool.name)
            raise

    def fake_stdin(loop, lines):
        lines.put_nowait('{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "maigret_username_search"}}')
        loop.call_later(0.2, lines.put_nowait, None)

    monkeypatch.setattr(server, "call_tool", endless)
    monkeypatch.setattr(server, "_read_stdin", fake_stdin)
    monkeypatch.setattr(server, "SHUTDOWN_GRACE", 0.1)
    srv = Server()
    srv.send = lambda message: None
    asyncio.run(asyncio.wait_for(srv.serve(), 10))
    assert stopped == ["maigret_username_search"]

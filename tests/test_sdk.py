"""Interoperability with the official MCP Python SDK (2.x): both the stateless and the handshake era."""

import asyncio
import sys

import pytest
from conftest import server_env

mcp = pytest.importorskip("mcp")
if not hasattr(mcp, "Client"):
    pytest.skip("needs version 2 of the MCP Python SDK", allow_module_level=True)


@pytest.mark.parametrize("mode", ["auto", "legacy", "2026-07-28"])
def test_sdk_client(mode):
    params = mcp.StdioServerParameters(command=sys.executable, args=["-m", "osint_toolbox_mcp"], env=server_env())

    async def session():
        async with mcp.Client(params, mode=mode) as client:
            listed = await client.list_tools()
            called = await client.call_tool("holehe_email_search", {"email": "not-an-email"})
            return listed, called

    listed, called = asyncio.run(session())
    assert isinstance(listed.tools, list)
    assert called.is_error

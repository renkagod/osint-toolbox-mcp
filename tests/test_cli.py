"""The installed entry point, run as a real subprocess."""

import json
import subprocess
import sys

from conftest import server_env

from osint_toolbox_mcp import __version__
from osint_toolbox_mcp.tools import TOOLS

SERVER = [sys.executable, "-m", "osint_toolbox_mcp"]


def test_version():
    done = subprocess.run([*SERVER, "--version"], capture_output=True, text=True, env=server_env(), timeout=60)
    assert done.stdout.strip() == f"osint-toolbox-mcp {__version__}"


def test_check_lists_every_tool(tmp_path):
    env = server_env(PATH=str(tmp_path), HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    done = subprocess.run([*SERVER, "--check"], capture_output=True, text=True, env=env, timeout=300)
    assert done.returncode in (0, 1)
    for tool in TOOLS:
        if tool.requires is None:
            assert tool.name in done.stdout
        else:
            assert f" {tool.label} " in done.stdout
    assert "tools ready." in done.stdout


def test_stdio_session():
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "server/discover",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        },
    ]
    stdin = "".join(json.dumps(message) + "\n" for message in messages)
    done = subprocess.run(SERVER, input=stdin.encode(), capture_output=True, env=server_env(), timeout=60)
    assert done.returncode == 0
    replies = {reply["id"]: reply for reply in map(json.loads, done.stdout.decode().splitlines())}
    assert set(replies) == {1, 2, 3}
    assert replies[1]["result"]["protocolVersion"] == "2025-06-18"
    assert isinstance(replies[2]["result"]["tools"], list)
    assert replies[3]["result"]["supportedVersions"] == ["2026-07-28"]
    assert b"\r\n" not in done.stdout

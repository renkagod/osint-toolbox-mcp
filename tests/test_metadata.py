"""Release metadata that has to agree with the code: versions, registry entry, bundle manifest."""

import json
import re
from pathlib import Path

from osint_toolbox_mcp import __version__
from osint_toolbox_mcp.tools import TOOLS, TOOLS_BY_NAME

ROOT = Path(__file__).resolve().parents[1]
SERVER_JSON = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8"))


def test_every_version_matches_the_package():
    assert SERVER_JSON["version"] == __version__
    for package in SERVER_JSON["packages"]:
        if package["registryType"] == "oci":
            assert package["identifier"].endswith(f":{__version__}")
        else:
            assert package["version"] == __version__
    assert MANIFEST["version"] == __version__
    bundle_project = (ROOT / "mcpb" / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'^version = "{re.escape(__version__)}"$', bundle_project, re.MULTILINE)


def test_changelog_has_the_version():
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_registry_entry():
    assert len(SERVER_JSON["description"]) <= 100
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"mcp-name: {SERVER_JSON['name']}" in readme


def test_bundle_manifest_lists_every_tool():
    assert [tool["name"] for tool in MANIFEST["tools"]] == [tool.name for tool in TOOLS]


def test_documented_variables_are_the_ones_the_server_reads():
    read = {
        getattr(tool.requires, "env", None) or tool.requires.dir_env
        for tool in TOOLS_BY_NAME.values()
        if tool.requires is not None
    }
    documented = {variable["name"] for variable in SERVER_JSON["packages"][0]["environmentVariables"]}
    assert documented <= read
    assert set(MANIFEST["server"]["mcp_config"]["env"]) <= read

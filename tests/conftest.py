import os
import sys
from pathlib import Path

import pytest

from osint_toolbox_mcp import locate

SRC = Path(__file__).resolve().parents[1] / "src"
REAL_SEARCH_PATH = locate.search_path


@pytest.fixture(autouse=True)
def isolated_tools(monkeypatch, tmp_path):
    """Tests see only the tools they create in tmp_path/bin, never the ones installed on the machine."""
    for name in list(os.environ):
        if name.startswith("OSINT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("OSINT_TOOLBOX_HOME", str(tmp_path / "toolbox"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(locate, "search_path", lambda: str(bin_dir))
    return bin_dir


def fake_executable(folder: Path, name: str) -> Path:
    """An empty file that PATH lookup accepts as a program."""
    path = folder / (f"{name}.exe" if sys.platform == "win32" else name)
    path.write_text("")
    path.chmod(0o755)
    return path


def server_env(**extra: str) -> dict[str, str]:
    """Environment for running the server as a subprocess from this checkout."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("OSINT_")}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(SRC), env.get("PYTHONPATH")]))
    env.update(extra)
    return env

import os
import sys
from pathlib import Path

from conftest import REAL_SEARCH_PATH, fake_executable

from osint_toolbox_mcp.locate import Program, Script, locate

SHERLOCK = Program(("sherlock",), "OSINT_SHERLOCK")
SPIDERFOOT = Script("sf.py", "OSINT_SPIDERFOOT_DIR", "OSINT_SPIDERFOOT_PYTHON")


def test_program_on_the_search_path(isolated_tools):
    path = fake_executable(isolated_tools, "sherlock")
    located, _ = locate(SHERLOCK)
    assert Path(located.command[0]) == path
    assert located.cwd is None


def test_missing_program():
    located, reason = locate(SHERLOCK)
    assert located is None
    assert reason == "not found"


def test_program_override(monkeypatch, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    path = fake_executable(elsewhere, "sherlock-custom")
    monkeypatch.setenv("OSINT_SHERLOCK", str(path))
    located, _ = locate(SHERLOCK)
    assert Path(located.command[0]) == path


def test_broken_override_is_explained(monkeypatch, isolated_tools, tmp_path):
    fake_executable(isolated_tools, "sherlock")
    monkeypatch.setenv("OSINT_SHERLOCK", str(tmp_path / "nope"))
    located, reason = locate(SHERLOCK)
    assert located is None
    assert "OSINT_SHERLOCK" in reason


def test_script_needs_its_folder(monkeypatch, tmp_path):
    assert locate(SPIDERFOOT) == (None, "OSINT_SPIDERFOOT_DIR is not set")
    monkeypatch.setenv("OSINT_SPIDERFOOT_DIR", str(tmp_path))
    located, reason = locate(SPIDERFOOT)
    assert located is None
    assert "has no sf.py" in reason


def test_script_prefers_the_checkout_venv(monkeypatch, tmp_path):
    (tmp_path / "sf.py").write_text("")
    venv_python = tmp_path / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    monkeypatch.setenv("OSINT_SPIDERFOOT_DIR", str(tmp_path))
    located, _ = locate(SPIDERFOOT)
    assert located.command == (str(venv_python), str(tmp_path / "sf.py"))
    assert located.cwd == str(tmp_path)


def test_script_python_skips_the_servers_own_environment(monkeypatch, tmp_path):
    """Under uvx the server's venv comes first on PATH; running a checkout with it would miss its packages."""
    checkout = tmp_path / "spiderfoot"
    checkout.mkdir()
    (checkout / "sf.py").write_text("")
    own_env, system = tmp_path / "uvx-env", tmp_path / "system"
    own_bin = own_env / ("Scripts" if sys.platform == "win32" else "bin")
    own_bin.mkdir(parents=True)
    system.mkdir()
    for folder in (own_bin, system):
        fake_executable(folder, "python")
        fake_executable(folder, "python3")
    monkeypatch.setattr(sys, "prefix", str(own_env))
    monkeypatch.setattr(sys, "base_prefix", str(system))
    monkeypatch.setenv("PATH", os.pathsep.join([str(own_bin), str(system)]))
    monkeypatch.setenv("OSINT_SPIDERFOOT_DIR", str(checkout))
    located, _ = locate(SPIDERFOOT)
    assert Path(located.command[0]).parent == system


def test_script_python_override(monkeypatch, tmp_path):
    (tmp_path / "sf.py").write_text("")
    monkeypatch.setenv("OSINT_SPIDERFOOT_DIR", str(tmp_path))
    monkeypatch.setenv("OSINT_SPIDERFOOT_PYTHON", sys.executable)
    located, _ = locate(SPIDERFOOT)
    assert Path(located.command[0]).resolve() == Path(sys.executable).resolve()


def test_search_path_adds_user_install_folders(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path / "a"))
    monkeypatch.setenv("UV_TOOL_BIN_DIR", str(tmp_path / "uv-bin"))
    monkeypatch.delenv("PIPX_BIN_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    folders = REAL_SEARCH_PATH().split(os.pathsep)
    assert folders[:3] == [str(tmp_path / "a"), str(tmp_path / "uv-bin"), str(tmp_path / ".local" / "bin")]

"""Finding the OSINT tools on this machine: PATH, usual install folders and OSINT_* variables."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Program:
    """A tool installed as a command, e.g. `sherlock`; `env` may point at the executable instead."""

    names: tuple[str, ...]
    env: str


@dataclass(frozen=True)
class Script:
    """A tool run with Python from a git checkout, e.g. SpiderFoot's sf.py."""

    script: str
    dir_env: str
    python_env: str


@dataclass(frozen=True)
class Located:
    command: tuple[str, ...]
    cwd: str | None = None

    @property
    def batch(self) -> bool:
        """A .bat/.cmd wrapper: Windows runs it through cmd.exe, which re-parses the arguments."""
        return sys.platform == "win32" and Path(self.command[0]).suffix.lower() in (".bat", ".cmd")


def locate(requirement: Program | Script) -> tuple[Located | None, str]:
    """Where the tool is, or why it could not be found."""
    if isinstance(requirement, Program):
        return _locate_program(requirement)
    return _locate_script(requirement)


def _setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    # A client that leaves an optional field empty may pass its template through, e.g. "${user_config.x}"
    return "" if value.startswith("${") else value


def _locate_program(program: Program) -> tuple[Located | None, str]:
    override = _setting(program.env)
    if override:
        path = shutil.which(override)
        if not path:
            return None, f"{program.env} is set to {override!r}, which is not an executable"
        return Located((path,)), ""
    search = search_path()
    for name in program.names:
        path = shutil.which(name, path=search)
        if path:
            return Located((path,)), ""
    return None, "not found"


def _locate_script(script: Script) -> tuple[Located | None, str]:
    folder = _setting(script.dir_env)
    if not folder:
        return None, f"{script.dir_env} is not set"
    root = Path(folder).expanduser()
    entry = root / script.script
    if not entry.is_file():
        return None, f"{script.dir_env} is set to {folder!r}, which has no {script.script}"
    python = _python_for(root, script.python_env)
    if not python:
        return None, f"no Python found to run {script.script}; set {script.python_env}"
    return Located((python, str(entry)), cwd=str(root)), ""


def _python_for(root: Path, env: str) -> str | None:
    """The interpreter for a checkout: an explicit one, the checkout's own venv, or the one on PATH."""
    override = _setting(env)
    if override:
        return shutil.which(override)
    inner = Path("Scripts", "python.exe") if sys.platform == "win32" else Path("bin", "python")
    for venv in (".venv", "venv"):
        candidate = root / venv / inner
        if candidate.is_file():
            return str(candidate)
    for name in ("python", "python3") if sys.platform == "win32" else ("python3", "python"):
        path = shutil.which(name)
        if path:
            return path
    return None


def search_path() -> str:
    """PATH plus the folders `uv tool` and `pipx` install into, which GUI clients often leave out of PATH."""
    folders = [folder for folder in os.environ.get("PATH", "").split(os.pathsep) if folder]
    extra = [os.environ.get("UV_TOOL_BIN_DIR"), os.environ.get("PIPX_BIN_DIR"), str(Path.home() / ".local" / "bin")]
    if sys.platform != "win32":
        extra += ["/opt/homebrew/bin", "/usr/local/bin"]
    for folder in extra:
        if folder and folder not in folders:
            folders.append(folder)
    return os.pathsep.join(folders)

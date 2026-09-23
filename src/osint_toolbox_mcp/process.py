"""Running tool processes: plain UTF-8 output, no stdin, cancellation."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Completed:
    returncode: int
    stdout: str
    stderr: str


def child_env() -> dict[str, str]:
    """The server's environment plus settings that keep tool output free of colors and in UTF-8."""
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("COLUMNS", "200")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def kill_tree(process: asyncio.subprocess.Process) -> None:
    """Stop a tool and everything it started (console-script launchers spawn a child interpreter)."""
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


async def run(command: list[str], cwd: str | None = None) -> Completed:
    if sys.platform == "win32":
        # Without it every console tool opens a window when the client is a GUI app
        platform_options = {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        # Own process group, so a cancel can stop the whole tree
        platform_options = {"start_new_session": True}

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        env=child_env(),
        # Never inherit the server's stdin: it carries MCP messages, and tools like ExifTool block on it
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **platform_options,
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        kill_tree(process)
        raise
    return Completed(process.returncode, _decode(stdout), _decode(stderr))


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").replace("\r\n", "\n")

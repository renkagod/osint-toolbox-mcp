"""`osint-toolbox-mcp --check`: which tools are installed, and whether they start."""

from __future__ import annotations

import asyncio

from . import __version__, process
from .locate import locate
from .tools import IN_CONTAINER, INSTALL_GUIDE, TOOLS, Tool

PROBE_TIMEOUT = 120  # GHunt checks for updates online before printing its help


async def _check(tool: Tool) -> tuple[str, str]:
    located, reason = locate(tool.requires)
    if located is None:
        if IN_CONTAINER and not tool.in_image:
            return "absent", "not in the Docker image: it has no license that allows redistributing it"
        return "missing", f"{reason}; to install: {tool.install}"
    try:
        done = await asyncio.wait_for(process.run([*located.command, *tool.probe], cwd=located.cwd), PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        return "broken", f"{located.command[-1]} did not respond in {PROBE_TIMEOUT} s"
    except OSError as error:
        return "broken", f"{located.command[-1]}: {error}"
    if done.returncode != 0:
        output = (done.stderr.strip() or done.stdout.strip()).splitlines()
        return "broken", f"{located.command[-1]} exited with code {done.returncode}: {output[-1] if output else ''}"
    return "ok", located.command[-1]


async def run() -> int:
    """Print a line per tool; the exit code is 0 when every tool that can be here works."""
    results = await asyncio.gather(*(_check(tool) for tool in TOOLS))
    width = max(len(tool.label) for tool in TOOLS)
    print(f"osint-toolbox-mcp {__version__}\n")
    for tool, (status, detail) in zip(TOOLS, results):
        print(f"  {status:<8} {tool.label:<{width}}  {detail}")
    expected = [status for status, _ in results if status != "absent"]
    ready = expected.count("ok")
    print(f"\n{ready} of {len(expected)} tools ready.")
    if ready < len(expected):
        print(f"Install guide: {INSTALL_GUIDE}")
    return 0 if ready == len(expected) else 1

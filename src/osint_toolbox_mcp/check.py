"""`osint-toolbox-mcp --check`: which tools are installed, and whether they start."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

from . import __version__, process
from .locate import locate
from .tools import IN_CONTAINER, INSTALL_COMMAND, INSTALL_GUIDE, TOOLS, Tool

PROBE_TIMEOUT = 120  # GHunt checks for updates online before printing its help


async def _check(tool: Tool) -> tuple[str, str]:
    located, reason = locate(tool.requires)
    if located is None:
        if IN_CONTAINER and not tool.in_image:
            return "absent", "not in the Docker image: it has no license that allows redistributing it"
        return "missing", f"{reason}; install: {INSTALL_COMMAND} {tool.label}"
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


async def run(labels: Collection[str] = ()) -> int:
    """Print a line per tool; the exit code is 0 when every tool that can be here works, or every tool named."""
    programs = [tool for tool in TOOLS if tool.requires is not None]
    results = await asyncio.gather(*(_check(tool) for tool in programs))
    width = max(len(tool.label) for tool in programs)
    print(f"osint-toolbox-mcp {__version__}\n")
    for tool, (status, detail) in zip(programs, results):
        print(f"  {status:<8} {tool.label:<{width}}  {detail}")
    built_in = [tool.name for tool in TOOLS if tool.requires is None]
    print(f"\n  built in, nothing to install: {', '.join(built_in)}")
    expected = [status for status, _ in results if status != "absent"]
    ready = expected.count("ok")
    print(f"\n{ready} of {len(expected)} tools ready.")
    if ready < len(expected):
        print(f"Install the missing ones with `{INSTALL_COMMAND}`; details: {INSTALL_GUIDE}")
    if labels:
        return 0 if all(status == "ok" for tool, (status, _) in zip(programs, results) if tool.label in labels) else 1
    return 0 if ready == len(expected) else 1

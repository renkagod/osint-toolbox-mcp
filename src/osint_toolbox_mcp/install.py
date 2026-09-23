"""`osint-toolbox-mcp --install`: install the missing tools, without admin rights.

Python tools go into their own environments with `uv tool install`, the SpiderFoot and Blackbird checkouts
and the downloaded programs into toolbox_home(). Every downloaded program is checked against the checksum
its authors publish.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import platform
import re
import shutil
import stat
import sys
import tarfile
import zipfile
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath
from typing import Any

from . import check, process, web
from .locate import locate, toolbox_home
from .tools import IN_CONTAINER, TOOLS, Tool

# Python 3.12 has wheels for every dependency the tools pin (GHunt's Pillow<11 has none for 3.14)
PYTHON = "3.12"

PACKAGES = {
    "sherlock": "sherlock-project",
    "holehe": "holehe",
    "maigret": "maigret",
    "ghunt": "ghunt",
    "dnstwist": "dnstwist",
}
# dnstwist[full] also pulls py-tlsh, which needs a C++ compiler where it has no wheels; these are what it uses here
EXTRAS = {"dnstwist": ("dnspython", "tld", "idna")}
# Not on PyPI: installed from the latest GitHub release, whose main branch can move ahead of any Python we pick
GITHUB_PACKAGES = {"theharvester": ("theHarvester", "laramies/theHarvester"), "dnsrecon": ("dnsrecon", "darkoperator/dnsrecon")}
CHECKOUTS = {"spiderfoot": "smicallef/spiderfoot", "blackbird": "antoniaci/blackbird"}


class InstallError(Exception):
    """Why a tool could not be installed."""


async def run(labels: list[str]) -> int:
    if IN_CONTAINER:
        print("The Docker image comes with its tools; --install is for a local installation.")
        return 1
    installable = [tool for tool in TOOLS if tool.requires is not None]
    unknown = sorted(set(labels) - {tool.label for tool in installable})
    if unknown:
        print(f"Unknown tool: {', '.join(unknown)}. Choose from: {', '.join(tool.label for tool in installable)}")
        return 2

    home = toolbox_home()
    print(f"Installing into {home} (set OSINT_TOOLBOX_HOME to change it)\n")
    width = max(len(tool.label) for tool in installable)
    failed = 0
    for tool in installable:
        if labels and tool.label not in labels:
            continue
        located, _ = locate(tool.requires)
        if located is not None:
            print(f"  {tool.label:<{width}}  already installed: {located.command[-1]}")
            continue
        print(f"  {tool.label:<{width}}  installing... ", end="", flush=True)
        try:
            print(await _install(tool, home))
        except (InstallError, web.WebError, OSError) as error:
            failed += 1
            print(f"failed: {error}")
    print()
    return max(await check.run(), 1 if failed else 0)


async def _install(tool: Tool, home: Path) -> str:
    if tool.label in PACKAGES or tool.label in GITHUB_PACKAGES:
        return await _uv_tool(tool.label)
    if tool.label in CHECKOUTS:
        return await _checkout(tool.label, home)
    installer = _DOWNLOADS.get(tool.label)
    if installer is None:
        raise InstallError(f"no automatic installation; {tool.install}")
    return await installer(home)


# Python tools

def _uv() -> str:
    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        raise InstallError("needs uv: https://docs.astral.sh/uv/getting-started/installation/")
    return uv


async def _run(command: list[str]) -> None:
    done = await process.run(command)
    if done.returncode != 0:
        lines = (done.stderr.strip() or done.stdout.strip()).splitlines()
        raise InstallError(lines[-1] if lines else f"{Path(command[0]).name} exited with code {done.returncode}")


async def _uv_tool(label: str) -> str:
    if label in GITHUB_PACKAGES:
        name, repository = GITHUB_PACKAGES[label]
        tag = (await _release(repository))["tag_name"]
        requirement = f"{name} @ https://github.com/{repository}/archive/refs/tags/{tag}.zip"
    else:
        requirement = PACKAGES[label]
    command = [_uv(), "tool", "install", "--python", PYTHON, requirement]
    for extra in EXTRAS.get(label, ()):
        command += ["--with", extra]
    await _run(command)
    note = "; run `ghunt login` before using it" if label == "ghunt" else ""
    return f"done ({requirement}){note}"


async def _checkout(label: str, home: Path) -> str:
    uv = _uv()
    archive = await asyncio.to_thread(web.fetch, f"https://github.com/{CHECKOUTS[label]}/archive/HEAD.zip", timeout=300)
    target = home / label
    await asyncio.to_thread(_unpack, archive, target, strip_root=True)
    await _run([uv, "venv", "--quiet", "--python", PYTHON, str(target / ".venv")])
    python = target / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    await _run([uv, "pip", "install", "--quiet", "--python", str(python), "-r", str(target / "requirements.txt")])
    return f"done ({target})"


# Downloaded programs

def _platform() -> tuple[str, str]:
    """(windows | macos | linux, amd64 | arm64)."""
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if arch is None:
        raise InstallError(f"no build for this processor ({machine})")
    return system, arch


async def _release(repository: str) -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    return await asyncio.to_thread(
        web.fetch_json, f"https://api.github.com/repos/{repository}/releases/latest", headers=headers
    )


async def _release_file(release: dict[str, Any], name: str) -> bytes:
    urls = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    if name not in urls:
        raise InstallError(f"release {release.get('tag_name')} has no {name}")
    return await asyncio.to_thread(web.fetch, urls[name], timeout=300)


def _verify(data: bytes, expected: str | None, name: str) -> None:
    if not expected:
        raise InstallError(f"no published checksum for {name}")
    if hashlib.sha256(data).hexdigest() != expected.lower():
        raise InstallError(f"checksum mismatch for {name}; the download may be corrupted or tampered with")


def _checksum(listing: bytes, name: str) -> str | None:
    """SHA-256 of `name` from a `<hash>  <file>` listing, as GoReleaser writes them."""
    for line in listing.decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0]
    return None


async def _phoneinfoga(home: Path) -> str:
    system, arch = _platform()
    release = await _release("sundowndev/phoneinfoga")
    os_name = {"windows": "Windows", "macos": "Darwin", "linux": "Linux"}[system]
    name = f"phoneinfoga_{os_name}_{'x86_64' if arch == 'amd64' else arch}.tar.gz"
    archive = await _release_file(release, name)
    _verify(archive, _checksum(await _release_file(release, "phoneinfoga_checksums.txt"), name), name)
    binary = "phoneinfoga.exe" if system == "windows" else "phoneinfoga"
    _extract_one(archive, binary, home / "bin" / binary)
    return f"done ({release.get('tag_name')}, {home / 'bin'})"


async def _subfinder(home: Path) -> str:
    system, arch = _platform()
    release = await _release("projectdiscovery/subfinder")
    version = str(release.get("tag_name", "")).lstrip("v")
    os_name = {"windows": "windows", "macos": "macOS", "linux": "linux"}[system]
    name = f"subfinder_{version}_{os_name}_{arch}.zip"
    archive = await _release_file(release, name)
    _verify(archive, _checksum(await _release_file(release, f"subfinder_{version}_checksums.txt"), name), name)
    binary = "subfinder.exe" if system == "windows" else "subfinder"
    _extract_one(archive, binary, home / "bin" / binary)
    return f"done ({release.get('tag_name')}, {home / 'bin'})"


async def _exiftool(home: Path) -> str:
    system, _ = _platform()
    version = (await asyncio.to_thread(web.fetch, "https://exiftool.org/ver.txt")).decode().strip()
    if not re.fullmatch(r"\d+\.\d+", version):
        raise InstallError(f"unexpected ExifTool version {version!r}")
    listing = await asyncio.to_thread(web.fetch, f"https://exiftool.org/checksums-{version}.txt")
    sums = dict(re.findall(r"SHA2-256\(([^)]+)\)=\s*([0-9a-f]{64})", listing.decode("utf-8", errors="replace")))

    if system == "windows":
        name = f"exiftool-{version}_64.zip"
    else:
        perl = shutil.which("perl")
        if not perl:
            raise InstallError(
                "needs Perl; or install ExifTool with your package manager "
                "(brew install exiftool, apt install libimage-exiftool-perl)"
            )
        name = f"Image-ExifTool-{version}.tar.gz"
    archive = await asyncio.to_thread(
        web.fetch, f"https://sourceforge.net/projects/exiftool/files/{name}/download", timeout=300
    )
    _verify(archive, sums.get(name), name)

    if system == "windows":
        # The Windows build is exiftool(-k).exe plus its exiftool_files folder; both must stay together
        target = home / "exiftool"
        _unpack(archive, target, strip_root=True)
        (target / "exiftool(-k).exe").replace(target / "exiftool.exe")
        return f"done ({version}, {target})"
    source = home / "exiftool-perl"
    _unpack(archive, source, strip_root=True)
    wrapper = home / "bin" / "exiftool"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(f'#!/bin/sh\nexec "{perl}" "{source / "exiftool"}" "$@"\n', encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"done ({version}, {wrapper})"


_DOWNLOADS: dict[str, Callable[[Path], Awaitable[str]]] = {
    "phoneinfoga": _phoneinfoga,
    "subfinder": _subfinder,
    "exiftool": _exiftool,
}


# Archives

def _members(archive: bytes) -> list[tuple[str, Callable[[], bytes], bool]]:
    """(path, read, is_executable) for every file in a zip or tar.gz archive."""
    if archive[:2] == b"PK":
        bundle = zipfile.ZipFile(io.BytesIO(archive))
        return [
            (info.filename, lambda info=info: bundle.read(info), bool((info.external_attr >> 16) & 0o111))
            for info in bundle.infolist()
            if not info.is_dir()
        ]
    tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:*")
    return [
        (member.name, lambda member=member: tar.extractfile(member).read(), bool(member.mode & 0o111))
        for member in tar.getmembers()
        if member.isfile()
    ]


def _safe_parts(name: str) -> tuple[str, ...]:
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if not parts or parts[0] == "/" or ".." in parts or ":" in parts[0]:
        raise InstallError(f"refusing to unpack {name!r}: it points outside the target folder")
    return parts


def _unpack(archive: bytes, target: Path, strip_root: bool) -> None:
    """Replace `target` with the archive's contents, without the archive's own top folder if strip_root."""
    if target.exists():
        shutil.rmtree(target)
    for name, read, executable in _members(archive):
        parts = _safe_parts(name)[1 if strip_root else 0:]
        if not parts:
            continue
        path = target.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(read())
        if executable:
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _extract_one(archive: bytes, filename: str, destination: Path) -> None:
    for name, read, _ in _members(archive):
        if _safe_parts(name)[-1] == filename:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(read())
            destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return
    raise InstallError(f"the archive has no {filename}")

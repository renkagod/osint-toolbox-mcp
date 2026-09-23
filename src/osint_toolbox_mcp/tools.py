"""The tools this server offers: input checks, how each OSINT program is run and what it returns."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import process
from .locate import Located, Program, Script, locate

INSTALL_GUIDE = "https://github.com/renkagod/osint-toolbox-mcp#install-the-tools"
DEFAULT_MAX_OUTPUT = 100_000
IN_CONTAINER = bool(os.environ.get("OSINT_TOOLBOX_CONTAINER"))


class ToolError(Exception):
    """Bad input or a failed run: returned to the model as a tool error it can act on."""


@dataclass(frozen=True)
class Tool:
    name: str
    label: str
    title: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]
    requires: Program | Script
    install: str
    probe: tuple[str, ...]  # arguments that make the program print its version or help and exit
    run: Callable[[dict[str, Any], Located], Awaitable[str]]
    open_world: bool = True

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": {"type": "object", "properties": self.properties, "required": list(self.required)},
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": self.open_world,
            },
        }


def available_tools() -> list[Tool]:
    return [tool for tool in TOOLS if locate(tool.requires)[0] is not None]


async def call_tool(tool: Tool, arguments: dict[str, Any]) -> str:
    located, reason = locate(tool.requires)
    if located is None:
        raise ToolError(f"{tool.label} is not available ({reason}). To install: {tool.install}. Guide: {INSTALL_GUIDE}")
    return limit_output(await tool.run(arguments, located))


def limit_output(text: str) -> str:
    try:
        cap = int(os.environ.get("OSINT_MAX_OUTPUT_CHARS") or DEFAULT_MAX_OUTPUT)
    except ValueError:
        cap = DEFAULT_MAX_OUTPUT
    if cap <= 0 or len(text) <= cap:
        return text
    return (
        f"{text[:cap]}\n\n[Output truncated to {cap} of {len(text)} characters. "
        "Narrow the search, or raise OSINT_MAX_OUTPUT_CHARS.]"
    )


# Input checks

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
# cmd.exe re-parses the command line of a .bat/.cmd wrapper, so these could end the argument or start a new command
_BATCH_UNSAFE = re.compile(r'["&|<>^%!]')


def _text(arguments: dict[str, Any], key: str, *, required: bool = True, max_length: int = 256) -> str | None:
    value = arguments.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolError(f"'{key}' is required")
        return None
    if not isinstance(value, str):
        raise ToolError(f"'{key}' must be a string")
    return _clean(key, value, max_length)


def _clean(key: str, value: str, max_length: int = 256) -> str:
    value = value.strip()
    if len(value) > max_length:
        raise ToolError(f"'{key}' must be at most {max_length} characters")
    if value.startswith("-"):
        raise ToolError(f"'{key}' must not start with '-': the tool would read it as an option")
    if _CONTROL_CHARS.search(value):
        raise ToolError(f"'{key}' must not contain control characters")
    return value


def _int(arguments: dict[str, Any], key: str, low: int, high: int) -> int | None:
    value = arguments.get(key)
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"'{key}' must be an integer")
    if not low <= value <= high:
        raise ToolError(f"'{key}' must be between {low} and {high}")
    return value


def _flag(arguments: dict[str, Any], key: str, default: bool) -> bool:
    value = arguments.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ToolError(f"'{key}' must be true or false")
    return value


def _choice(arguments: dict[str, Any], key: str, choices: tuple[str, ...], default: str) -> str:
    value = arguments.get(key)
    if value is None:
        return default
    if value not in choices:
        raise ToolError(f"'{key}' must be one of: {', '.join(choices)}")
    return value


# Running

async def _execute(located: Located, arguments: list[str], cwd: str | None = None) -> process.Completed:
    if located.batch and any(_BATCH_UNSAFE.search(argument) for argument in arguments):
        raise ToolError(
            f"{Path(located.command[0]).name} is a .bat/.cmd wrapper and this input has characters cmd.exe "
            "would interpret; point the OSINT_* variable at the real executable"
        )
    try:
        return await process.run([*located.command, *arguments], cwd=cwd or located.cwd)
    except OSError as error:
        raise ToolError(f"could not start {located.command[0]}: {error}") from error


def _failure(label: str, done: process.Completed) -> ToolError:
    details = (done.stderr.strip() or done.stdout.strip())[-3000:]
    message = f"{label} exited with code {done.returncode}"
    return ToolError(f"{message}:\n{details}" if details else message)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1)


def _read_files(folder: str) -> str:
    parts = []
    for path in sorted(Path(folder).iterdir()):
        if path.is_file():
            parts.append(f"{path.name}:\n{path.read_text(encoding='utf-8', errors='replace').strip()}")
    return "\n\n".join(parts)


# Handlers

async def _sherlock(arguments: dict[str, Any], located: Located) -> str:
    username = _text(arguments, "username")
    timeout = _int(arguments, "timeout", 1, 600)
    sites = arguments.get("sites") or []
    if not isinstance(sites, list) or not all(isinstance(site, str) for site in sites):
        raise ToolError("'sites' must be a list of site names")
    output_format = _choice(arguments, "output_format", ("csv", "txt"), "csv")

    options = [username, "--no-color", "--print-found"]
    if timeout:
        options += ["--timeout", str(timeout)]
    for site in sites:
        options += ["--site", _clean("sites", site)]
    if output_format == "csv":
        options += ["--csv", "--no-txt"]
    with tempfile.TemporaryDirectory(prefix="osint-sherlock-") as folder:
        done = await _execute(located, [*options, "--folderoutput", folder], cwd=folder)
        if done.returncode != 0:
            raise _failure("Sherlock", done)
        return _read_files(folder) or done.stdout.strip()


# Holehe prints its author's links before and after the results
_HOLEHE_PROMO = ("Twitter : @palenath", "Github : https://github.com/megadose/holehe", "For BTC Donations")


async def _holehe(arguments: dict[str, Any], located: Located) -> str:
    email = _text(arguments, "email")
    if "@" not in email:
        raise ToolError("'email' must be an email address")
    timeout = _int(arguments, "timeout", 1, 600)

    options = [email, "--no-color", "--no-clear"]
    if _flag(arguments, "only_used", True):
        options.append("--only-used")
    if timeout:
        options += ["--timeout", str(timeout)]
    with tempfile.TemporaryDirectory(prefix="osint-holehe-") as folder:
        done = await _execute(located, options, cwd=folder)
    if done.returncode != 0:
        raise _failure("Holehe", done)
    lines = [line for line in done.stdout.splitlines() if not line.startswith(_HOLEHE_PROMO)]
    return "\n".join(lines).strip()


SPIDERFOOT_USE_CASES = ("all", "footprint", "investigate", "passive")


async def _spiderfoot(arguments: dict[str, Any], located: Located) -> str:
    target = _text(arguments, "target")
    use_case = _choice(arguments, "use_case", SPIDERFOOT_USE_CASES, "all")

    done = await _execute(located, ["-s", target, "-u", use_case, "-o", "json", "-q"])
    if done.returncode != 0:
        raise _failure("SpiderFoot", done)
    events = _spiderfoot_events(done.stdout)
    if events:
        return _json(events)
    output = done.stdout.strip()
    return output if output.strip("[] ") else f"SpiderFoot found nothing for {target!r}."


def _spiderfoot_events(output: str) -> dict[str, list[str]]:
    """Event data grouped by type, without the duplicates SpiderFoot reports once per module.

    The events are read one object at a time: SpiderFoot's scan process prints them while the main
    process prints the enclosing brackets, so the array comes out as `{...},\\n{...}[]`.
    """
    decoder = json.JSONDecoder()
    grouped: dict[str, dict[str, None]] = {}
    position = output.find("{")
    while position != -1:
        try:
            event, position = decoder.raw_decode(output, position)
        except ValueError:
            position += 1
        else:
            if isinstance(event, dict) and event.get("data") is not None:
                grouped.setdefault(str(event.get("type")), {})[str(event["data"])] = None
        position = output.find("{", position)
    return {kind: list(values) for kind, values in grouped.items()}


async def _ghunt(arguments: dict[str, Any], located: Located) -> str:
    identifier = _text(arguments, "identifier")
    if identifier.isdigit():
        mode = "gaia"
    elif "@" in identifier:
        mode = "email"
    else:
        raise ToolError("'identifier' must be an email address or a numeric Gaia ID")

    with tempfile.TemporaryDirectory(prefix="osint-ghunt-") as folder:
        report = Path(folder, "report.json")
        done = await _execute(located, [mode, identifier, "--json", str(report)], cwd=folder)
        if report.is_file():
            return _json(json.loads(report.read_text(encoding="utf-8")))
    output = f"{done.stdout}\n{done.stderr}".lower()
    if "ghunt login" in output or "master token" in output:
        raise ToolError(
            "GHunt has no valid login (missing, or its master token expired): run `ghunt login` "
            "(for Docker, see the README), then retry"
        )
    if done.returncode != 0:
        raise _failure("GHunt", done)
    return done.stdout.strip()


async def _maigret(arguments: dict[str, Any], located: Located) -> str:
    username = _text(arguments, "username")
    timeout = _int(arguments, "timeout", 1, 600)

    options = [username, "--no-color", "--no-progressbar", "--json", "simple"]
    if timeout:
        options += ["--timeout", str(timeout)]
    if _flag(arguments, "all_sites", False):
        options.append("--all-sites")
    with tempfile.TemporaryDirectory(prefix="osint-maigret-") as folder:
        done = await _execute(located, [*options, "--folderoutput", folder], cwd=folder)
        if done.returncode != 0:
            raise _failure("Maigret", done)
        reports = sorted(Path(folder).glob("*.json"))
        if not reports:
            return done.stdout.strip()
        accounts: dict[str, Any] = {}
        for report in reports:
            accounts.update(_maigret_accounts(json.loads(report.read_text(encoding="utf-8"))))
    return _json(accounts) if accounts else f"No accounts found for {username!r}."


def _maigret_accounts(report: Any) -> dict[str, Any]:
    """Profile URL, extracted data and tags per site; the rest of the report is Maigret's own site-check config."""
    if not isinstance(report, dict):
        return {}
    accounts = {}
    for site, entry in report.items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
        account: dict[str, Any] = {"url": entry.get("url_user") or status.get("url")}
        if status.get("ids"):
            account["data"] = status["ids"]
        if status.get("tags"):
            account["tags"] = status["tags"]
        if entry.get("is_similar"):
            account["similar_username"] = True
        accounts[site] = account
    return accounts


_SOURCES = re.compile(r"[A-Za-z0-9_-]+(,[A-Za-z0-9_-]+)*")


async def _theharvester(arguments: dict[str, Any], located: Located) -> str:
    domain = _text(arguments, "domain")
    sources = _text(arguments, "sources", required=False) or "all"
    if not _SOURCES.fullmatch(sources):
        raise ToolError("'sources' must be a comma-separated list of source names, or 'all'")
    limit = _int(arguments, "limit", 1, 10_000) or 500

    with tempfile.TemporaryDirectory(prefix="osint-theharvester-") as folder:
        report = Path(folder, "report")
        done = await _execute(
            located, ["-d", domain, "-b", sources, "-l", str(limit), "-q", "-f", str(report)], cwd=folder
        )
        if done.returncode != 0:
            raise _failure("theHarvester", done)
        report = report.with_suffix(".json")
        if report.is_file():
            return _json(json.loads(report.read_text(encoding="utf-8")))
    return done.stdout.strip()


# Blackbird opens with a block-letter banner and a credits line
_BLOCK_ART = set("▄▀█▌▐░▒▓ ")


async def _blackbird(arguments: dict[str, Any], located: Located) -> str:
    username = _text(arguments, "username")
    timeout = _int(arguments, "timeout", 1, 600)

    options = ["-u", username]
    if timeout:
        options += ["--timeout", str(timeout)]
    done = await _execute(located, options)
    if done.returncode != 0:
        raise _failure("Blackbird", done)
    lines = done.stdout.splitlines()
    while lines and (set(lines[0].strip()) <= _BLOCK_ART or " | by " in lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()


_PHONE_NUMBER = re.compile(r"\+?[0-9][0-9 ().-]{4,30}")


async def _phoneinfoga(arguments: dict[str, Any], located: Located) -> str:
    number = _text(arguments, "number", max_length=32)
    if not _PHONE_NUMBER.fullmatch(number):
        raise ToolError("'number' must be a phone number in international format, e.g. +14155552671")

    with tempfile.TemporaryDirectory(prefix="osint-phoneinfoga-") as folder:
        # PhoneInfoga reads .env from its working directory; an empty one keeps unrelated files out
        done = await _execute(located, ["scan", "-n", number], cwd=folder)
    if done.returncode != 0:
        raise _failure("PhoneInfoga", done)
    return done.stdout.strip()


async def _exiftool(arguments: dict[str, Any], located: Located) -> str:
    path = Path(_text(arguments, "file_path", max_length=4096)).expanduser()
    if not path.is_absolute():
        raise ToolError("'file_path' must be an absolute path")
    if not path.is_file():
        raise ToolError(f"no such file: {path}")

    with tempfile.TemporaryDirectory(prefix="osint-exiftool-") as folder:
        if sys.platform == "win32" and not str(path).isascii():
            # ExifTool reads a Windows command line in the ANSI code page; an argument file keeps the name intact
            argfile = Path(folder, "args.txt")
            argfile.write_text(f"-j\n{path}\n", encoding="utf-8")
            options = ["-charset", "filename=utf8", "-@", str(argfile)]
        else:
            options = ["-j", str(path)]
        done = await _execute(located, options, cwd=folder)
    if done.returncode != 0:
        raise _failure("ExifTool", done)
    try:
        data = json.loads(done.stdout)
    except ValueError:
        return done.stdout.strip()
    return _json(data[0] if isinstance(data, list) and len(data) == 1 else data)


def _timeout(default: int) -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": 600,
        "description": f"Seconds to wait for each site's response (the tool's default: {default})",
    }


_USERNAME = {"type": "string", "description": "Username to search for"}

TOOLS: tuple[Tool, ...] = (
    Tool(
        name="sherlock_username_search",
        label="sherlock",
        title="Sherlock username search",
        description=(
            "Find accounts that use a username on 400+ social networks and websites (Sherlock). "
            "Returns the sites where the username exists, with profile URLs."
        ),
        properties={
            "username": _USERNAME,
            "sites": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only check these sites (Sherlock site names, e.g. GitHub)",
            },
            "timeout": _timeout(60),
            "output_format": {
                "type": "string",
                "enum": ["csv", "txt"],
                "description": "csv (default): site, profile URL, HTTP status and response time; txt: profile URLs only",
            },
        },
        required=("username",),
        requires=Program(("sherlock",), "OSINT_SHERLOCK"),
        install="uv tool install sherlock-project",
        probe=("--version",),
        run=_sherlock,
    ),
    Tool(
        name="holehe_email_search",
        label="holehe",
        title="Holehe email registration check",
        description="Check which of about 120 websites have an account registered to an email address (Holehe).",
        properties={
            "email": {"type": "string", "description": "Email address to check"},
            "only_used": {
                "type": "boolean",
                "description": "Report only the sites where the email is registered (default: true)",
            },
            "timeout": _timeout(10),
        },
        required=("email",),
        requires=Program(("holehe",), "OSINT_HOLEHE"),
        install="uv tool install holehe",
        probe=("--help",),
        run=_holehe,
    ),
    Tool(
        name="spiderfoot_scan",
        label="spiderfoot",
        title="SpiderFoot scan",
        description=(
            "Run a SpiderFoot scan: it detects the target type and runs the matching modules. "
            "Results are grouped by event type. A 'passive' scan takes minutes, 'all' can take 30+ minutes."
        ),
        properties={
            "target": {
                "type": "string",
                "description": (
                    "Domain, IP address, subnet (CIDR), email address, phone number, username, "
                    'person name in double quotes (e.g. "John Smith"), Bitcoin address or BGP AS number'
                ),
            },
            "use_case": {
                "type": "string",
                "enum": list(SPIDERFOOT_USE_CASES),
                "description": (
                    "Which modules run: passive (no direct contact with the target, fastest), footprint, "
                    "investigate, or all (default, slowest)"
                ),
            },
        },
        required=("target",),
        requires=Script("sf.py", "OSINT_SPIDERFOOT_DIR", "OSINT_SPIDERFOOT_PYTHON"),
        install=(
            "git clone https://github.com/smicallef/spiderfoot, install its requirements.txt "
            "and set OSINT_SPIDERFOOT_DIR to the folder"
        ),
        probe=("-V",),
        run=_spiderfoot,
    ),
    Tool(
        name="ghunt_google_search",
        label="ghunt",
        title="GHunt Google account lookup",
        description=(
            "Look up a Google account by email address or Gaia ID (GHunt): name, profile picture, Gaia ID, "
            "Maps reviews, calendar and other public data. Requires a one-time `ghunt login`."
        ),
        properties={
            "identifier": {"type": "string", "description": "Google account email address, or numeric Gaia ID"},
        },
        required=("identifier",),
        requires=Program(("ghunt",), "OSINT_GHUNT"),
        install="uv tool install ghunt, then run `ghunt login`",
        probe=("--help",),
        run=_ghunt,
    ),
    Tool(
        name="maigret_username_search",
        label="maigret",
        title="Maigret username search",
        description=(
            "Search a username with Maigret: the 500 most popular sites by default, 3000+ with all_sites. "
            "Extracts profile data (names, links, IDs) and filters false positives."
        ),
        properties={
            "username": _USERNAME,
            "all_sites": {
                "type": "boolean",
                "description": "Check every site in Maigret's database instead of the 500 most popular (much slower)",
            },
            "timeout": _timeout(30),
        },
        required=("username",),
        requires=Program(("maigret",), "OSINT_MAIGRET"),
        install="uv tool install maigret",
        probe=("--version",),
        run=_maigret,
    ),
    Tool(
        name="theharvester_domain_search",
        label="theharvester",
        title="theHarvester domain search",
        description=(
            "Collect email addresses, subdomains, hosts, IP addresses and URLs for a domain or company name "
            "from public sources (theHarvester)."
        ),
        properties={
            "domain": {"type": "string", "description": "Domain (example.com) or company name"},
            "sources": {
                "type": "string",
                "description": (
                    "Comma-separated sources, e.g. crtsh,duckduckgo,hackertarget (default: all; "
                    "sources that need an API key are skipped unless the key is in theHarvester's api-keys.yaml)"
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10000,
                "description": "Maximum number of results (default: 500)",
            },
        },
        required=("domain",),
        requires=Program(("theHarvester", "theharvester"), "OSINT_THEHARVESTER"),
        install="uv tool install git+https://github.com/laramies/theHarvester",
        probe=("--help",),
        run=_theharvester,
    ),
    Tool(
        name="blackbird_username_search",
        label="blackbird",
        title="Blackbird username search",
        description="Search a username on the 700+ sites of the WhatsMyName list (Blackbird).",
        properties={"username": _USERNAME, "timeout": _timeout(30)},
        required=("username",),
        requires=Script("blackbird.py", "OSINT_BLACKBIRD_DIR", "OSINT_BLACKBIRD_PYTHON"),
        install=(
            "git clone https://github.com/antoniaci/blackbird, install its requirements.txt "
            "and set OSINT_BLACKBIRD_DIR to the folder"
        ),
        probe=("--help",),
        run=_blackbird,
    ),
    Tool(
        name="phoneinfoga_scan",
        label="phoneinfoga",
        title="PhoneInfoga phone number scan",
        description=(
            "Scan a phone number with PhoneInfoga: country, number formats, carrier and line type "
            "(with an API key), and search engine queries for it."
        ),
        properties={
            "number": {
                "type": "string",
                "description": "Phone number in international (E.164) format, e.g. +14155552671",
            },
        },
        required=("number",),
        requires=Program(("phoneinfoga",), "OSINT_PHONEINFOGA"),
        install=(
            "download a release from https://github.com/sundowndev/phoneinfoga/releases "
            "and put phoneinfoga on PATH (or set OSINT_PHONEINFOGA)"
        ),
        probe=("version",),
        run=_phoneinfoga,
    ),
    Tool(
        name="exiftool_metadata",
        label="exiftool",
        title="ExifTool metadata",
        description=(
            "Read the metadata of a local photo, video or document with ExifTool: GPS coordinates, camera, "
            "author, software and timestamps."
            + (
                " Running in Docker: only files in the folder mounted at /data are visible, "
                "so pass paths like /data/photo.jpg."
                if IN_CONTAINER
                else ""
            )
        ),
        properties={
            "file_path": {"type": "string", "description": "Absolute path to the photo, video or document"},
        },
        required=("file_path",),
        requires=Program(("exiftool",), "OSINT_EXIFTOOL"),
        install="install ExifTool (https://exiftool.org or a package manager) and put exiftool on PATH (or set OSINT_EXIFTOOL)",
        probe=("-ver",),
        run=_exiftool,
        open_world=False,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}

"""The tools this server offers: how each OSINT program is run and what it returns."""

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

from . import lookups, process
from .inputs import ToolError, choice, clean, domain, flag, integer, text
from .locate import Located, Program, Script, locate

__all__ = ["TOOLS", "TOOLS_BY_NAME", "Tool", "ToolError", "available_tools", "call_tool", "limit_output"]

INSTALL_GUIDE = "https://github.com/renkagod/osint-toolbox-mcp#install-the-tools"
INSTALL_COMMAND = "uvx osint-toolbox-mcp --install"
DEFAULT_MAX_OUTPUT = 100_000
IN_CONTAINER = bool(os.environ.get("OSINT_TOOLBOX_CONTAINER"))


@dataclass(frozen=True)
class Tool:
    name: str
    label: str
    title: str
    description: str
    properties: dict[str, Any]
    required: tuple[str, ...]
    run: Callable[[dict[str, Any], Located | None], Awaitable[str]]
    requires: Program | Script | None = None  # None: built into the server
    install: str = ""
    probe: tuple[str, ...] = ()  # arguments that make the program print its version or help and exit
    open_world: bool = True
    in_image: bool = True  # shipped in the Docker image

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
    return [tool for tool in TOOLS if tool.requires is None or locate(tool.requires)[0] is not None]


async def call_tool(tool: Tool, arguments: dict[str, Any]) -> str:
    located = None
    if tool.requires is not None:
        located, reason = locate(tool.requires)
        if located is None:
            raise ToolError(f"{tool.label} is not available ({reason}). {_how_to_install(tool)}")
    return limit_output(await tool.run(arguments, located))


def _how_to_install(tool: Tool) -> str:
    if IN_CONTAINER:
        return "It is not included in this Docker image." if not tool.in_image else "The Docker image should include it."
    return f"Install it with `{INSTALL_COMMAND} {tool.label}`, or manually: {tool.install}."


def limit_output(output: str) -> str:
    try:
        cap = int(os.environ.get("OSINT_MAX_OUTPUT_CHARS") or DEFAULT_MAX_OUTPUT)
    except ValueError:
        cap = DEFAULT_MAX_OUTPUT
    if cap <= 0 or len(output) <= cap:
        return output
    return (
        f"{output[:cap]}\n\n[Output truncated to {cap} of {len(output)} characters. "
        "Narrow the search, or raise OSINT_MAX_OUTPUT_CHARS.]"
    )


# Running

# cmd.exe re-parses the command line of a .bat/.cmd wrapper, so these could end the argument or start a new command
_BATCH_UNSAFE = re.compile(r'["&|<>^%!]')


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
    username = text(arguments, "username")
    timeout = integer(arguments, "timeout", 1, 600)
    sites = arguments.get("sites") or []
    if not isinstance(sites, list) or not all(isinstance(site, str) for site in sites):
        raise ToolError("'sites' must be a list of site names")
    output_format = choice(arguments, "output_format", ("csv", "txt"), "csv")

    options = [username, "--no-color", "--print-found"]
    if timeout:
        options += ["--timeout", str(timeout)]
    for site in sites:
        options += ["--site", clean("sites", site)]
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
    email = text(arguments, "email")
    if "@" not in email:
        raise ToolError("'email' must be an email address")
    timeout = integer(arguments, "timeout", 1, 600)

    options = [email, "--no-color", "--no-clear"]
    if flag(arguments, "only_used", True):
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
    target = text(arguments, "target")
    use_case = choice(arguments, "use_case", SPIDERFOOT_USE_CASES, "all")

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
    identifier = text(arguments, "identifier")
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
            "GHunt has no valid login: run `ghunt login` (for Docker, see the README). If the saved session "
            "was revoked, `ghunt login` fails too: run `ghunt login --clean` first to delete it."
        )
    if done.returncode != 0:
        raise _failure("GHunt", done)
    # Without a report there are only GHunt's status lines, like "[-] The target wasn't found.", after its banner
    status = [line.strip() for line in done.stdout.splitlines() if line.strip().startswith("[")]
    return "\n".join(status) or done.stdout.strip()


async def _maigret(arguments: dict[str, Any], located: Located) -> str:
    username = text(arguments, "username")
    timeout = integer(arguments, "timeout", 1, 600)

    options = [username, "--no-color", "--no-progressbar", "--json", "simple"]
    if timeout:
        options += ["--timeout", str(timeout)]
    if flag(arguments, "all_sites", False):
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
    target = text(arguments, "domain")
    sources = text(arguments, "sources", required=False) or "all"
    if not _SOURCES.fullmatch(sources):
        raise ToolError("'sources' must be a comma-separated list of source names, or 'all'")
    limit = integer(arguments, "limit", 1, 10_000) or 500

    with tempfile.TemporaryDirectory(prefix="osint-theharvester-") as folder:
        report = Path(folder, "report")
        done = await _execute(
            located, ["-d", target, "-b", sources, "-l", str(limit), "-q", "-f", str(report)], cwd=folder
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
    username = text(arguments, "username")
    timeout = integer(arguments, "timeout", 1, 600)

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
    number = text(arguments, "number", max_length=32)
    if not _PHONE_NUMBER.fullmatch(number):
        raise ToolError("'number' must be a phone number in international format, e.g. +14155552671")

    with tempfile.TemporaryDirectory(prefix="osint-phoneinfoga-") as folder:
        # PhoneInfoga reads .env from its working directory; an empty one keeps unrelated files out
        done = await _execute(located, ["scan", "-n", number], cwd=folder)
    if done.returncode != 0:
        raise _failure("PhoneInfoga", done)
    return done.stdout.strip()


async def _exiftool(arguments: dict[str, Any], located: Located) -> str:
    path = Path(text(arguments, "file_path", max_length=4096)).expanduser()
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


async def _subfinder(arguments: dict[str, Any], located: Located) -> str:
    target = domain(arguments, "domain")
    timeout = integer(arguments, "timeout", 1, 600)

    options = ["-d", target, "-silent", "-oJ", "-cs", "-nc"]
    if flag(arguments, "all_sources", False):
        options.append("-all")
    if timeout:
        options += ["-timeout", str(timeout)]
    with tempfile.TemporaryDirectory(prefix="osint-subfinder-") as folder:
        done = await _execute(located, options, cwd=folder)
    if done.returncode != 0:
        raise _failure("subfinder", done)
    hosts: dict[str, set[str]] = {}
    for line in done.stdout.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("host"):
            sources = record.get("sources") or ([record["source"]] if record.get("source") else [])
            hosts.setdefault(str(record["host"]).lower(), set()).update(map(str, sources))
    if not hosts:
        return f"subfinder found no subdomains of {target}."
    return _json({"domain": target, "subdomains": {host: sorted(hosts[host]) for host in sorted(hosts)}})


async def _dnstwist(arguments: dict[str, Any], located: Located) -> str:
    target = domain(arguments, "domain")
    registered_only = flag(arguments, "registered_only", True)

    options = ["--format", "json"]
    if registered_only:
        options.append("--registered")
    done = await _execute(located, [*options, target])
    if done.returncode != 0:
        raise _failure("dnstwist", done)
    try:
        entries = json.loads(done.stdout)
    except ValueError:
        return done.stdout.strip()
    lookalikes = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("fuzzer") == "*original":
            continue
        lookalike = {"domain": entry.get("domain"), "fuzzer": entry.get("fuzzer")}
        for key in ("dns_a", "dns_aaaa", "dns_mx", "dns_ns"):
            if entry.get(key):
                lookalike[key.removeprefix("dns_")] = entry[key]
        lookalikes.append(lookalike)
    if not lookalikes:
        return f"dnstwist found no {'registered ' if registered_only else ''}lookalikes of {target}."
    return _json({"domain": target, "lookalikes": lookalikes})


DNSRECON_SCANS = ("std", "srv", "axfr", "crt", "zonewalk")


async def _dnsrecon(arguments: dict[str, Any], located: Located) -> str:
    target = domain(arguments, "domain")
    scan = choice(arguments, "scan_type", DNSRECON_SCANS, "std")

    with tempfile.TemporaryDirectory(prefix="osint-dnsrecon-") as folder:
        report = Path(folder, "report.json")
        done = await _execute(located, ["-d", target, "-t", scan, "-j", str(report)], cwd=folder)
        if done.returncode != 0:
            raise _failure("dnsrecon", done)
        if report.is_file():
            records = json.loads(report.read_text(encoding="utf-8"))
            records = [record for record in records if not (isinstance(record, dict) and record.get("type") == "ScanInfo")]
            return _json(records) if records else f"dnsrecon found no records for {target}."
    return done.stdout.strip()


async def _status(arguments: dict[str, Any], located: Located | None = None) -> str:
    ready, missing = [], []
    for tool in TOOLS:
        if tool.requires is None:
            ready.append(tool.name)
            continue
        found, reason = locate(tool.requires)
        if found:
            ready.append(tool.name)
        else:
            missing.append(f"- {tool.name} ({tool.label}): {reason}. {_how_to_install(tool)}")
    report = [f"Available ({len(ready)}): {', '.join(ready)}."]
    if missing:
        report.append(f"Not installed ({len(missing)}):\n" + "\n".join(missing))
        if not IN_CONTAINER:
            report.append(
                f"The user can install everything that is missing with `{INSTALL_COMMAND}`, then restart the MCP "
                f"client so it sees the new tools. Details: {INSTALL_GUIDE}"
            )
    return "\n\n".join(report)


def _timeout(default: int) -> dict[str, Any]:
    return {
        "type": "integer",
        "minimum": 1,
        "maximum": 600,
        "description": f"Seconds to wait for each site's response (the tool's default: {default})",
    }


_USERNAME = {"type": "string", "description": "Username to search for"}
_DOMAIN = {"type": "string", "description": "Domain name, e.g. example.com"}

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
        requires=Script("sf.py", "OSINT_SPIDERFOOT_DIR", "OSINT_SPIDERFOOT_PYTHON", "spiderfoot"),
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
        install="uv tool install git+https://github.com/laramies/theHarvester@4.11.1 (or a newer release tag)",
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
        requires=Script("blackbird.py", "OSINT_BLACKBIRD_DIR", "OSINT_BLACKBIRD_PYTHON", "blackbird"),
        install=(
            "git clone https://github.com/antoniaci/blackbird, install its requirements.txt "
            "and set OSINT_BLACKBIRD_DIR to the folder"
        ),
        probe=("--help",),
        run=_blackbird,
        in_image=False,  # no license that allows redistributing it
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
    Tool(
        name="subfinder_subdomain_search",
        label="subfinder",
        title="subfinder subdomain search",
        description=(
            "Find subdomains of a domain in passive sources such as certificate logs and DNS datasets (subfinder). "
            "Returns each subdomain with the sources that reported it."
        ),
        properties={
            "domain": _DOMAIN,
            "all_sources": {
                "type": "boolean",
                "description": "Query every source instead of subfinder's fast default set (slower)",
            },
            "timeout": {
                "type": "integer",
                "minimum": 1,
                "maximum": 600,
                "description": "Seconds to wait for each source (subfinder's default: 30)",
            },
        },
        required=("domain",),
        requires=Program(("subfinder",), "OSINT_SUBFINDER"),
        install=(
            "download a release from https://github.com/projectdiscovery/subfinder/releases "
            "and put subfinder on PATH (or set OSINT_SUBFINDER)"
        ),
        probe=("-version",),
        run=_subfinder,
    ),
    Tool(
        name="dnstwist_lookalike_domains",
        label="dnstwist",
        title="dnstwist lookalike domains",
        description=(
            "Generate lookalike domains (typos, homoglyphs, other TLDs) for a domain and check which are "
            "registered, with their A, MX and NS records (dnstwist). Useful to spot phishing domains."
        ),
        properties={
            "domain": _DOMAIN,
            "registered_only": {
                "type": "boolean",
                "description": "Return only lookalikes that are registered (default: true)",
            },
        },
        required=("domain",),
        requires=Program(("dnstwist",), "OSINT_DNSTWIST"),
        install="uv tool install dnstwist --with dnspython --with tld --with idna",
        probe=("--help",),
        run=_dnstwist,
    ),
    Tool(
        name="dnsrecon_domain_scan",
        label="dnsrecon",
        title="dnsrecon DNS reconnaissance",
        description=(
            "DNS reconnaissance of a domain with dnsrecon: SOA, NS, MX, A, AAAA and SRV records, zone transfer "
            "attempts, DNSSEC zone walking and certificate-log names, depending on scan_type."
        ),
        properties={
            "domain": _DOMAIN,
            "scan_type": {
                "type": "string",
                "enum": list(DNSRECON_SCANS),
                "description": (
                    "std (default): standard records and a zone transfer attempt; srv: common SRV records; "
                    "axfr: zone transfer against every name server; crt: names from crt.sh; zonewalk: DNSSEC NSEC walk"
                ),
            },
        },
        required=("domain",),
        requires=Program(("dnsrecon",), "OSINT_DNSRECON"),
        install="uv tool install git+https://github.com/darkoperator/dnsrecon@1.6.3 (or a newer release tag)",
        probe=("--help",),
        run=_dnsrecon,
    ),
    Tool(
        name="whois_lookup",
        label="whois",
        title="WHOIS lookup",
        description=(
            "Registration data for a domain, IP address, network or AS number: registrar, dates, name servers, "
            "holder and contacts where public. Uses RDAP, or WHOIS for registries without RDAP."
        ),
        properties={
            "query": {"type": "string", "description": "Domain (example.com), IP address, CIDR network or AS number (AS13335)"},
        },
        required=("query",),
        run=lookups.whois_lookup,
    ),
    Tool(
        name="dns_lookup",
        label="dns",
        title="DNS lookup",
        description=(
            "DNS records of a name (A, AAAA, CNAME, MX, NS, TXT, SOA, CAA by default), or the reverse name "
            "of an IP address. Asks public DNS-over-HTTPS resolvers."
        ),
        properties={
            "name": {"type": "string", "description": "Domain name, or an IP address for a reverse (PTR) lookup"},
            "types": {
                "type": "array",
                "items": {"type": "string", "enum": list(lookups.DNS_TYPES)},
                "description": "Record types to fetch",
            },
        },
        required=("name",),
        run=lookups.dns_lookup,
    ),
    Tool(
        name="crtsh_certificate_search",
        label="crtsh",
        title="Certificate transparency search",
        description=(
            "Host names (often unlisted subdomains) and email addresses found in TLS certificates issued "
            "for a domain, from the crt.sh certificate transparency log search."
        ),
        properties={
            "domain": _DOMAIN,
            "include_expired": {
                "type": "boolean",
                "description": "Include expired certificates (default: true)",
            },
        },
        required=("domain",),
        run=lookups.crtsh_certificate_search,
    ),
    Tool(
        name="wayback_snapshots",
        label="wayback",
        title="Wayback Machine snapshots",
        description=(
            "Archived snapshots of a URL, a site or a domain in the Internet Archive's Wayback Machine, "
            "newest first, with links to view each one."
        ),
        properties={
            "url": {"type": "string", "description": "URL or domain, e.g. example.com/about"},
            "match": {
                "type": "string",
                "enum": ["exact", "prefix", "host", "domain"],
                "description": "exact URL (default), every URL under it (prefix), the whole host, or the domain with subdomains",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "description": "Number of snapshots (default: 50)"},
            "from": {"type": "string", "description": "Earliest date, e.g. 2019 or 20190131"},
            "to": {"type": "string", "description": "Latest date, e.g. 2021 or 20211231"},
        },
        required=("url",),
        run=lookups.wayback_snapshots,
    ),
    Tool(
        name="osint_toolbox_status",
        label="status",
        title="Toolbox status",
        description=(
            "Which OSINT tools this server can run on this machine, and how to install the missing ones. "
            "Call it when a tool you need is not available."
        ),
        properties={},
        required=(),
        run=_status,
        open_world=False,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}

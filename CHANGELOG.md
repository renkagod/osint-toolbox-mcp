# Changelog

The project follows [Semantic Versioning](https://semver.org/). The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [1.0.1] - 2026-09-24

### Fixed

- Run from `uvx` (or any virtual environment), the server started SpiderFoot and Blackbird checkouts without their own `.venv` with its own Python, which lacks their packages. It now looks for Python on PATH outside its own environment.
- `--check` shows tool paths in the platform's usual form.

## [1.0.0] - 2026-09-24

First release.

### Added

- MCP server over stdio with nine tools: Sherlock, Holehe, Maigret, GHunt, theHarvester, SpiderFoot, Blackbird, PhoneInfoga and ExifTool.
- Tools are found on PATH, in the folders `uv tool` and `pipx` install into, or through `OSINT_*` variables. Tools that aren't installed are not offered.
- `osint-toolbox-mcp --check` shows which tools are installed and whether they start.
- Supports MCP protocol revisions 2024-11-05 to 2025-11-25 (initialize handshake) and 2026-07-28 (stateless requests).
- Requests run concurrently. A cancelled request stops its tool together with the processes the tool started.
- Compact results: Maigret's report is reduced to profile URLs and the data found on them, SpiderFoot events are grouped by type without duplicates, and every result is capped at 100,000 characters (`OSINT_MAX_OUTPUT_CHARS`).
- Values that start with `-` are rejected, so no tool can mistake an input for an option.
- Docker image for linux/amd64 and linux/arm64 with every tool except Blackbird, which has no license that allows redistributing it.
- MCP bundle (`.mcpb`) for desktop clients that install servers with one click.

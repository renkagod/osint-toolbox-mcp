# osint-toolbox-mcp

An MCP server that lets AI agents run classic OSINT tools on your own machine: Sherlock, Maigret, Holehe, GHunt, theHarvester, SpiderFoot, Blackbird, PhoneInfoga and ExifTool. No API keys and no cloud service in between: the tools run locally and query public sources directly.

[![CI](https://github.com/renkagod/osint-toolbox-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/renkagod/osint-toolbox-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/osint-toolbox-mcp?logo=pypi&logoColor=white)](https://pypi.org/project/osint-toolbox-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/osint-toolbox-mcp?logo=python&logoColor=white)](https://pypi.org/project/osint-toolbox-mcp/)
[![Docker image](https://img.shields.io/badge/image-ghcr.io%2Frenkagod%2Fosint--toolbox--mcp-blue?logo=docker&logoColor=white)](https://github.com/renkagod/osint-toolbox-mcp/pkgs/container/osint-toolbox-mcp)
[![License: MIT](https://img.shields.io/github/license/renkagod/osint-toolbox-mcp)](https://github.com/renkagod/osint-toolbox-mcp/blob/main/LICENSE)

<!-- mcp-name: io.github.renkagod/osint-toolbox-mcp -->

Ask your assistant "which sites have an account for jane@example.com?" or "what can you find about example.com?", and it picks the tools, runs them and reads the results for you.

## Tools

| Tool | Give it | You get | Needs |
|---|---|---|---|
| `sherlock_username_search` | username | accounts on 400+ sites | Sherlock |
| `maigret_username_search` | username | accounts on up to 3000+ sites, with the profile data found on them | Maigret |
| `blackbird_username_search` | username | accounts on the 700+ sites of the WhatsMyName list | Blackbird checkout (not in the Docker image) |
| `holehe_email_search` | email address | which of about 120 sites have an account for it | Holehe |
| `ghunt_google_search` | Google account email or Gaia ID | name, profile picture, Maps reviews, calendar and other public data | GHunt, logged in |
| `theharvester_domain_search` | domain or company name | email addresses, subdomains, hosts, IP addresses | theHarvester |
| `spiderfoot_scan` | domain, IP, email, phone, username, person name... | findings grouped by type | SpiderFoot checkout |
| `phoneinfoga_scan` | phone number | country, number formats, carrier (with an API key), search queries | PhoneInfoga |
| `exiftool_metadata` | path to a local file | GPS coordinates, camera, author, software, timestamps | ExifTool |

Only installed tools are offered to the agent. Runs take from seconds to half an hour (a full SpiderFoot scan); requests run in parallel and can be cancelled.

## Quick start

Pick one:

- **Docker**: every tool but Blackbird in one image, nothing else to install.
- **uvx**: the server uses the tools installed on your machine.

### Docker

The image is large, so pull it once before adding the server; otherwise the first start can take longer than your client waits:

```
docker pull ghcr.io/renkagod/osint-toolbox-mcp
```

Add the server to your client:

```json
{
  "mcpServers": {
    "osint-toolbox": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/renkagod/osint-toolbox-mcp"]
    }
  }
}
```

Files for ExifTool, the GHunt login, API keys and proxies are covered in [Docker details](#docker-details).

### uvx

Install [uv](https://docs.astral.sh/uv/), [install the tools](#install-the-tools) you want and check what the server finds:

```
uvx osint-toolbox-mcp --check
```

Add the server to your client:

```json
{
  "mcpServers": {
    "osint-toolbox": {
      "command": "uvx",
      "args": ["osint-toolbox-mcp"]
    }
  }
}
```

To run the latest code from `main` instead of a release, use `uvx --from git+https://github.com/renkagod/osint-toolbox-mcp osint-toolbox-mcp`.

## Connect your client

One-click install:

| Client | Docker (eight tools) | uvx (your tools) |
|---|---|---|
| Cursor | [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=osint-toolbox&config=eyJjb21tYW5kIjoiZG9ja2VyIiwiYXJncyI6WyJydW4iLCItaSIsIi0tcm0iLCJnaGNyLmlvL3JlbmthZ29kL29zaW50LXRvb2xib3gtbWNwIl19) | [![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=osint-toolbox&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJvc2ludC10b29sYm94LW1jcCJdfQ%3D%3D) |
| VS Code | [![Install in VS Code](https://img.shields.io/badge/VS_Code-Install-0098FF?logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=osint-toolbox&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22-i%22%2C%22--rm%22%2C%22ghcr.io%2Frenkagod%2Fosint-toolbox-mcp%22%5D%7D) | [![Install in VS Code](https://img.shields.io/badge/VS_Code-Install-0098FF?logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=osint-toolbox&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22osint-toolbox-mcp%22%5D%7D) |
| VS Code Insiders | [![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install-24bfa5?logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=osint-toolbox&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22-i%22%2C%22--rm%22%2C%22ghcr.io%2Frenkagod%2Fosint-toolbox-mcp%22%5D%7D&quality=insiders) | [![Install in VS Code Insiders](https://img.shields.io/badge/VS_Code_Insiders-Install-24bfa5?logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=osint-toolbox&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22osint-toolbox-mcp%22%5D%7D&quality=insiders) |
| LM Studio | [![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-dark.svg)](https://lmstudio.ai/install-mcp?name=osint-toolbox&config=eyJjb21tYW5kIjoiZG9ja2VyIiwiYXJncyI6WyJydW4iLCItaSIsIi0tcm0iLCJnaGNyLmlvL3JlbmthZ29kL29zaW50LXRvb2xib3gtbWNwIl19) | [![Add to LM Studio](https://files.lmstudio.ai/deeplink/mcp-install-dark.svg)](https://lmstudio.ai/install-mcp?name=osint-toolbox&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJvc2ludC10b29sYm94LW1jcCJdfQ%3D%3D) |

**Claude Desktop**: download `osint-toolbox-mcp-<version>.mcpb` from the [latest release](https://github.com/renkagod/osint-toolbox-mcp/releases/latest) and open it. Claude Desktop installs it as an extension and asks for the optional SpiderFoot, Blackbird and ExifTool locations; the other tools are found on PATH. You can also paste the JSON above into Settings → Developer → Edit Config.

**Claude Code**:

```
claude mcp add osint-toolbox -- uvx osint-toolbox-mcp
claude mcp add osint-toolbox -- docker run -i --rm ghcr.io/renkagod/osint-toolbox-mcp
```

**Clients that read the `mcpServers` JSON above** (paste it into the file):

| Client | Where the config lives |
|---|---|
| Cursor | `~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| Cline | MCP Servers → Configure → `cline_mcp_settings.json` |
| Roo Code | `.roo/mcp.json` in a project, or the global MCP settings |
| Gemini CLI | `~/.gemini/settings.json` |
| Antigravity | agent panel "…" → MCP Servers → Manage MCP Servers → View raw config |
| LM Studio | Program tab → Install → Edit `mcp.json` |
| Kiro | `~/.kiro/settings/mcp.json`, or `.kiro/settings/mcp.json` in a project |

Clients with their own format (shown with uvx; for Docker, use `docker` with the arguments `run -i --rm ghcr.io/renkagod/osint-toolbox-mcp`):

<details>
<summary>VS Code</summary>

```
code --add-mcp '{"name":"osint-toolbox","command":"uvx","args":["osint-toolbox-mcp"]}'
```

Or in `.vscode/mcp.json`:

```json
{
  "servers": {
    "osint-toolbox": {
      "type": "stdio",
      "command": "uvx",
      "args": ["osint-toolbox-mcp"]
    }
  }
}
```

</details>

<details>
<summary>Codex CLI</summary>

```
codex mcp add osint-toolbox -- uvx osint-toolbox-mcp
```

Or in `~/.codex/config.toml`, with a longer timeout for slow scans:

```toml
[mcp_servers.osint-toolbox]
command = "uvx"
args = ["osint-toolbox-mcp"]
tool_timeout_sec = 1800
```

</details>

<details>
<summary>Zed</summary>

In `settings.json`:

```json
{
  "context_servers": {
    "osint-toolbox": {
      "command": "uvx",
      "args": ["osint-toolbox-mcp"],
      "env": {}
    }
  }
}
```

</details>

<details>
<summary>Goose</summary>

In `~/.config/goose/config.yaml`:

```yaml
extensions:
  osint-toolbox:
    name: osint-toolbox
    type: stdio
    cmd: uvx
    args: [osint-toolbox-mcp]
    enabled: true
    timeout: 1800
```

</details>

<details>
<summary>opencode</summary>

In `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "osint-toolbox": {
      "type": "local",
      "command": ["uvx", "osint-toolbox-mcp"],
      "enabled": true
    }
  }
}
```

</details>

<details>
<summary>Continue</summary>

In `.continue/mcpServers/osint-toolbox.yaml`:

```yaml
name: OSINT Toolbox
version: 1.0.0
schema: v1
mcpServers:
  - name: osint-toolbox
    type: stdio
    command: uvx
    args:
      - osint-toolbox-mcp
```

</details>

## Install the tools

Skip this if you use Docker, unless you want Blackbird. Otherwise install any subset. Put each Python tool in its own environment with `uv tool install` (or `pipx install`): their dependencies conflict with each other.

| Tool | Install | Tested with |
|---|---|---|
| Sherlock | `uv tool install sherlock-project` | 0.16 |
| Holehe | `uv tool install holehe` | 1.61 |
| Maigret | `uv tool install maigret` | 0.6 |
| GHunt | `uv tool install ghunt`, then `ghunt login` | 2.3.4 |
| theHarvester | `uv tool install git+https://github.com/laramies/theHarvester` | 4.11.1 |
| PhoneInfoga | a binary from [its releases](https://github.com/sundowndev/phoneinfoga/releases), on PATH | 2.11.0 |
| ExifTool | [exiftool.org](https://exiftool.org), `brew install exiftool` or `apt install libimage-exiftool-perl` | 13.59 |
| SpiderFoot | a checkout, see below | commit `0f815a2` |
| Blackbird | a checkout, see below | commit `b455050` |

SpiderFoot and Blackbird run from git checkouts. Give each its own `.venv`, which the server picks up automatically, and tell the server where the checkout is:

```
git clone https://github.com/smicallef/spiderfoot
cd spiderfoot
uv venv --python 3.12
uv pip install -r requirements.txt
```

Then set `OSINT_SPIDERFOOT_DIR` to that folder in your client's config (`env`). Blackbird is the same with `https://github.com/antoniaci/blackbird` and `OSINT_BLACKBIRD_DIR`. SpiderFoot pins `lxml<5`, which has no builds for Python 3.13 and newer; to use a newer Python, apply [`patches/spiderfoot-requirements.patch`](https://github.com/renkagod/osint-toolbox-mcp/blob/main/patches/spiderfoot-requirements.patch) first.

Finally, check: `uvx osint-toolbox-mcp --check` lists every tool as `ok`, `missing` (with how to install it) or `broken` (found but fails to start).

## Configuration

All settings are environment variables, set in the `env` block of your client's config:

```json
{
  "mcpServers": {
    "osint-toolbox": {
      "command": "uvx",
      "args": ["osint-toolbox-mcp"],
      "env": {
        "OSINT_SPIDERFOOT_DIR": "/home/me/spiderfoot",
        "OSINT_EXIFTOOL": "/opt/exiftool/exiftool"
      }
    }
  }
}
```

| Variable | Meaning |
|---|---|
| `OSINT_SHERLOCK`, `OSINT_HOLEHE`, `OSINT_MAIGRET`, `OSINT_GHUNT`, `OSINT_THEHARVESTER`, `OSINT_PHONEINFOGA`, `OSINT_EXIFTOOL` | Full path to the tool, when it isn't on PATH |
| `OSINT_SPIDERFOOT_DIR`, `OSINT_BLACKBIRD_DIR` | Folder of the SpiderFoot or Blackbird checkout |
| `OSINT_SPIDERFOOT_PYTHON`, `OSINT_BLACKBIRD_PYTHON` | Python to run the checkout with; by default its `.venv`, then `python` on PATH |
| `OSINT_MAX_OUTPUT_CHARS` | Longest result returned to the model, 100000 by default; `0` for no limit |
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` | Passed on to the tools; whether a tool uses them depends on the tool |

Besides PATH, the server looks in the folders `uv tool` and `pipx` install into (`~/.local/bin` by default), which desktop apps often leave out of PATH.

## Docker details

- **Blackbird** is not in the image: it has no license that allows redistributing it. Install it yourself to use it.
- **ExifTool**: the container sees only mounted files. Add `-v /path/to/files:/data:ro` to the arguments and ask about `/data/photo.jpg`.
- **GHunt**: log in once into a named volume, then mount it:

  ```
  docker run -it --rm --entrypoint ghunt -v osint-toolbox-ghunt:/home/osint/.malfrats ghcr.io/renkagod/osint-toolbox-mcp login
  ```

  GHunt's listening mode (option 1) doesn't work in a container; pick option 2 (paste from the GHunt Companion extension) or 3 (an `oauth_token`, see [GHunt's README](https://github.com/mxrch/GHunt#readme)).

- **API keys**: theHarvester reads `/home/osint/.theHarvester/api-keys.yaml` (mount your file there), PhoneInfoga reads its keys from environment variables (`-e NAME=value`).
- **Proxy**: `-e HTTPS_PROXY=http://host.docker.internal:8080`, for example.
- **Tags**: `latest` and version tags such as `1.0.0` for releases, `edge` for the current `main`. Built for linux/amd64 and linux/arm64.

A full configuration:

```json
{
  "mcpServers": {
    "osint-toolbox": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-v", "/home/me/osint-files:/data:ro",
        "-v", "osint-toolbox-ghunt:/home/osint/.malfrats",
        "ghcr.io/renkagod/osint-toolbox-mcp"
      ]
    }
  }
}
```

## Example requests

- "Which sites have an account registered to jane.doe@example.com?"
- "Search for the username jdoe_1987 with Sherlock and Maigret and compare what they find."
- "What subdomains and email addresses are public for example.com?"
- "Read the metadata of /home/me/photo.jpg and tell me where and with what it was taken."
- "Run a passive SpiderFoot scan of example.com and summarize the findings."

## Troubleshooting

- **A tool is missing.** Run `osint-toolbox-mcp --check` (or `docker run --rm ghcr.io/renkagod/osint-toolbox-mcp --check`). Desktop apps often start servers with a shorter PATH than your terminal; set the tool's `OSINT_*` variable to its full path.
- **Long scans time out.** Many clients stop waiting for a tool after a minute or so. Raise the limit where your client allows it: `MCP_TOOL_TIMEOUT` in milliseconds for Claude Code, `tool_timeout_sec` for Codex CLI, `timeout` in milliseconds on the server entry for Gemini CLI, `timeout` in seconds for Goose. Otherwise ask for faster runs: a `passive` SpiderFoot scan, Maigret without `all_sites`.
- **GHunt fails.** It needs a valid login: run `ghunt login`. When the saved session has been revoked, `ghunt login` itself fails; run `ghunt login --clean` to delete it, then `ghunt login`.
- **Empty results, errors or captchas.** Sites rate-limit and change their pages; retry later, lower the load, or go through a proxy. If a tool fails the same way outside the server, report it to that tool's project.
- **Windows and `.bat` or `.cmd` wrappers.** Arguments to such wrappers pass through `cmd.exe`, so the server refuses inputs with characters like `&` or `|`; point the `OSINT_*` variable at the real executable instead.

## Responsible use

These tools collect information about real people and organizations. Use them only where you have a lawful basis and authorization: your own accounts, security assessments within scope, research that respects privacy law (GDPR, CCPA and local equivalents) and the sites' terms of service. Don't use them to stalk, harass, dox or otherwise harm anyone. You are responsible for what you run and for what you do with the results.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](https://github.com/renkagod/osint-toolbox-mcp/blob/main/CONTRIBUTING.md). Report vulnerabilities privately as described in [SECURITY.md](https://github.com/renkagod/osint-toolbox-mcp/blob/main/SECURITY.md). Changes are listed in the [changelog](https://github.com/renkagod/osint-toolbox-mcp/blob/main/CHANGELOG.md).

## License and credits

MIT, see [LICENSE](https://github.com/renkagod/osint-toolbox-mcp/blob/main/LICENSE).

The tools belong to their authors and keep their own licenses: [Sherlock](https://github.com/sherlock-project/sherlock), [Maigret](https://github.com/soxoj/maigret), [Holehe](https://github.com/megadose/holehe), [GHunt](https://github.com/mxrch/GHunt), [theHarvester](https://github.com/laramies/theHarvester), [SpiderFoot](https://github.com/smicallef/spiderfoot), [Blackbird](https://github.com/antoniaci/blackbird), [PhoneInfoga](https://github.com/sundowndev/phoneinfoga), [ExifTool](https://exiftool.org). The server starts them as separate programs; the Docker image contains them unmodified.

This project started from [frishtik/osint-tools-mcp-server](https://github.com/frishtik/osint-tools-mcp-server) (MIT).

# osint-toolbox-mcp

An MCP server that lets AI agents run classic OSINT tools on your own machine: Sherlock, Maigret, Blackbird, Holehe, GHunt, theHarvester, SpiderFoot, subfinder, dnstwist, dnsrecon, PhoneInfoga and ExifTool, plus built-in WHOIS, DNS, certificate transparency and Wayback Machine lookups. No API keys and no cloud service in between: the tools run locally and query public sources directly.

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
| `subfinder_subdomain_search` | domain | subdomains from passive sources, with the sources that reported them | subfinder |
| `dnstwist_lookalike_domains` | domain | registered lookalike domains (typos, homoglyphs, other TLDs) with their A, MX and NS records | dnstwist |
| `dnsrecon_domain_scan` | domain | DNS records, zone transfer attempts, DNSSEC zone walking | dnsrecon |
| `whois_lookup` | domain, IP address, network or AS number | registrar, dates, name servers, holder and contacts where public (RDAP, or WHOIS) | built in |
| `dns_lookup` | domain name or IP address | A, AAAA, CNAME, MX, NS, TXT, SOA, CAA records, or the reverse name | built in |
| `crtsh_certificate_search` | domain | host names and email addresses from TLS certificates issued for it (crt.sh) | built in |
| `wayback_snapshots` | URL or domain | archived snapshots in the Wayback Machine, newest first | built in |
| `osint_toolbox_status` | nothing | which tools are installed, and how to install the missing ones | built in |

Only installed tools are offered to the agent. Runs take from seconds to half an hour (a full SpiderFoot scan); requests run in parallel and can be cancelled.

## Quick start

Pick one:

- **Docker**: every tool but Blackbird in one image, nothing else to install.
- **uvx**: one command installs the tools on your machine, without admin rights.

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

Install [uv](https://docs.astral.sh/uv/), then install the tools. This installs everything that is missing and checks that each tool starts; see [Install the tools](#install-the-tools) for what it does:

```
uvx osint-toolbox-mcp --install
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

| Client | Docker (all but Blackbird) | uvx (your tools) |
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

Skip this if you use Docker, unless you want Blackbird.

```
uvx osint-toolbox-mcp --install
```

installs every tool that is missing, without admin rights, then checks that each one starts. `uvx osint-toolbox-mcp --install sherlock maigret` installs only the tools named. It needs [uv](https://docs.astral.sh/uv/) and:

- puts each Python tool (Sherlock, Holehe, Maigret, GHunt, theHarvester, dnstwist, dnsrecon) in its own environment with `uv tool install`, on Python 3.12: their dependencies conflict with each other, and some have no builds for newer Pythons;
- downloads SpiderFoot and Blackbird from GitHub, each with its own virtual environment;
- downloads PhoneInfoga, subfinder and ExifTool and checks them against the checksums their authors publish. On macOS and Linux, ExifTool needs Perl, which those systems usually have.

Checkouts and downloads go to `%LOCALAPPDATA%\osint-toolbox-mcp` on Windows, `~/Library/Application Support/osint-toolbox-mcp` on macOS and `~/.local/share/osint-toolbox-mcp` on Linux; set `OSINT_TOOLBOX_HOME` to use another folder. The server looks there by itself. GHunt still needs a one-time `ghunt login` afterwards.

`uvx osint-toolbox-mcp --check` shows, at any time, every tool as `ok`, `missing` (with how to install it) or `broken` (found but fails to start). The agent can ask the same through the `osint_toolbox_status` tool.

### Installing by hand

| Tool | Install | Tested with |
|---|---|---|
| Sherlock | `uv tool install sherlock-project` | 0.16 |
| Holehe | `uv tool install holehe` | 1.61 |
| Maigret | `uv tool install maigret` | 0.6 |
| GHunt | `uv tool install ghunt`, then `ghunt login` | 2.3.4 |
| theHarvester | `uv tool install git+https://github.com/laramies/theHarvester` | 4.11.1 |
| dnstwist | `uv tool install "dnstwist[full]"` | 20250130 |
| dnsrecon | `uv tool install git+https://github.com/darkoperator/dnsrecon` | 1.6.3 |
| subfinder | a binary from [its releases](https://github.com/projectdiscovery/subfinder/releases), on PATH | 2.16.0 |
| PhoneInfoga | a binary from [its releases](https://github.com/sundowndev/phoneinfoga/releases), on PATH | 2.11.0 |
| ExifTool | [exiftool.org](https://exiftool.org), `brew install exiftool` or `apt install libimage-exiftool-perl` | 13.59 |
| SpiderFoot | a checkout, see below | commit `0f815a2` |
| Blackbird | a checkout, see below | commit `b455050` |

If a Python tool fails to build on your default Python, add `--python 3.12` to its `uv tool install`.

SpiderFoot and Blackbird run from git checkouts. Give each its own `.venv`, which the server picks up automatically, and tell the server where the checkout is:

```
git clone https://github.com/smicallef/spiderfoot
cd spiderfoot
uv venv --python 3.12
uv pip install -r requirements.txt
```

Then set `OSINT_SPIDERFOOT_DIR` to that folder in your client's config (`env`). Blackbird is the same with `https://github.com/antoniaci/blackbird` and `OSINT_BLACKBIRD_DIR`. SpiderFoot pins `lxml<5`, which has no builds for Python 3.13 and newer; to use a newer Python, apply [`patches/spiderfoot-requirements.patch`](https://github.com/renkagod/osint-toolbox-mcp/blob/main/patches/spiderfoot-requirements.patch) first.

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
| `OSINT_SHERLOCK`, `OSINT_HOLEHE`, `OSINT_MAIGRET`, `OSINT_GHUNT`, `OSINT_THEHARVESTER`, `OSINT_SUBFINDER`, `OSINT_DNSTWIST`, `OSINT_DNSRECON`, `OSINT_PHONEINFOGA`, `OSINT_EXIFTOOL` | Full path to the tool, when it isn't on PATH |
| `OSINT_SPIDERFOOT_DIR`, `OSINT_BLACKBIRD_DIR` | Folder of the SpiderFoot or Blackbird checkout |
| `OSINT_SPIDERFOOT_PYTHON`, `OSINT_BLACKBIRD_PYTHON` | Python to run the checkout with; by default its `.venv`, then `python` on PATH |
| `OSINT_TOOLBOX_HOME` | Where `--install` puts checkouts and downloads, and where the server looks for them |
| `OSINT_MAX_OUTPUT_CHARS` | Longest result returned to the model, 100000 by default; `0` for no limit |
| `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` | Used by the built-in lookups and `--install` (HTTP and SOCKS5 proxies), and passed on to the tools, which may or may not use them |

Besides PATH, the server looks in the `--install` folder and in the folders `uv tool` and `pipx` install into (`~/.local/bin` by default), which desktop apps often leave out of PATH.

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
- "Which lookalike domains of example.com are registered, and do any of them have mail servers?"
- "Who owns example.com and when does it expire? Show me how its homepage looked in 2015."
- "Read the metadata of /home/me/photo.jpg and tell me where and with what it was taken."
- "Run a passive SpiderFoot scan of example.com and summarize the findings."

## Troubleshooting

- **A tool is missing.** Run `uvx osint-toolbox-mcp --install`, or `--check` to see why a tool isn't found (`docker run --rm ghcr.io/renkagod/osint-toolbox-mcp --check` for the image). After installing, restart your client so it lists the new tools. Desktop apps often start servers with a shorter PATH than your terminal; set the tool's `OSINT_*` variable to its full path.
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

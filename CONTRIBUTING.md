# Contributing

Bug reports, fixes and new tools are welcome. Every pull request is reviewed by the maintainer before it is merged; this is a spare-time project, so reviews can take a while.

## Setup

You need [uv](https://docs.astral.sh/uv/). From a clone:

```
uv run pytest                        # tests, no OSINT tools needed
uv run osint-toolbox-mcp --check     # which tools this machine has
```

The server has no runtime dependencies and should stay that way: every tool is a separate program it starts.

## Adding a tool

1. Add a `Tool` entry and its handler in `src/osint_toolbox_mcp/tools.py`. Check every input, never pass a value that starts with `-`, and return compact text: the model reads all of it.
2. Test the handler with the fake runner in `tests/test_tools.py`; tests must not need the real tool or the network.
3. Install it in the `Dockerfile` (pinned version) and list it in `mcpb/manifest.json`, the README and the CHANGELOG.

## Pull requests

- One topic per pull request, with a short description of what changes and why.
- Tests, fixtures and screenshots must not contain real people's data.

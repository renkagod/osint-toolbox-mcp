"""Call tools through the server over stdio and fail if any of them reports an error.

    python scripts/try_tools.py dns_lookup '{"name": "example.com"}' whois_lookup '{"query": "example.com"}'
"""

import json
import subprocess
import sys


def main(arguments: list[str]) -> int:
    calls = [(name, json.loads(values)) for name, values in zip(arguments[::2], arguments[1::2])]
    server = subprocess.Popen(
        [sys.executable, "-m", "osint_toolbox_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    messages = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}]
    messages += [
        {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {"name": name, "arguments": values}}
        for number, (name, values) in enumerate(calls, 1)
    ]
    for message in messages:
        server.stdin.write(json.dumps(message) + "\n")
    server.stdin.flush()

    # Keep stdin open until every answer is in: closing it tells the server to stop running tools
    pending, failed = {number: name for number, (name, _) in enumerate(calls, 1)}, 0
    while pending:
        reply = json.loads(server.stdout.readline())
        name = pending.pop(reply.get("id"), None)
        if name is None:
            continue
        result = reply.get("result") or {}
        output = result["content"][0]["text"] if result else json.dumps(reply.get("error"))
        ok = bool(result) and not result.get("isError")
        failed += not ok
        print(f"{'ok' if ok else 'FAILED':<6} {name}: {output[:400]}\n", flush=True)
    server.stdin.close()
    server.wait(60)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

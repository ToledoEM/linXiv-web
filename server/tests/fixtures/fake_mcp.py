"""Stand-in for linxiv-mcp in tests: newline-delimited JSON-RPC over stdio."""

import json
import sys
import time

TOOLS = [
    "get_settings",
    "list_papers",
    "create_note",
    "merge_papers",
    "download_pdf",
    "brand_new_tool",
]

for line in sys.stdin:
    msg = json.loads(line)
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        continue  # notification
    # A server notification first: the bridge must skip it.
    print(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {}}), flush=True
    )
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake"},
        }
    elif method == "tools/list":
        result = {"tools": [{"name": n, "inputSchema": {"type": "object"}} for n in TOOLS]}
    elif method == "tools/call":
        text = json.dumps({"called": msg["params"]["name"], "args": msg["params"].get("arguments")})
        result = {"content": [{"type": "text", "text": text}]}
    elif method == "slow":
        time.sleep(30)
        result = {}
    elif method == "crash":
        sys.exit(1)
    else:
        print(
            json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "no"}}),
            flush=True,
        )
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)

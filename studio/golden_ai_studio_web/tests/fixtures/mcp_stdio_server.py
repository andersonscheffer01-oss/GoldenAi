"""Controlled local MCP fixture for E3 tests; never used by production."""

import json
import sys
import time
from pathlib import Path


MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
MARKER = Path(sys.argv[2]) if len(sys.argv) > 2 else None


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        continue
    if MODE == "crash":
        raise SystemExit(3)
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request_id, "result": {
            "protocolVersion": request["params"]["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "golden-test-mcp", "version": "1"},
        }})
    elif method == "tools/list":
        if MODE == "malformed":
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "tools": [{"name": "bad", "inputSchema": {"type": "unknown"}}]
            }})
            continue
        send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [
            {"name": "read_echo", "description": "Reads a value",
             "inputSchema": {"type": "object", "properties": {
                 "message": {"type": "string"}}, "required": ["message"],
                 "additionalProperties": False}},
            {"name": "write_like", "description": "Mutation-like fixture tool",
             "inputSchema": {"type": "object", "properties": {
                 "value": {"type": "string"}}, "required": ["value"],
                 "additionalProperties": False}},
        ]}})
    elif method == "tools/call":
        name = request["params"]["name"]
        args = request["params"].get("arguments", {})
        if MODE == "slow":
            time.sleep(5)
        if name == "read_echo":
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": args["message"]}],
                "structuredContent": {"echo": args["message"]}}})
        elif name == "write_like":
            if MARKER:
                MARKER.write_text(args["value"], encoding="utf-8")
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "content": [{"type": "text", "text": "written"}]}})
        else:
            send({"jsonrpc": "2.0", "id": request_id, "error": {
                "code": -32602, "message": "unknown tool"}})

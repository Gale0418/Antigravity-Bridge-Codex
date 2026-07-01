#!/usr/bin/env python3
"""Minimal MCP stdio server for the local Antigravity bridge.

The server intentionally wraps the Python fallback instead of duplicating RPC
logic. It keeps the tool path available when a Codex thread loses the skill-only
capability snapshot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import antigravity_bridge as bridge  # noqa: E402


PROTOCOL_VERSION = "2024-11-05"


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.lower()] = value.strip()

    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def text_result(value: Any, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, indent=2),
            }
        ],
        "isError": is_error,
    }


def tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "antigravity_discover",
            "description": "Discover the current local Antigravity session from logs.",
            "inputSchema": {
                "type": "object",
                "properties": {"show_secret": {"type": "boolean", "default": False}},
            },
        },
        {
            "name": "antigravity_smoke",
            "description": "Start a local Antigravity cascade and wait for a marker.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_path": {"type": "string"},
                    "prompt": {"type": "string", "default": "Please reply only BRIDGE_OK"},
                    "pattern": {"type": "string", "default": "BRIDGE_OK"},
                    "model": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "integer", "default": 90},
                    "allow_timeout": {"type": "boolean", "default": False},
                    "include_trajectory": {"type": "boolean", "default": False},
                },
            },
        },
        {
            "name": "antigravity_start",
            "description": "Start a local Antigravity cascade, send an opening prompt, and wait for a pattern.",
            "inputSchema": {
                "type": "object",
                "required": ["opening_prompt"],
                "properties": {
                    "workspace_path": {"type": "string"},
                    "opening_prompt": {"type": "string"},
                    "wait_pattern": {"type": "string", "default": "(?s).+"},
                    "model": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "integer", "default": 90},
                    "allow_timeout": {"type": "boolean", "default": False},
                    "include_trajectory": {"type": "boolean", "default": False},
                },
            },
        },
        {
            "name": "antigravity_send",
            "description": "Send a message to an existing local Antigravity cascade and wait for a pattern.",
            "inputSchema": {
                "type": "object",
                "required": ["cascade_id", "text"],
                "properties": {
                    "cascade_id": {"type": "string"},
                    "text": {"type": "string"},
                    "wait_pattern": {"type": "string", "default": "(?s).+"},
                    "model": {"type": "string", "default": ""},
                    "timeout_seconds": {"type": "integer", "default": 90},
                    "allow_timeout": {"type": "boolean", "default": False},
                    "omit_requested_model": {"type": "boolean", "default": False},
                    "include_trajectory": {"type": "boolean", "default": False},
                },
            },
        },
        {
            "name": "antigravity_trajectory",
            "description": "Read the raw trajectory for an existing local Antigravity cascade.",
            "inputSchema": {
                "type": "object",
                "required": ["cascade_id"],
                "properties": {
                    "cascade_id": {"type": "string"},
                    "verbosity": {"type": "integer", "default": 2},
                },
            },
        },
    ]


def require_string(arguments: dict[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Missing required string argument: {name}")
    return value


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "antigravity_discover":
        session = bridge.get_session_info()
        return session.public_dict(bool(arguments.get("show_secret", False)))

    if name == "antigravity_smoke":
        session = bridge.get_session_info()
        cascade = bridge.new_cascade([arguments.get("workspace_path") or str(REPO_ROOT)], arguments.get("model", ""), session=session)
        bridge.send_message(cascade["cascadeId"], arguments.get("prompt", "Please reply only BRIDGE_OK"), arguments.get("model", ""), session=session)
        outcome = bridge.wait_trajectory_outcome(
            cascade["cascadeId"],
            arguments.get("pattern", "BRIDGE_OK"),
            int(arguments.get("timeout_seconds", 90)),
            session=session,
        )
        if outcome["timedOut"] and not arguments.get("allow_timeout", False):
            raise RuntimeError(
                f"Tool '{name}' timed out waiting for pattern {outcome['pattern']} in cascade {outcome['cascadeId']}."
            )
        return {
            "action": "smoke",
            "cascadeId": cascade["cascadeId"],
            "workspacePath": arguments.get("workspace_path") or str(REPO_ROOT),
            **bridge.compact_outcome(outcome, bool(arguments.get("include_trajectory", False))),
        }

    if name == "antigravity_start":
        opening_prompt = require_string(arguments, "opening_prompt")
        session = bridge.get_session_info()
        cascade = bridge.new_cascade([arguments.get("workspace_path") or str(REPO_ROOT)], arguments.get("model", ""), session=session)
        bridge.send_message(cascade["cascadeId"], opening_prompt, arguments.get("model", ""), session=session)
        outcome = bridge.wait_trajectory_outcome(
            cascade["cascadeId"],
            arguments.get("wait_pattern", "(?s).+"),
            int(arguments.get("timeout_seconds", 90)),
            session=session,
        )
        if outcome["timedOut"] and not arguments.get("allow_timeout", False):
            raise RuntimeError(
                f"Tool '{name}' timed out waiting for pattern {outcome['pattern']} in cascade {outcome['cascadeId']}."
            )
        return {
            "action": "start",
            "cascadeId": cascade["cascadeId"],
            "workspacePath": arguments.get("workspace_path") or str(REPO_ROOT),
            **bridge.compact_outcome(outcome, bool(arguments.get("include_trajectory", False))),
        }

    if name == "antigravity_send":
        cascade_id = require_string(arguments, "cascade_id")
        text = require_string(arguments, "text")
        session = bridge.get_session_info()
        bridge.send_message(
            cascade_id,
            text,
            arguments.get("model", ""),
            bool(arguments.get("omit_requested_model", False)),
            session,
        )
        outcome = bridge.wait_trajectory_outcome(
            cascade_id,
            arguments.get("wait_pattern", "(?s).+"),
            int(arguments.get("timeout_seconds", 90)),
            session=session,
        )
        if outcome["timedOut"] and not arguments.get("allow_timeout", False):
            raise RuntimeError(
                f"Tool '{name}' timed out waiting for pattern {outcome['pattern']} in cascade {outcome['cascadeId']}."
            )
        return {"action": "send", **bridge.compact_outcome(outcome, bool(arguments.get("include_trajectory", False)))}

    if name == "antigravity_trajectory":
        cascade_id = require_string(arguments, "cascade_id")
        session = bridge.get_session_info()
        return bridge.get_trajectory(cascade_id, int(arguments.get("verbosity", 2)), session)

    raise RuntimeError(f"Unknown tool: {name}")


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    if request_id is None:
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {"name": "antigravity-bridge-codex", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": tools()}
        elif method == "tools/call":
            params = request.get("params") or {}
            result = text_result(call_tool(params.get("name", ""), params.get("arguments") or {}))
        elif method == "ping":
            result = {}
        else:
            raise RuntimeError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        if method == "tools/call":
            return {"jsonrpc": "2.0", "id": request_id, "result": text_result({"error": str(exc)}, True)}
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": str(exc)}}


def main() -> int:
    while True:
        request = read_message()
        if request is None:
            return 0
        response = handle_request(request)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())

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


def read_message() -> Any | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(payload + b"\n")
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
            "name": "antigravity_prompt",
            "description": "Run an idempotent Hub-native visible RPC prompt first; retain request_id and reuse it for retries. Auto falls back to agy only before delivery begins.",
            "inputSchema": {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string"},
                    "conversation_id": {"type": "string", "default": ""},
                    "workspace_path": {"type": "string", "default": ""},
                    "model": {"type": "string", "default": bridge.DEFAULT_AGY_MODEL},
                    "transport": {"type": "string", "enum": ["auto", "rpc", "agy"], "default": "auto"},
                    "timeout_seconds": {"type": "integer", "default": 90},
                    "agy_executable": {"type": "string", "default": "agy"},
                    "no_transcript": {"type": "boolean", "default": False},
                    "project_id": {"type": "string", "default": ""},
                    "request_id": {"type": "string", "default": ""},
                    "mission_id": {"type": "string", "default": ""},
                    "lane_id": {"type": "string", "default": ""},
                    "auto_launch": {"type": "boolean", "default": True, "description": "Open the Antigravity GUI only when pre-dispatch discovery confirms no live session; set false to disable."},
                    "auto_launch_timeout_seconds": {"type": "number", "default": 30.0},
                    "auto_launch_poll_interval_seconds": {"type": "number", "default": 0.5},
                    "gui_path": {"type": "string", "default": ""},
                },
            },
        },
        {
            "name": "antigravity_discover",
            "description": "Legacy diagnostic tool: discover the current local Antigravity session from logs.",
            "inputSchema": {
                "type": "object",
                "properties": {"show_secret": {"type": "boolean", "default": False}},
            },
        },
        {
            "name": "antigravity_smoke",
            "description": "Legacy diagnostic tool: start a local Antigravity cascade and wait for a marker.",
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
            "description": "Legacy diagnostic tool: start a local Antigravity cascade, send an opening prompt, and wait for a pattern.",
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
            "description": "Legacy diagnostic tool: send a message to an existing local Antigravity cascade and wait for a pattern.",
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
            "description": "Legacy diagnostic tool: read the raw trajectory for an existing local Antigravity cascade.",
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


def optional_bool(arguments: dict[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if not isinstance(value, bool):
        raise RuntimeError(f"Argument '{name}' must be a boolean")
    return value


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "antigravity_prompt":
        prompt = require_string(arguments, "prompt")
        receipt = bridge.run_prompt(
            prompt,
            conversation_id=str(arguments.get("conversation_id") or ""),
            model=str(arguments.get("model") or bridge.DEFAULT_AGY_MODEL),
            transport=str(arguments.get("transport") or "auto"),
            timeout_seconds=int(arguments.get("timeout_seconds", 90)),
            executable=str(arguments.get("agy_executable") or ""),
            workspace_path=str(arguments.get("workspace_path") or ""),
            no_transcript=bool(arguments.get("no_transcript", False)),
            project_id=str(arguments.get("project_id") or ""),
            request_id=str(arguments.get("request_id") or ""),
            mission_id=str(arguments.get("mission_id") or ""),
            lane_id=str(arguments.get("lane_id") or ""),
            auto_launch=optional_bool(arguments, "auto_launch", True),
            auto_launch_timeout_seconds=float(arguments.get("auto_launch_timeout_seconds", 30.0)),
            auto_launch_poll_interval_seconds=float(arguments.get("auto_launch_poll_interval_seconds", 0.5)),
            gui_path=str(arguments.get("gui_path") or ""),
        )
        if not isinstance(receipt, dict):
            raise RuntimeError("Antigravity prompt returned an invalid receipt")
        return receipt
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
            tool_name = params.get("name", "")
            tool_result = call_tool(tool_name, params.get("arguments") or {})
            is_error = (
                tool_name == "antigravity_prompt"
                and isinstance(tool_result, dict)
                and str(tool_result.get("status") or "").upper() in {"ERROR", "TIMEOUT", "CONFLICT"}
                and str(tool_result.get("delivery_state") or "") not in {"IN_PROGRESS", "DELIVERING", "DELIVERY_UNKNOWN", "ACCEPTED_PENDING", "INPUT_REQUIRED"}
            )
            result = text_result(tool_result, is_error)
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
        try:
            request = read_message()
        except (UnicodeDecodeError, json.JSONDecodeError):
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue
        if request is None:
            return 0
        if not isinstance(request, dict):
            write_message(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"},
                }
            )
            continue
        response = handle_request(request)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())

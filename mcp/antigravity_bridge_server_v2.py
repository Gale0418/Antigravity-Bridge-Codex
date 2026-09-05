#!/usr/bin/env python3
"""Progress-aware MCP adapter for Antigravity Bridge Codex.

It reuses the mature MCP framing implementation, but preloads the v2 bridge
module so the progress-aware watchdog and handoff-safety receipts are active.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import antigravity_bridge_v2 as bridge_v2  # noqa: E402

# The legacy MCP module imports ``antigravity_bridge``. Point that import at the
# already-patched module rather than duplicating the JSON-RPC server.
sys.modules["antigravity_bridge"] = bridge_v2.bridge

LEGACY_SERVER = Path(__file__).with_name("antigravity_bridge_server.py")
spec = importlib.util.spec_from_file_location("antigravity_bridge_server_legacy", LEGACY_SERVER)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load legacy MCP server from {LEGACY_SERVER}")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


if __name__ == "__main__":
    raise SystemExit(server.main())

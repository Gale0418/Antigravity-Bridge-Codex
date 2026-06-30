#!/usr/bin/env python3
"""Install the Antigravity bridge skill and local plugin package into Codex."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


SKILL_ITEMS = (
    "SKILL.md",
    "agents",
    "assets",
    "references",
    "scripts",
    "mcp",
    ".mcp.json",
)


def legacy_plugin_name() -> str:
    return "antigravity-" + "gemini" + "-bridge"


def normalize_mcp_manifest(manifest_path: Path) -> None:
    if not manifest_path.exists():
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    server = manifest.get("mcpServers", {}).get("antigravity-bridge-codex")
    if not isinstance(server, dict):
        return

    server.setdefault("type", "stdio")
    if os.name == "nt" and server.get("command") == "python3":
        server["command"] = "python"

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def copy_fresh_item(source: Path, destination: Path) -> None:
    if not source.exists():
        return

    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def get_codex_home() -> Path:
    env_path = os.environ.get("CODEX_HOME")
    if env_path:
        return Path(env_path).expanduser()
    return Path.home() / ".codex"


def get_codex_executable(codex_home: Path) -> Path | None:
    for candidate in (
        codex_home / ".sandbox-bin" / "codex",
        codex_home / ".sandbox-bin" / "codex.exe",
    ):
        if candidate.exists():
            return candidate

    for name in ("codex", "codex.exe"):
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved)

    return None


def run_native_or_throw(executable: Path, *arguments: str) -> None:
    command = [str(executable), *arguments]
    subprocess.run(command, check=True)


def run_native_best_effort(executable: Path, *arguments: str) -> None:
    command = [str(executable), *arguments]
    subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def remove_path_best_effort(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def remove_legacy_install(codex_home: Path, codex_executable: Path | None) -> None:
    legacy_name = legacy_plugin_name()
    legacy_marketplace = f"{legacy_name}-local"

    if codex_executable is not None:
        run_native_best_effort(codex_executable, "plugin", "remove", f"{legacy_name}@{legacy_marketplace}")
        run_native_best_effort(codex_executable, "plugin", "marketplace", "remove", legacy_marketplace)

    for path in (
        codex_home / "skills" / legacy_name,
        codex_home / "local-marketplaces" / legacy_name,
        codex_home / "plugins" / "cache" / legacy_marketplace,
    ):
        remove_path_best_effort(path)


def main() -> int:
    source_root = Path(__file__).resolve().parent
    codex_home = get_codex_home()
    codex_executable = get_codex_executable(codex_home)
    remove_legacy_install(codex_home, codex_executable)

    skill_root = codex_home / "skills" / "antigravity-bridge-codex"
    marketplace_root = codex_home / "local-marketplaces" / "antigravity-bridge-codex"
    marketplace_manifest_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    plugin_root = marketplace_root / "plugins" / "antigravity-bridge-codex"
    plugin_skill_root = plugin_root / "skills" / "antigravity-bridge-codex"
    repo_plugin_manifest_path = source_root / ".codex-plugin" / "plugin.json"
    installed_plugin_manifest_path = plugin_root / ".codex-plugin" / "plugin.json"

    skill_root.mkdir(parents=True, exist_ok=True)
    print(f"Installing personal skill from {source_root} to {skill_root}")
    for item in SKILL_ITEMS:
        copy_fresh_item(source_root / item, skill_root / item)
    normalize_mcp_manifest(skill_root / ".mcp.json")

    if not repo_plugin_manifest_path.exists():
        print(f"Warning: skipping local plugin sync because {repo_plugin_manifest_path} is missing.", file=sys.stderr)
        print("Install completed.")
        return 0

    print(f"Syncing local plugin package to {plugin_root}")
    plugin_skill_root.mkdir(parents=True, exist_ok=True)

    copy_fresh_item(source_root / ".codex-plugin", plugin_root / ".codex-plugin")
    copy_fresh_item(source_root / ".mcp.json", plugin_root / ".mcp.json")
    copy_fresh_item(source_root / "assets", plugin_root / "assets")
    copy_fresh_item(source_root / "mcp", plugin_root / "mcp")
    copy_fresh_item(source_root / "scripts", plugin_root / "scripts")
    normalize_mcp_manifest(plugin_root / ".mcp.json")

    for item in SKILL_ITEMS:
        copy_fresh_item(source_root / item, plugin_skill_root / item)
    normalize_mcp_manifest(plugin_skill_root / ".mcp.json")

    plugin_manifest = json.loads(installed_plugin_manifest_path.read_text(encoding="utf-8"))
    plugin_manifest["version"] = f"0.1.0+codex.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    installed_plugin_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    installed_plugin_manifest_path.write_text(
        json.dumps(plugin_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    marketplace_manifest = {
        "name": "antigravity-bridge-codex-local",
        "interface": {"displayName": "Local Antigravity Bridge Codex"},
        "plugins": [
            {
                "name": "antigravity-bridge-codex",
                "source": {
                    "source": "local",
                    "path": "./plugins/antigravity-bridge-codex",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }
    marketplace_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_manifest_path.write_text(
        json.dumps(marketplace_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if codex_executable is None:
        print("Warning: Codex executable not found; local plugin files were synced but not registered.", file=sys.stderr)
        print("Install completed.")
        return 0

    print(f"Registering marketplace with {codex_executable}")
    run_native_or_throw(codex_executable, "plugin", "marketplace", "add", str(marketplace_root))
    print("Installing or refreshing local plugin antigravity-bridge-codex@antigravity-bridge-codex-local")
    run_native_or_throw(codex_executable, "plugin", "add", "antigravity-bridge-codex@antigravity-bridge-codex-local")
    print("Install completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def main() -> int:
    source_root = Path(__file__).resolve().parent
    codex_home = get_codex_home()
    skill_root = codex_home / "skills" / "antigravity-gemini-bridge"
    marketplace_root = codex_home / "local-marketplaces" / "antigravity-gemini-bridge"
    marketplace_manifest_path = marketplace_root / ".agents" / "plugins" / "marketplace.json"
    plugin_root = marketplace_root / "plugins" / "antigravity-gemini-bridge"
    plugin_skill_root = plugin_root / "skills" / "antigravity-gemini-bridge"
    repo_plugin_manifest_path = source_root / ".codex-plugin" / "plugin.json"
    installed_plugin_manifest_path = plugin_root / ".codex-plugin" / "plugin.json"

    skill_root.mkdir(parents=True, exist_ok=True)
    print(f"Installing personal skill from {source_root} to {skill_root}")
    for item in SKILL_ITEMS:
        copy_fresh_item(source_root / item, skill_root / item)

    if not repo_plugin_manifest_path.exists():
        print(f"Warning: skipping local plugin sync because {repo_plugin_manifest_path} is missing.", file=sys.stderr)
        print("Install completed.")
        return 0

    print(f"Syncing local plugin package to {plugin_root}")
    plugin_skill_root.mkdir(parents=True, exist_ok=True)

    copy_fresh_item(source_root / ".codex-plugin", plugin_root / ".codex-plugin")
    copy_fresh_item(source_root / "assets", plugin_root / "assets")
    copy_fresh_item(source_root / "scripts", plugin_root / "scripts")

    for item in SKILL_ITEMS:
        copy_fresh_item(source_root / item, plugin_skill_root / item)

    plugin_manifest = json.loads(installed_plugin_manifest_path.read_text(encoding="utf-8"))
    plugin_manifest["version"] = f"0.1.0+codex.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    installed_plugin_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    installed_plugin_manifest_path.write_text(
        json.dumps(plugin_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    marketplace_manifest = {
        "name": "antigravity-gemini-bridge-local",
        "interface": {"displayName": "Local Antigravity Bridge Codex"},
        "plugins": [
            {
                "name": "antigravity-gemini-bridge",
                "source": {
                    "source": "local",
                    "path": "./plugins/antigravity-gemini-bridge",
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

    codex_executable = get_codex_executable(codex_home)
    if codex_executable is None:
        print("Warning: Codex executable not found; local plugin files were synced but not registered.", file=sys.stderr)
        print("Install completed.")
        return 0

    print(f"Registering marketplace with {codex_executable}")
    run_native_or_throw(codex_executable, "plugin", "marketplace", "add", str(marketplace_root))
    print("Installing or refreshing local plugin antigravity-gemini-bridge@antigravity-gemini-bridge-local")
    run_native_or_throw(codex_executable, "plugin", "add", "antigravity-gemini-bridge@antigravity-gemini-bridge-local")
    print("Install completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

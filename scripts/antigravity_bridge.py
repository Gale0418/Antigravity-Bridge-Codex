#!/usr/bin/env python3
"""Cross-platform Antigravity bridge CLI.

This mirrors the PowerShell bridge with standard-library Python so Codex can
recover when a thread has shell access but no loaded Antigravity skill/tool.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SERVICE_PREFIX = "http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/{method}"
DEFAULT_WAIT_PATTERN = r"(?s).+"


@dataclass
class AntigravitySession:
    csrf_token: str
    local_url: str
    https_port: int
    http_port: int
    process_id: int
    main_log_path: str
    language_server_log_path: str

    def public_dict(self, show_secret: bool = False) -> dict[str, Any]:
        data = asdict(self)
        data["csrf_token"] = self.csrf_token if show_secret else "<redacted>"
        return data


@dataclass
class ModelSelection:
    model_id: str = ""
    model_enum: str = ""


def get_platform(value: str = "") -> str:
    if value:
        return value
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    if system == "Linux":
        return "Linux"
    return "Windows"


def last_regex_value(text: str, pattern: str, group: int = 1) -> str | None:
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if not matches:
        return None
    return matches[-1].group(group)


def session_from_text(main_log_text: str, language_server_log_text: str) -> dict[str, Any]:
    csrf_token = last_regex_value(main_log_text, r"--csrf_token\s+([0-9a-fA-F-]{36})")
    local_url = last_regex_value(main_log_text, r"Local:\s+(https://127\.0\.0\.1:(\d+)/)", 1)
    if not local_url:
        local_url = last_regex_value(main_log_text, r"URL:\s+(https://127\.0\.0\.1:(\d+)/)", 1)

    local_https_port = last_regex_value(main_log_text, r"Local:\s+https://127\.0\.0\.1:(\d+)/", 1)
    if not local_https_port:
        local_https_port = last_regex_value(main_log_text, r"URL:\s+https://127\.0\.0\.1:(\d+)/", 1)

    process_id = last_regex_value(language_server_log_text, r"process with pid\s+(\d+)", 1)
    https_port = last_regex_value(language_server_log_text, r"port at\s+(\d+)\s+for HTTPS", 1)
    http_port = last_regex_value(language_server_log_text, r"port at\s+(\d+)\s+for HTTP", 1)

    if not csrf_token:
        raise RuntimeError("Unable to locate Antigravity CSRF token in main.log")
    if not local_url:
        raise RuntimeError("Unable to locate Antigravity local URL in main.log")

    https_port = https_port or local_https_port
    if not https_port or not http_port:
        raise RuntimeError("Unable to locate Antigravity HTTP/HTTPS ports in language_server.log")
    if not process_id:
        raise RuntimeError("Unable to locate Antigravity language server pid in language_server.log")

    return {
        "csrf_token": csrf_token,
        "local_url": local_url,
        "https_port": int(https_port),
        "http_port": int(http_port),
        "process_id": int(process_id),
    }


def default_log_path_candidates(
    platform_name: str = "",
    home_directory: str | Path | None = None,
    appdata_directory: str | Path | None = None,
) -> dict[str, Any]:
    resolved_platform = get_platform(platform_name)
    home = Path(home_directory).expanduser() if home_directory else Path.home()
    appdata = Path(appdata_directory).expanduser() if appdata_directory else None
    main_candidates: list[Path] = []
    language_candidates: list[Path] = []

    if resolved_platform == "Windows":
        if appdata:
            base = appdata / "Antigravity" / "logs"
        else:
            base = home / "AppData" / "Roaming" / "Antigravity" / "logs"
        main_candidates.append(base / "main.log")
        language_candidates.append(base / "language_server.log")
    elif resolved_platform == "macOS":
        main_candidates.append(home / "Library" / "Logs" / "Antigravity" / "main.log")
        language_candidates.append(home / "Library" / "Logs" / "Antigravity" / "language_server.log")

        snapshot_root = home / "Library" / "Application Support" / "Antigravity" / "logs"
        if snapshot_root.exists():
            for directory in sorted((p for p in snapshot_root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True):
                main_candidates.append(directory / "main.log")
                language_candidates.append(directory / "ls-main.log")
                language_candidates.extend(sorted(directory.glob("ls-main.*.log"), key=lambda p: p.name, reverse=True))
    elif resolved_platform == "Linux":
        config_base = home / ".config" / "Antigravity" / "logs"
        main_candidates.append(config_base / "main.log")
        language_candidates.append(config_base / "language_server.log")
        local_base = home / ".local" / "share" / "Antigravity" / "logs"
        main_candidates.append(local_base / "main.log")
        language_candidates.append(local_base / "language_server.log")

    return {
        "platform": resolved_platform,
        "main_log_candidates": unique_paths(main_candidates),
        "language_server_log_candidates": unique_paths(language_candidates),
    }


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def resolve_log_path(provided_path: str = "", candidates: list[Path] | None = None, label: str = "log") -> Path:
    if provided_path:
        path = Path(provided_path).expanduser()
        if not path.exists():
            raise RuntimeError(f"Antigravity {label} not found: {path}")
        return path

    for candidate in candidates or []:
        if candidate.exists():
            return candidate

    checked = ", ".join(str(path) for path in candidates or []) or "<none>"
    raise RuntimeError(f"Antigravity {label} not found. Checked: {checked}")


def get_session_info(
    main_log_path: str = "",
    language_server_log_path: str = "",
    platform_name: str = "",
    home_directory: str | Path | None = None,
    appdata_directory: str | Path | None = None,
) -> AntigravitySession:
    candidates = default_log_path_candidates(platform_name, home_directory, appdata_directory)
    main_path = resolve_log_path(main_log_path, candidates["main_log_candidates"], "main log")
    language_path = resolve_log_path(language_server_log_path, candidates["language_server_log_candidates"], "language server log")

    data = session_from_text(
        main_path.read_text(encoding="utf-8", errors="replace"),
        language_path.read_text(encoding="utf-8", errors="replace"),
    )
    return AntigravitySession(
        csrf_token=data["csrf_token"],
        local_url=data["local_url"],
        https_port=data["https_port"],
        http_port=data["http_port"],
        process_id=data["process_id"],
        main_log_path=str(main_path),
        language_server_log_path=str(language_path),
    )


def conversation_directory_candidates(
    platform_name: str = "",
    home_directory: str | Path | None = None,
    user_profile_directory: str | Path | None = None,
) -> list[Path]:
    resolved_platform = get_platform(platform_name)
    home = Path(home_directory or user_profile_directory or Path.home()).expanduser()
    candidates = [home / ".gemini" / "antigravity" / "conversations"]
    if resolved_platform == "Windows":
        candidates.append(home / ".gemini\\antigravity\\conversations")
    return unique_paths(candidates)


def binary_ascii(bytes_value: bytes) -> str:
    return "".join(chr(byte) if (32 <= byte <= 126 or byte in (9, 10, 13)) else " " for byte in bytes_value)


def find_recent_model_selection(
    conversation_directory: str = "",
    platform_name: str = "",
    home_directory: str | Path | None = None,
    user_profile_directory: str | Path | None = None,
    max_files: int = 8,
) -> ModelSelection:
    directories = [Path(conversation_directory).expanduser()] if conversation_directory else conversation_directory_candidates(
        platform_name, home_directory, user_profile_directory
    )
    model_pattern = re.compile(r"(?<![A-Za-z0-9])(?:gemini|claude|gpt|gemma|openrouter)(?:[a-z0-9./:-]*[a-z0-9])")
    enum_pattern = re.compile(r"MODEL_PLACEHOLDER_M\d+")
    composite_pattern = re.compile(
        r"(?s)(?P<model>(?<![A-Za-z0-9])(?:gemini|claude|gpt|gemma|openrouter)(?:[a-z0-9./:-]*[a-z0-9])).{0,220}?model_enum\s+(?P<enum>MODEL_PLACEHOLDER_M\d+)"
    )

    for directory in directories:
        if not directory.exists():
            continue
        files = sorted(
            [path for path in directory.iterdir() if path.is_file() and path.suffix in {".db", ".pb"}],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:max_files]

        for file_path in files:
            try:
                content = binary_ascii(file_path.read_bytes())
            except OSError:
                continue

            composite = composite_pattern.search(content)
            if composite:
                return ModelSelection(composite.group("model").strip(), composite.group("enum").strip())

            for match in model_pattern.finditer(content):
                candidate = match.group(0).strip()
                if not re.search(r"[-/:]", candidate):
                    continue
                start = max(0, match.start() - 220)
                window = content[start : start + 440]
                enum = enum_pattern.search(window)
                return ModelSelection(candidate, enum.group(0).strip() if enum else "")

    return ModelSelection()


def resolve_model_selection(model: str = "", conversation_directory: str = "") -> ModelSelection:
    env_model = os.environ.get("ANTIGRAVITY_MODEL", "")
    explicit_model = model.strip() or env_model.strip()
    recent = find_recent_model_selection(conversation_directory)

    if explicit_model:
        if re.match(r"^MODEL_PLACEHOLDER_M\d+$", explicit_model):
            return ModelSelection(recent.model_id if recent.model_enum == explicit_model else explicit_model, explicit_model)
        if recent.model_id == explicit_model and recent.model_enum:
            return recent
        return ModelSelection(explicit_model, "")

    if recent.model_id:
        return recent

    raise RuntimeError(
        "Antigravity model is required. Pass --model, set ANTIGRAVITY_MODEL, "
        "or ensure Antigravity has a recent successful local conversation with a real model id."
    )


def convert_to_file_uri(path_value: str) -> str:
    if re.match(r"^[\\/]{2}[^\\/]", path_value):
        raise RuntimeError(f"UNC paths are currently not supported: {path_value}")

    if re.match(r"^[A-Za-z]:[\\/]", path_value):
        normalized = path_value.replace("\\", "/")
        return "file:///" + urllib.parse.quote(normalized, safe="/:")

    if path_value.startswith("/"):
        return "file://" + urllib.parse.quote(path_value, safe="/:")

    resolved = os.path.abspath(os.path.expanduser(path_value))
    if re.match(r"^[\\/]{2}[^\\/]", resolved):
        raise RuntimeError(f"UNC paths are currently not supported: {resolved}")
    if re.match(r"^[A-Za-z]:[\\/]", resolved):
        normalized = resolved.replace("\\", "/")
        return "file:///" + urllib.parse.quote(normalized, safe="/:")
    if resolved.startswith("/"):
        return "file://" + urllib.parse.quote(resolved, safe="/:")

    raise RuntimeError(f"Only Windows drive-letter and POSIX absolute paths are currently supported: {resolved}")


def service_uri(session: AntigravitySession, method: str) -> str:
    return SERVICE_PREFIX.format(port=session.http_port, method=method)


def invoke_rpc(method: str, body: dict[str, Any], session: AntigravitySession | None = None) -> Any:
    resolved_session = session or get_session_info()
    request = urllib.request.Request(
        service_uri(resolved_session, method),
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-codeium-csrf-token": resolved_session.csrf_token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Antigravity RPC {method} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Antigravity RPC {method} failed: {exc.reason}") from exc

    if not data:
        return {}
    return json.loads(data.decode("utf-8"))


def new_cascade(
    workspace_paths: list[str] | None = None,
    model: str = "",
    cascade_id: str = "",
    session: AntigravitySession | None = None,
) -> dict[str, Any]:
    import uuid

    resolved_model = resolve_model_selection(model)
    body: dict[str, Any] = {
        "source": 1,
        "cascadeId": cascade_id or str(uuid.uuid4()),
        "requestedModel": resolved_model.model_enum or resolved_model.model_id,
    }
    if workspace_paths:
        body["workspaceUris"] = [convert_to_file_uri(path) for path in workspace_paths]

    response = invoke_rpc("StartCascade", body, session)
    return {
        "cascadeId": response.get("cascadeId") or body["cascadeId"],
        "workspaceUris": body.get("workspaceUris", []),
        "response": response,
    }


def send_message(
    cascade_id: str,
    text: str,
    model: str = "",
    omit_requested_model: bool = False,
    session: AntigravitySession | None = None,
) -> Any:
    body: dict[str, Any] = {"cascadeId": cascade_id, "items": [{"text": text}]}
    if not omit_requested_model:
        resolved_model = resolve_model_selection(model)
        body["cascadeConfig"] = {
            "plannerConfig": {
                "planModel" if resolved_model.model_enum else "requestedModel": (
                    resolved_model.model_enum if resolved_model.model_enum else {"model": resolved_model.model_id}
                )
            }
        }
    return invoke_rpc("SendUserCascadeMessage", body, session)


def get_trajectory(cascade_id: str, verbosity: int = 2, session: AntigravitySession | None = None) -> Any:
    envelope = invoke_rpc("GetCascadeTrajectory", {"cascadeId": cascade_id, "verbosity": verbosity}, session)
    return envelope.get("trajectory")


def trajectory_steps(trajectory: Any) -> list[Any]:
    if not isinstance(trajectory, dict):
        return []
    steps = trajectory.get("steps")
    return steps if isinstance(steps, list) else []


def latest_planner_response_text(trajectory: Any) -> str:
    for step in reversed(trajectory_steps(trajectory)):
        if step.get("type") == "CORTEX_STEP_TYPE_PLANNER_RESPONSE":
            return str(step.get("plannerResponse", {}).get("response", ""))
    return ""


def latest_error_text(trajectory: Any) -> str:
    for step in reversed(trajectory_steps(trajectory)):
        if step.get("type") == "CORTEX_STEP_TYPE_ERROR_MESSAGE":
            error_message = step.get("errorMessage", {})
            error = error_message.get("error", {})
            return str(error.get("shortError") or error.get("userErrorMessage") or json.dumps(error_message, separators=(",", ":")))
    return ""


def wait_trajectory_outcome(
    cascade_id: str,
    pattern: str,
    timeout_seconds: int = 90,
    poll_interval_seconds: int = 3,
    session: AntigravitySession | None = None,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_trajectory: Any = None
    last_response = ""
    last_error = ""
    last_combined = ""
    compiled = re.compile(pattern)

    while True:
        last_trajectory = get_trajectory(cascade_id, session=session)
        last_response = latest_planner_response_text(last_trajectory)
        last_error = latest_error_text(last_trajectory)
        last_combined = "\n".join([last_response, last_error])

        if compiled.search(last_combined):
            return {
                "cascadeId": cascade_id,
                "pattern": pattern,
                "matched": True,
                "timedOut": False,
                "trajectory": last_trajectory,
                "response": last_response,
                "failure": last_error,
                "observedText": last_combined,
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(poll_interval_seconds)

    return {
        "cascadeId": cascade_id,
        "pattern": pattern,
        "matched": False,
        "timedOut": True,
        "trajectory": last_trajectory,
        "response": last_response,
        "failure": last_error,
        "observedText": last_combined,
    }


def compact_outcome(outcome: dict[str, Any], include_trajectory: bool = False) -> dict[str, Any]:
    compact = dict(outcome)
    if not include_trajectory:
        compact.pop("trajectory", None)
    return compact


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Talk to a locally logged-in Antigravity session.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("--show-secret", action="store_true")

    start = subparsers.add_parser("start")
    start.add_argument("--workspace-path", default=os.getcwd())
    start.add_argument("--opening-prompt", required=True)
    start.add_argument("--model", default="")
    start.add_argument("--wait-pattern", default=DEFAULT_WAIT_PATTERN)
    start.add_argument("--timeout-seconds", type=int, default=90)
    start.add_argument("--allow-timeout", action="store_true")
    start.add_argument("--include-trajectory", action="store_true")

    send = subparsers.add_parser("send")
    send.add_argument("--cascade-id", required=True)
    send.add_argument("--text", required=True)
    send.add_argument("--model", default="")
    send.add_argument("--wait-pattern", default=DEFAULT_WAIT_PATTERN)
    send.add_argument("--timeout-seconds", type=int, default=90)
    send.add_argument("--allow-timeout", action="store_true")
    send.add_argument("--include-trajectory", action="store_true")
    send.add_argument("--omit-requested-model", action="store_true")

    trajectory = subparsers.add_parser("trajectory")
    trajectory.add_argument("--cascade-id", required=True)
    trajectory.add_argument("--verbosity", type=int, default=2)

    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--workspace-path", default=os.getcwd())
    smoke.add_argument("--prompt", default="Please reply only BRIDGE_OK")
    smoke.add_argument("--pattern", default="BRIDGE_OK")
    smoke.add_argument("--model", default="")
    smoke.add_argument("--timeout-seconds", type=int, default=90)
    smoke.add_argument("--allow-timeout", action="store_true")
    smoke.add_argument("--include-trajectory", action="store_true")

    return parser


def run(args: argparse.Namespace) -> Any:
    session = get_session_info()
    if args.action == "discover":
        return session.public_dict(show_secret=args.show_secret)
    if args.action == "start":
        cascade = new_cascade([args.workspace_path], model=args.model, session=session)
        send_message(cascade["cascadeId"], args.opening_prompt, model=args.model, session=session)
        outcome = wait_trajectory_outcome(cascade["cascadeId"], args.wait_pattern, args.timeout_seconds, session=session)
        if outcome["timedOut"] and not args.allow_timeout:
            raise RuntimeError(
                f"Action 'start' timed out waiting for pattern {outcome['pattern']} in cascade {outcome['cascadeId']}. "
                "Re-run with --allow-timeout to inspect partial output."
            )
        return {
            "action": "start",
            "cascadeId": cascade["cascadeId"],
            "workspacePath": args.workspace_path,
            **compact_outcome(outcome, args.include_trajectory),
        }
    if args.action == "send":
        send_message(args.cascade_id, args.text, model=args.model, omit_requested_model=args.omit_requested_model, session=session)
        outcome = wait_trajectory_outcome(args.cascade_id, args.wait_pattern, args.timeout_seconds, session=session)
        if outcome["timedOut"] and not args.allow_timeout:
            raise RuntimeError(
                f"Action 'send' timed out waiting for pattern {outcome['pattern']} in cascade {outcome['cascadeId']}. "
                "Re-run with --allow-timeout to inspect partial output."
            )
        return {"action": "send", **compact_outcome(outcome, args.include_trajectory)}
    if args.action == "trajectory":
        return get_trajectory(args.cascade_id, args.verbosity, session=session)
    if args.action == "smoke":
        cascade = new_cascade([args.workspace_path], model=args.model, session=session)
        send_message(cascade["cascadeId"], args.prompt, model=args.model, session=session)
        outcome = wait_trajectory_outcome(cascade["cascadeId"], args.pattern, args.timeout_seconds, session=session)
        if outcome["timedOut"] and not args.allow_timeout:
            raise RuntimeError(
                f"Action 'smoke' timed out waiting for pattern {outcome['pattern']} in cascade {outcome['cascadeId']}. "
                "Re-run with --allow-timeout to inspect partial output."
            )
        return {
            "action": "smoke",
            "cascadeId": cascade["cascadeId"],
            "workspacePath": args.workspace_path,
            **compact_outcome(outcome, args.include_trajectory),
        }
    raise RuntimeError(f"Unsupported action: {args.action}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        print_json(run(args))
        return 0
    except Exception as exc:
        print_json({"error": str(exc), "action": args.action})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

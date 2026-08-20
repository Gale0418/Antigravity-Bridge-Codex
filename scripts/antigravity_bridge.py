#!/usr/bin/env python3
"""Cross-platform Antigravity bridge CLI.

This mirrors the PowerShell bridge with standard-library Python so Codex can
recover when a thread has shell access but no loaded Antigravity skill/tool.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERVICE_PREFIX = "http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/{method}"
DEFAULT_WAIT_PATTERN = r"(?s).+"
DEFAULT_AGY_MODEL = "gemini-3.6-flash-high"
KNOWN_MODEL_ENUMS = {DEFAULT_AGY_MODEL: "MODEL_PLACEHOLDER_M71"}

DELIVERY_PENDING = {"PREPARING", "IN_PROGRESS", "DELIVERING", "DELIVERY_UNKNOWN", "ACCEPTED_PENDING", "INPUT_REQUIRED"}


class HealthState:
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    INPUT_REQUIRED = "INPUT_REQUIRED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"


class CircuitState:
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class ProcessOwnershipRecord:
    executable: str
    process_id: int
    start_token: str
    launched_at: float = 0.0


_GLOBAL_PROCESS_OWNERSHIP: dict[int, ProcessOwnershipRecord] = {}


def record_process_ownership(executable: str, process_id: int, start_token: str = "") -> ProcessOwnershipRecord:
    token = start_token or uuid.uuid4().hex
    rec = ProcessOwnershipRecord(
        executable=str(Path(executable).resolve()) if executable else "",
        process_id=process_id,
        start_token=token,
        launched_at=time.monotonic(),
    )
    if process_id:
        _GLOBAL_PROCESS_OWNERSHIP[process_id] = rec
    return rec


def get_process_ownership(process_id: int) -> ProcessOwnershipRecord | None:
    return _GLOBAL_PROCESS_OWNERSHIP.get(process_id)


def clear_process_ownership() -> None:
    _GLOBAL_PROCESS_OWNERSHIP.clear()


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_success_time = 0.0

    def current_state(self, now: float | None = None) -> str:
        current_now = now if now is not None else time.monotonic()
        if self.state == CircuitState.OPEN:
            if current_now - self.last_failure_time >= self.cooldown_seconds:
                return CircuitState.HALF_OPEN
        return self.state

    def allow_request(self, now: float | None = None) -> bool:
        st = self.current_state(now)
        return st in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self, now: float | None = None) -> None:
        current_now = now if now is not None else time.monotonic()
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        self.last_success_time = current_now

    def record_failure(self, health_status_or_error: str, now: float | None = None) -> None:
        if health_status_or_error in (HealthState.INPUT_REQUIRED, HealthState.DELIVERY_UNKNOWN, "INPUT_REQUIRED", "DELIVERY_UNKNOWN"):
            return
        current_now = now if now is not None else time.monotonic()
        self.failure_count += 1
        self.last_failure_time = current_now
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_success_time = 0.0


_GLOBAL_CIRCUIT_BREAKER = CircuitBreaker()


def classify_predispatch_failure(error: BaseException | str) -> str:
    """Classify failures that occurred before Send; ambiguous classes never trip recovery."""
    message = str(error).lower()
    if any(token in message for token in ("http 401", "http 403", "not authorized", "permission", "authentication", "login required")):
        return HealthState.INPUT_REQUIRED
    if any(token in message for token in ("connection refused", "unavailable", "no log", "not found", "deadline exceeded", "timed out", "timeout")):
        return HealthState.UNAVAILABLE
    return HealthState.DEGRADED


def validate_workspace_boundary(workspace_path: str) -> str:
    """Resolve one caller-selected workspace and enforce optional configured roots."""
    resolved = Path(workspace_path or os.getcwd()).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"workspace_path must be an existing directory: {resolved}")
    configured = os.environ.get("ANTIGRAVITY_ALLOWED_WORKSPACES", "").strip()
    if not configured:
        return str(resolved)
    roots = [Path(value).expanduser().resolve() for value in configured.split(os.pathsep) if value.strip()]
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise PermissionError(
            f"workspace_path is outside ANTIGRAVITY_ALLOWED_WORKSPACES: {resolved}"
        )
    return str(resolved)


def is_process_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def assess_health(
    journal_path: str = "",
    probe: bool = True,
    session: AntigravitySession | None = None,
    timeout_seconds: float = 3.0,
    main_log_path: str = "",
    language_server_log_path: str = "",
    platform_name: str = "",
    home_directory: str | Path | None = None,
    appdata_directory: str | Path | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "discovery": False,
        "probe": False,
        "has_pending_delivery": False,
    }

    try:
        j_path = request_journal_path(journal_path)
        if j_path.exists():
            with closing(sqlite3.connect(j_path, timeout=2.0)) as db:
                rows = db.execute(
                    "SELECT request_id, state FROM requests WHERE state IN ('PREPARING', 'IN_PROGRESS', 'DELIVERING', 'DELIVERY_UNKNOWN', 'ACCEPTED_PENDING', 'INPUT_REQUIRED')"
                ).fetchall()
                if rows:
                    details["has_pending_delivery"] = True
                    details["pending_requests"] = [r[0] for r in rows]
                    details["input_required"] = any(r[1] == "INPUT_REQUIRED" for r in rows)
    except Exception as exc:
        details["journal_error"] = str(exc)

    discovered_session = session
    if not discovered_session:
        try:
            discovered_session = get_session_info(
                main_log_path=main_log_path,
                language_server_log_path=language_server_log_path,
                platform_name=platform_name,
                home_directory=home_directory,
                appdata_directory=appdata_directory,
            )
            details["discovery"] = True
            details["process_id"] = discovered_session.process_id
        except Exception as exc:
            details["discovery_error"] = str(exc)
            status = (
                HealthState.INPUT_REQUIRED
                if details.get("input_required")
                else HealthState.DELIVERY_UNKNOWN
                if details["has_pending_delivery"]
                else HealthState.UNAVAILABLE
            )
            return {"status": status, "details": details}

    if discovered_session and discovered_session.process_id:
        details["process_id"] = discovered_session.process_id
        if not is_process_alive(discovered_session.process_id):
            details["process_alive"] = False
            status = (
                HealthState.INPUT_REQUIRED
                if details.get("input_required")
                else HealthState.DELIVERY_UNKNOWN
                if details["has_pending_delivery"]
                else HealthState.UNAVAILABLE
            )
            return {"status": status, "details": details}
        details["process_alive"] = True

    if probe and discovered_session:
        try:
            probe_deadline = time.monotonic() + timeout_seconds
            invoke_rpc("GetUserStatus", {}, session=discovered_session, deadline=probe_deadline)
            details["probe"] = True
        except Exception as exc:
            err_str = str(exc)
            details["probe_error"] = err_str
            if "expired or is not authorized" in err_str or "HTTP 401" in err_str or "HTTP 403" in err_str:
                status = HealthState.INPUT_REQUIRED
                return {"status": status, "details": details}
            if "unavailable" in err_str or "refused" in err_str or "not found" in err_str:
                status = (
                    HealthState.INPUT_REQUIRED
                    if details.get("input_required")
                    else HealthState.DELIVERY_UNKNOWN
                    if details["has_pending_delivery"]
                    else HealthState.UNAVAILABLE
                )
                return {"status": status, "details": details}
            details["probe_degraded"] = True

    if details.get("input_required"):
        status = HealthState.INPUT_REQUIRED
    elif details["has_pending_delivery"]:
        status = HealthState.DELIVERY_UNKNOWN
    elif details.get("probe_degraded"):
        status = HealthState.DEGRADED
    elif details.get("discovery") or discovered_session:
        status = HealthState.HEALTHY
    else:
        status = HealthState.UNAVAILABLE

    return {"status": status, "details": details}


@dataclass
class RecoveryDecision:
    action: str
    reason: str
    allowed: bool


def assess_recovery_decision(
    health_status: str,
    has_pending_delivery: bool,
    process_record: ProcessOwnershipRecord | None = None,
    current_process_info: dict[str, Any] | None = None,
) -> RecoveryDecision:
    if has_pending_delivery or health_status == HealthState.DELIVERY_UNKNOWN:
        return RecoveryDecision(
            action="NONE",
            reason="pending or ambiguous delivery in journal; restart prohibited to preserve delivery guarantees",
            allowed=False,
        )

    if health_status == HealthState.INPUT_REQUIRED:
        return RecoveryDecision(
            action="REQUIRE_USER",
            reason="user authorization or permission required",
            allowed=False,
        )

    if health_status in (HealthState.HEALTHY, HealthState.DEGRADED):
        return RecoveryDecision(
            action="NONE",
            reason=f"system state is {health_status}; restart not needed",
            allowed=False,
        )

    if health_status != HealthState.UNAVAILABLE:
        return RecoveryDecision(
            action="NONE",
            reason=f"system state is {health_status}; restart not allowed",
            allowed=False,
        )

    if not process_record:
        return RecoveryDecision(
            action="REQUIRE_USER",
            reason="unowned process; bridge did not launch process",
            allowed=False,
        )

    if current_process_info is None:
        return RecoveryDecision(
            action="REQUIRE_USER",
            reason="live process identity was not supplied; ownership cannot be revalidated",
            allowed=False,
        )

    rec_exe = str(Path(process_record.executable).resolve()) if process_record.executable else ""
    cur_exe = str(Path(current_process_info.get("executable", "")).resolve()) if current_process_info.get("executable") else ""

    if (
        rec_exe != cur_exe
        or process_record.process_id != current_process_info.get("process_id")
        or process_record.start_token != current_process_info.get("start_token")
    ):
        return RecoveryDecision(
            action="REQUIRE_USER",
            reason="process ownership verification failed (PID, executable, or start token mismatch)",
            allowed=False,
        )

    return RecoveryDecision(
        action="RESTART",
        reason="bridge-owned process is confirmed unavailable with no pending delivery",
        allowed=True,
    )


def execute_recovery_restart(
    decision: RecoveryDecision,
    process_record: ProcessOwnershipRecord | None = None,
    dry_run: bool = True,
    current_process_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not decision.allowed or decision.action != "RESTART":
        return {
            "executed": False,
            "dry_run": dry_run,
            "action": decision.action,
            "allowed": False,
            "reason": f"restart blocked: {decision.reason}",
        }

    if not process_record:
        return {
            "executed": False,
            "dry_run": dry_run,
            "action": "REQUIRE_USER",
            "allowed": False,
            "reason": "revalidation failed: process ownership record missing",
        }

    if current_process_info is None:
        return {
            "executed": False,
            "dry_run": dry_run,
            "action": "REQUIRE_USER",
            "allowed": False,
            "reason": "revalidation failed: live process identity missing immediately prior to action",
        }

    rec_exe = str(Path(process_record.executable).resolve()) if process_record.executable else ""
    cur_exe = str(Path(current_process_info.get("executable", "")).resolve()) if current_process_info.get("executable") else ""

    if (
        rec_exe != cur_exe
        or process_record.process_id != current_process_info.get("process_id")
        or process_record.start_token != current_process_info.get("start_token")
    ):
        return {
            "executed": False,
            "dry_run": dry_run,
            "action": "REQUIRE_USER",
            "allowed": False,
            "reason": "revalidation failed: PID, executable, or start token mismatch immediately prior to action",
        }

    if dry_run:
        return {
            "executed": False,
            "dry_run": True,
            "action": "RESTART",
            "allowed": True,
            "target_pid": process_record.process_id,
            "target_executable": process_record.executable,
            "start_token": process_record.start_token,
            "reason": decision.reason,
        }

    # Real restart execution is intentionally unavailable until a platform-specific,
    # process-owned launcher can revalidate identity and restart the exact executable.
    return {
        "executed": False,
        "dry_run": False,
        "action": "REQUIRE_USER",
        "allowed": False,
        "target_pid": process_record.process_id,
        "target_executable": process_record.executable,
        "start_token": process_record.start_token,
        "reason": "real restart execution is not implemented; no process was changed",
    }



def request_journal_path(path: str = "") -> Path:
    if path:
        return Path(path).expanduser()
    explicit = os.environ.get("ANTIGRAVITY_BRIDGE_JOURNAL_PATH", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) if os.name == "nt" else Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "AntigravityBridge" / "requests.sqlite3"


def request_fingerprint(prompt: str, conversation_id: str, model: str, workspace_path: str, mission_id: str, lane_id: str) -> str:
    # Never persist prompt text or session credentials.
    payload = json.dumps({"prompt": prompt, "conversation_id": conversation_id, "model": model, "workspace_path": workspace_path, "mission_id": mission_id, "lane_id": lane_id}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _protect_sensitive_text(value: Any) -> str:
    safe = str(value or "")
    safe = re.sub(
        r"(?im)\b(csrf(?:[_-]?token)?|api[_-]?key|access[_-]?token|authorization)\b\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+",
        r"\1: <redacted>",
        safe,
    )
    return re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer <redacted>", safe)


def _sanitize_journal_value(value: Any, redact_all_text: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_journal_value(
                nested,
                redact_all_text or key.lower() in {"response", "error"},
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_journal_value(item, redact_all_text) for item in value]
    return _protect_sensitive_text(value) if redact_all_text else value


def sanitize_journal_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Redact response/error text while retaining replay and delivery metadata."""
    return _sanitize_journal_value(receipt)


class RequestJournal:
    def __init__(self, path: str = "") -> None:
        self.path = request_journal_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect_db()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL, cascade_id TEXT NOT NULL DEFAULT '', marker TEXT NOT NULL DEFAULT '', receipt TEXT NOT NULL DEFAULT '', updated REAL NOT NULL)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS lane_leases ("
                "mission_id TEXT NOT NULL DEFAULT '', "
                "lane_id TEXT NOT NULL DEFAULT '', "
                "owner_id TEXT NOT NULL DEFAULT '', "
                "epoch INTEGER NOT NULL DEFAULT 1, "
                "lease_until REAL NOT NULL DEFAULT 0.0, "
                "quota_remaining INTEGER NOT NULL DEFAULT -1, "
                "cancelled INTEGER NOT NULL DEFAULT 0, "
                "updated REAL NOT NULL DEFAULT 0.0, "
                "PRIMARY KEY (mission_id, lane_id))"
            )
            db.commit()

    def _connect_db(self, isolation_level: str | None = None) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5.0, isolation_level=isolation_level)
        try:
            db.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        db.execute("PRAGMA busy_timeout=5000;")
        return db

    def claim(self, request_id: str, fingerprint: str) -> dict[str, Any]:
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint,state,cascade_id,marker,receipt FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    db.execute("COMMIT")
                    return {"kind": "conflict"}
                db.execute("COMMIT")
                return {"kind": "replay", "state": row[1], "cascade_id": row[2], "marker": row[3], "receipt": json.loads(row[4]) if row[4] else {}}
            db.execute("INSERT INTO requests(request_id,fingerprint,state,updated) VALUES(?,?,?,?)", (request_id, fingerprint, "IN_PROGRESS", time.time()))
            db.execute("COMMIT")
        return {"kind": "new"}

    def prepare_delivery(self, request_id: str, cascade_id: str, marker: str, state: str = "DELIVERING") -> None:
        with closing(self._connect_db()) as db:
            db.execute(
                "UPDATE requests SET state=?,cascade_id=?,marker=?,updated=? WHERE request_id=?",
                (state, cascade_id, marker, time.time(), request_id),
            )
            db.commit()

    def finish(self, request_id: str, receipt: dict[str, Any]) -> None:
        with closing(self._connect_db()) as db:
            sanitized_receipt = sanitize_journal_receipt(receipt)
            db.execute("UPDATE requests SET state=?,receipt=?,updated=? WHERE request_id=?", (str(sanitized_receipt.get("delivery_state") or sanitized_receipt.get("status") or "DELIVERY_UNKNOWN"), json.dumps(sanitized_receipt, ensure_ascii=False, separators=(",", ":")), time.time(), request_id))
            db.commit()

    def claim_lane_lease(
        self,
        mission_id: str,
        lane_id: str,
        owner_id: str,
        lease_seconds: float = 60.0,
        initial_quota: int = -1,
        epoch: int = 0,
    ) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id, epoch, lease_until, quota_remaining, cancelled FROM lane_leases WHERE mission_id=? AND lane_id=?",
                (mission_id, lane_id),
            ).fetchone()
            if not row:
                granted_epoch = epoch if epoch > 0 else 1
                lease_until = now + lease_seconds
                db.execute(
                    "INSERT INTO lane_leases (mission_id, lane_id, owner_id, epoch, lease_until, quota_remaining, cancelled, updated) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                    (mission_id, lane_id, owner_id, granted_epoch, lease_until, initial_quota, now),
                )
                db.execute("COMMIT")
                return {
                    "kind": "granted",
                    "owner_id": owner_id,
                    "epoch": granted_epoch,
                    "lease_until": lease_until,
                    "quota_remaining": initial_quota,
                    "cancelled": False,
                    "lane_state": "ACTIVE",
                }

            curr_owner, curr_epoch, curr_lease_until, curr_quota, cancelled = row
            if cancelled:
                db.execute("COMMIT")
                return {
                    "kind": "cancelled",
                    "owner_id": curr_owner,
                    "epoch": curr_epoch,
                    "quota_remaining": curr_quota,
                    "cancelled": True,
                    "lane_state": "CANCELLED",
                }

            if now < curr_lease_until:
                if curr_owner == owner_id:
                    if epoch != curr_epoch:
                        db.execute("COMMIT")
                        return {
                            "kind": "fenced",
                            "reason": "epoch_mismatch",
                            "owner_id": curr_owner,
                            "epoch": curr_epoch,
                            "lane_state": "BUSY",
                        }
                    new_lease_until = now + lease_seconds
                    db.execute(
                        "UPDATE lane_leases SET lease_until=?, updated=? WHERE mission_id=? AND lane_id=?",
                        (new_lease_until, now, mission_id, lane_id),
                    )
                    db.execute("COMMIT")
                    return {
                        "kind": "active",
                        "owner_id": curr_owner,
                        "epoch": curr_epoch,
                        "lease_until": new_lease_until,
                        "quota_remaining": curr_quota,
                        "cancelled": False,
                        "lane_state": "ACTIVE",
                    }
                else:
                    db.execute("COMMIT")
                    return {
                        "kind": "busy",
                        "reason": "lease_held_by_other_owner",
                        "owner_id": curr_owner,
                        "epoch": curr_epoch,
                        "lease_until": curr_lease_until,
                        "lane_state": "BUSY",
                    }
            else:
                new_epoch = max(curr_epoch + 1, epoch if epoch > 0 else curr_epoch + 1)
                new_lease_until = now + lease_seconds
                new_quota = initial_quota if initial_quota >= 0 else curr_quota
                db.execute(
                    "UPDATE lane_leases SET owner_id=?, epoch=?, lease_until=?, quota_remaining=?, cancelled=0, updated=? WHERE mission_id=? AND lane_id=?",
                    (owner_id, new_epoch, new_lease_until, new_quota, now, mission_id, lane_id),
                )
                db.execute("COMMIT")
                return {
                    "kind": "taken_over",
                    "owner_id": owner_id,
                    "epoch": new_epoch,
                    "lease_until": new_lease_until,
                    "quota_remaining": new_quota,
                    "cancelled": False,
                    "lane_state": "ACTIVE",
                }

    def renew_lane_lease(
        self,
        mission_id: str,
        lane_id: str,
        owner_id: str,
        epoch: int = 0,
        lease_seconds: float = 60.0,
    ) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id, epoch, lease_until, quota_remaining, cancelled FROM lane_leases WHERE mission_id=? AND lane_id=?",
                (mission_id, lane_id),
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return {"kind": "not_found", "lane_state": "UNBOUND"}
            curr_owner, curr_epoch, curr_lease_until, curr_quota, cancelled = row
            if cancelled:
                db.execute("COMMIT")
                return {"kind": "cancelled", "lane_state": "CANCELLED"}
            if curr_owner != owner_id or curr_epoch != epoch:
                db.execute("COMMIT")
                return {"kind": "fenced", "owner_id": curr_owner, "epoch": curr_epoch, "lane_state": "BUSY"}
            new_lease_until = now + lease_seconds
            db.execute(
                "UPDATE lane_leases SET lease_until=?, updated=? WHERE mission_id=? AND lane_id=?",
                (new_lease_until, now, mission_id, lane_id),
            )
            db.execute("COMMIT")
            return {"kind": "renewed", "owner_id": owner_id, "epoch": curr_epoch, "lease_until": new_lease_until, "lane_state": "ACTIVE"}

    def cancel_lane(self, mission_id: str, lane_id: str) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id, epoch FROM lane_leases WHERE mission_id=? AND lane_id=?",
                (mission_id, lane_id),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE lane_leases SET cancelled=1, updated=? WHERE mission_id=? AND lane_id=?",
                    (now, mission_id, lane_id),
                )
            else:
                db.execute(
                    "INSERT INTO lane_leases (mission_id, lane_id, owner_id, epoch, lease_until, quota_remaining, cancelled, updated) VALUES (?, ?, '', 1, 0.0, -1, 1, ?)",
                    (mission_id, lane_id, now),
                )
            db.execute("COMMIT")
            return {"kind": "cancelled", "mission_id": mission_id, "lane_id": lane_id, "lane_state": "CANCELLED"}

    def consume_lane_quota(
        self,
        mission_id: str,
        lane_id: str,
        owner_id: str,
        epoch: int = 0,
        amount: int = 1,
    ) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id, epoch, quota_remaining, cancelled FROM lane_leases WHERE mission_id=? AND lane_id=?",
                (mission_id, lane_id),
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return {"kind": "not_found", "lane_state": "UNBOUND"}
            curr_owner, curr_epoch, curr_quota, cancelled = row
            if cancelled:
                db.execute("COMMIT")
                return {"kind": "cancelled", "lane_state": "CANCELLED"}
            if curr_owner != owner_id or curr_epoch != epoch:
                db.execute("COMMIT")
                return {"kind": "fenced", "owner_id": curr_owner, "epoch": curr_epoch, "lane_state": "BUSY"}
            if curr_quota < 0:
                db.execute("COMMIT")
                return {"kind": "ok", "quota_remaining": -1, "lane_state": "ACTIVE"}
            if curr_quota < amount:
                db.execute("COMMIT")
                return {"kind": "exhausted", "quota_remaining": curr_quota, "lane_state": "EXHAUSTED"}
            new_quota = curr_quota - amount
            db.execute(
                "UPDATE lane_leases SET quota_remaining=?, updated=? WHERE mission_id=? AND lane_id=?",
                (new_quota, now, mission_id, lane_id),
            )
            db.execute("COMMIT")
            return {"kind": "ok", "quota_remaining": new_quota, "lane_state": "ACTIVE"}

    def release_lane_lease(
        self,
        mission_id: str,
        lane_id: str,
        owner_id: str,
        epoch: int = 0,
    ) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id, epoch FROM lane_leases WHERE mission_id=? AND lane_id=?",
                (mission_id, lane_id),
            ).fetchone()
            if not row:
                db.execute("COMMIT")
                return {"kind": "not_found", "lane_state": "UNBOUND"}
            curr_owner, curr_epoch = row
            if curr_owner != owner_id or curr_epoch != epoch:
                db.execute("COMMIT")
                return {"kind": "fenced", "owner_id": curr_owner, "epoch": curr_epoch, "lane_state": "BUSY"}
            db.execute(
                "UPDATE lane_leases SET lease_until=0.0, updated=? WHERE mission_id=? AND lane_id=?",
                (now, mission_id, lane_id),
            )
            db.execute("COMMIT")
            return {"kind": "released", "lane_state": "EXPIRED"}

    def authorize_lane_prompt(
        self,
        mission_id: str,
        lane_id: str,
        owner_id: str,
        epoch: int = 0,
        lease_seconds: float = 60.0,
        quota: int = -1,
    ) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect_db(isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT owner_id, epoch, lease_until, quota_remaining, cancelled FROM lane_leases WHERE mission_id=? AND lane_id=?",
                (mission_id, lane_id),
            ).fetchone()

            if not row:
                effective_epoch = epoch if epoch > 0 else 1
                lease_until = now + lease_seconds
                remaining_quota = quota
                if remaining_quota > 0:
                    remaining_quota -= 1
                elif remaining_quota == 0:
                    db.execute(
                        "INSERT INTO lane_leases (mission_id, lane_id, owner_id, epoch, lease_until, quota_remaining, cancelled, updated) VALUES (?, ?, ?, ?, ?, 0, 0, ?)",
                        (mission_id, lane_id, owner_id, effective_epoch, lease_until, now),
                    )
                    db.execute("COMMIT")
                    return {
                        "authorized": False,
                        "status": "QUOTA_EXCEEDED",
                        "error": f"Lane quota exhausted for '{lane_id}'",
                        "owner_id": owner_id,
                        "epoch": effective_epoch,
                        "lane_state": "EXHAUSTED",
                    }
                db.execute(
                    "INSERT INTO lane_leases (mission_id, lane_id, owner_id, epoch, lease_until, quota_remaining, cancelled, updated) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                    (mission_id, lane_id, owner_id, effective_epoch, lease_until, remaining_quota, now),
                )
                db.execute("COMMIT")
                return {
                    "authorized": True,
                    "status": "AUTHORIZED",
                    "owner_id": owner_id,
                    "epoch": effective_epoch,
                    "lease_until": lease_until,
                    "quota_remaining": remaining_quota,
                    "lane_state": "ACTIVE",
                }

            curr_owner, curr_epoch, curr_lease_until, curr_quota, cancelled = row

            if cancelled:
                db.execute("COMMIT")
                return {
                    "authorized": False,
                    "status": "CANCELLED",
                    "error": f"Lane '{lane_id}' is cancelled",
                    "owner_id": curr_owner,
                    "epoch": curr_epoch,
                    "lane_state": "CANCELLED",
                }

            if now < curr_lease_until:
                if curr_owner != owner_id:
                    db.execute("COMMIT")
                    return {
                        "authorized": False,
                        "status": "LANE_BUSY",
                        "error": f"Lane busy: held by owner '{curr_owner}' (epoch {curr_epoch})",
                        "owner_id": curr_owner,
                        "epoch": curr_epoch,
                        "lane_state": "BUSY",
                    }
                if epoch != curr_epoch:
                    db.execute("COMMIT")
                    return {
                        "authorized": False,
                        "status": "LANE_BUSY",
                        "error": f"Epoch mismatch: expected {curr_epoch}, got {epoch}",
                        "owner_id": curr_owner,
                        "epoch": curr_epoch,
                        "lane_state": "BUSY",
                    }
                effective_epoch = curr_epoch
                remaining_quota = curr_quota
            else:
                effective_epoch = max(curr_epoch + 1, epoch if epoch > 0 else curr_epoch + 1)
                remaining_quota = quota if quota >= 0 else curr_quota

            if remaining_quota >= 0:
                if remaining_quota <= 0:
                    db.execute("COMMIT")
                    return {
                        "authorized": False,
                        "status": "QUOTA_EXCEEDED",
                        "error": f"Lane quota exhausted for '{lane_id}'",
                        "owner_id": owner_id,
                        "epoch": effective_epoch,
                        "lane_state": "EXHAUSTED",
                    }
                remaining_quota -= 1

            new_lease_until = now + lease_seconds
            db.execute(
                "UPDATE lane_leases SET owner_id=?, epoch=?, lease_until=?, quota_remaining=?, cancelled=0, updated=? WHERE mission_id=? AND lane_id=?",
                (owner_id, effective_epoch, new_lease_until, remaining_quota, now, mission_id, lane_id),
            )
            db.execute("COMMIT")
            return {
                "authorized": True,
                "status": "AUTHORIZED",
                "owner_id": owner_id,
                "epoch": effective_epoch,
                "lease_until": new_lease_until,
                "quota_remaining": remaining_quota,
                "lane_state": "ACTIVE",
            }

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


@dataclass
class ModelPolicyResult:
    model_id: str
    source: str
    reason: str
    model_enum: str = ""


_CATALOG_CACHE: dict[str, Any] = {
    "executable": "",
    "version": "",
    "key": "",
    "timestamp": 0.0,
    "models": [],
}
_CATALOG_CACHE_TTL = 300.0  # 5 minutes


def get_cli_version(executable: str = "") -> str:
    try:
        res = subprocess.run(
            [executable, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    try:
        if executable and os.path.exists(executable):
            return str(os.path.getmtime(executable))
    except Exception:
        pass
    return "unknown"


def parse_model_catalog_output(stdout: str) -> list[dict[str, str]]:
    if not stdout or not stdout.strip():
        return []
    start = stdout.find("{")
    end = stdout.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            json_str = stdout[start : end + 1]
            data = json.loads(json_str)
            models_raw = []
            if isinstance(data, dict):
                models_raw = (
                    data.get("data", {}).get("models")
                    or data.get("models")
                    or data.get("command", {}).get("data", {}).get("models")
                    or []
                )
            elif isinstance(data, list):
                models_raw = data

            results = []
            for item in models_raw:
                if isinstance(item, dict):
                    m_id = str(item.get("id") or item.get("name") or "").strip()
                    m_label = str(item.get("label") or item.get("title") or m_id).strip()
                    if m_id:
                        results.append({"id": m_id, "label": m_label})
                elif isinstance(item, str) and item.strip():
                    results.append({"id": item.strip(), "label": item.strip()})
            if results:
                return results
        except Exception:
            pass

    # TSV Fallback for older CLI output
    results = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        m_id = parts[0].strip()
        if m_id and m_id.lower() != "id":
            m_label = parts[1].strip() if len(parts) > 1 else m_id
            results.append({"id": m_id, "label": m_label})

    return results


def fetch_model_catalog(executable: str = "", force_refresh: bool = False) -> list[dict[str, str]]:
    global _CATALOG_CACHE
    now = time.monotonic()
    try:
        resolved_exe = resolve_agy_executable(executable)
    except Exception:
        return []

    if not force_refresh and _CATALOG_CACHE.get("executable") == resolved_exe:
        if now - _CATALOG_CACHE.get("timestamp", 0.0) < _CATALOG_CACHE_TTL:
            return _CATALOG_CACHE.get("models", [])

    version = get_cli_version(resolved_exe)
    cache_key = f"{resolved_exe}:{version}"

    if not force_refresh and _CATALOG_CACHE.get("key") == cache_key:
        if now - _CATALOG_CACHE.get("timestamp", 0.0) < _CATALOG_CACHE_TTL:
            _CATALOG_CACHE["executable"] = resolved_exe
            _CATALOG_CACHE["timestamp"] = now
            return _CATALOG_CACHE.get("models", [])

    try:
        res = subprocess.run(
            [resolved_exe, "--output-format", "json", "models"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        stdout = res.stdout or ""
        models = parse_model_catalog_output(stdout)
    except Exception:
        models = []

    _CATALOG_CACHE = {
        "executable": resolved_exe,
        "version": version,
        "key": cache_key,
        "timestamp": now,
        "models": models,
    }
    return models


def invalidate_model_catalog_cache() -> None:
    global _CATALOG_CACHE
    _CATALOG_CACHE = {"executable": "", "version": "", "key": "", "timestamp": 0.0, "models": []}


def parse_gemini_model_rank(model_dict: dict[str, str], lane_id: str = "") -> tuple[int, float, int]:
    model_id = model_dict.get("id", "").lower()
    is_pro = 1 if "pro" in model_id else 0

    match = re.search(r"gemini-(\d+(?:\.\d+)?)", model_id)
    version = float(match.group(1)) if match else 0.0

    is_worker = lane_id.lower() in {"worker", "subagent"} or "worker" in lane_id.lower()

    if "high" in model_id:
        tier_score = 2 if is_worker else 3
    elif "medium" in model_id:
        tier_score = 3 if is_worker else 2
    elif "low" in model_id:
        tier_score = 1
    else:
        tier_score = 2

    return (is_pro, version, tier_score)


def filter_and_rank_catalog_models(models: list[dict[str, str]], lane_id: str = "") -> list[dict[str, str]]:
    candidates = []
    for item in models:
        m_id = item.get("id", "")
        m_id_lower = m_id.lower()
        if "gemini" not in m_id_lower:
            continue
        if re.search(r"gemini-3\.1-pro", m_id_lower):
            continue
        candidates.append(item)

    if not candidates:
        return []

    candidates.sort(key=lambda m: parse_gemini_model_rank(m, lane_id), reverse=True)
    return candidates


def resolve_model_policy(
    model: str = "",
    lane_id: str = "",
    conversation_directory: str = "",
    executable: str = "",
    for_rpc: bool = False,
    force_refresh_catalog: bool = False,
) -> ModelPolicyResult:
    explicit_model = model.strip()
    env_model = os.environ.get("ANTIGRAVITY_MODEL", "").strip()
    recent = find_recent_model_selection(conversation_directory)

    if explicit_model:
        if re.match(r"^MODEL_PLACEHOLDER_M\d+$", explicit_model):
            matched_id = recent.model_id if recent.model_enum == explicit_model else explicit_model
            return ModelPolicyResult(matched_id, "explicit", f"explicit model enum {explicit_model} requested", explicit_model)
        enum = recent.model_enum if recent.model_id == explicit_model and recent.model_enum else KNOWN_MODEL_ENUMS.get(explicit_model, "")
        return ModelPolicyResult(explicit_model, "explicit", f"explicit --model {explicit_model} requested", enum)

    if env_model:
        enum = recent.model_enum if recent.model_id == env_model and recent.model_enum else KNOWN_MODEL_ENUMS.get(env_model, "")
        return ModelPolicyResult(env_model, "environment", f"ANTIGRAVITY_MODEL environment variable {env_model} set", enum)

    catalog_models = fetch_model_catalog(executable, force_refresh=force_refresh_catalog)
    ranked_candidates = filter_and_rank_catalog_models(catalog_models, lane_id=lane_id)
    if ranked_candidates:
        best = ranked_candidates[0]["id"]
        proven_enum = ""
        if best in KNOWN_MODEL_ENUMS:
            proven_enum = KNOWN_MODEL_ENUMS[best]
        elif recent.model_id == best and recent.model_enum:
            proven_enum = recent.model_enum

        if for_rpc:
            if proven_enum:
                return ModelPolicyResult(best, "catalog", f"catalog selected {best} for {lane_id or 'main'} lane", proven_enum)
            default_enum = KNOWN_MODEL_ENUMS.get(DEFAULT_AGY_MODEL, "MODEL_PLACEHOLDER_M71")
            return ModelPolicyResult(
                DEFAULT_AGY_MODEL,
                "default",
                f"RPC compatibility fallback to default {DEFAULT_AGY_MODEL} because catalog model {best} has no proven RPC enum",
                default_enum,
            )
        else:
            return ModelPolicyResult(best, "catalog", f"catalog selected {best} for {lane_id or 'main'} lane", proven_enum)

    if recent.model_id:
        return ModelPolicyResult(recent.model_id, "recent_conversation", f"recent conversation selection {recent.model_id}", recent.model_enum)

    default_enum = KNOWN_MODEL_ENUMS.get(DEFAULT_AGY_MODEL, "MODEL_PLACEHOLDER_M71")
    return ModelPolicyResult(DEFAULT_AGY_MODEL, "default", f"DEFAULT_AGY_MODEL fallback {DEFAULT_AGY_MODEL}", default_enum)


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
        return ModelSelection(explicit_model, KNOWN_MODEL_ENUMS.get(explicit_model, ""))

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


def resolve_agy_executable(explicit: str = "") -> str:
    candidates = [explicit.strip(), os.environ.get("ANTIGRAVITY_AGY_PATH", "").strip()]
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(str(Path(local_app_data) / "agy" / "bin" / "agy.exe"))
    path_match = shutil.which("agy")
    if path_match:
        candidates.append(path_match)
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError("Official agy CLI was not found. Install agy or pass --agy-executable.")


def terminate_process_tree(process: subprocess.Popen[str], grace_seconds: int = 5) -> bool:
    if process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=grace_seconds,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=grace_seconds)
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=grace_seconds)
            return True
        except (OSError, subprocess.SubprocessError):
            return process.poll() is not None


def agy_receipt(
    *,
    conversation_id: str = "",
    status: str = "ERROR",
    response: str = "",
    error: Any = None,
    error_code: str = "",
    model: str = "",
    model_source: str = "",
    model_reason: str = "",
    workspace_path: str = "",
    exit_code: int | None = None,
    timed_out: bool = False,
    elapsed_seconds: float = 0.0,
) -> dict[str, Any]:
    usable = status == "SUCCESS" and not timed_out and exit_code == 0 and not error
    return {
        "transport": "agy",
        "legacy": False,
        "conversation_id": conversation_id,
        "status": status,
        "response": response,
        "error": error,
        "error_code": error_code,
        "model": model,
        "model_source": model_source,
        "model_reason": model_reason,
        "workspace_path": workspace_path,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "usable": usable,
        "resume_command": f"agy --conversation {conversation_id}" if conversation_id else "",
    }


def transcript_root() -> Path:
    explicit = os.environ.get("ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "AntigravityBridge" / "conversations"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "antigravity-bridge" / "conversations"


def select_agy_project(workspace_path: str, requested_project_id: str = "") -> tuple[str, str]:
    if requested_project_id.strip():
        return requested_project_id.strip(), "explicit"
    projects_root = Path.home() / ".gemini" / "config" / "projects"
    best: tuple[int, str] = (0, "")
    workspace = Path(workspace_path).resolve()
    try:
        config_paths = list(projects_root.glob("*.json"))
    except OSError:
        config_paths = []
    for config_path in config_paths:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        for resource in config.get("projectResources", {}).get("resources", []):
            uri = resource.get("folderUri") or resource.get("gitFolder", {}).get("folderUri", "") or resource.get("localFolder", {}).get("folderUri", "")
            if not isinstance(uri, str) or not uri.startswith("file:"):
                continue
            try:
                uri_path = urllib.parse.unquote(urllib.parse.urlparse(uri).path)
                if re.match(r"^/[A-Za-z]:[\\/]", uri_path):
                    uri_path = uri_path[1:]
                candidate = Path(uri_path).resolve()
            except (OSError, ValueError):
                continue
            if workspace == candidate or candidate in workspace.parents:
                score = len(str(candidate))
                project_id = str(config.get("id") or config_path.stem)
                if score > best[0]:
                    best = (score, project_id)
    return (best[1], "workspace_match") if best[1] else ("", "")


def protect_transcript_text(value: Any) -> str:
    safe = str(value or "")
    safe = re.sub(
        r"(?im)\b(csrf(?:[_-]?token)?|api[_-]?key|access[_-]?token|authorization)\b\s*[:=]\s*\S+",
        r"\1: <redacted>",
        safe,
    )
    return re.sub(r"(?i)\bBearer\s+\S+", "Bearer <redacted>", safe)

def finalize_agy_receipt(receipt: dict[str, Any], prompt: str, no_transcript: bool, project_id: str = "", project_source: str = "") -> dict[str, Any]:
    receipt["project_id"] = project_id
    receipt["project_source"] = project_source
    receipt["project_binding_requested"] = bool(project_id)
    receipt["ui_project_visibility"] = "not_verified"
    receipt["ui_note"] = (
        "Antigravity 2.4.3 may label agy SQLite conversations Outside of Project "
        "even when agy logs confirm the project id."
    )
    receipt["transcript_path"] = ""
    receipt["transcript_error"] = ""
    if no_transcript or not receipt["conversation_id"]:
        return receipt
    try:
        root = transcript_root()
        root.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", receipt["conversation_id"])
        path = root / f"{safe_name}.md"
        error = receipt["error"] or ""
        entry = (
            f"\n## {datetime.now(timezone.utc).isoformat()} UTC\n"
            f"- model: {protect_transcript_text(receipt['model'])}\n"
            f"- workspace: {protect_transcript_text(receipt['workspace_path'])}\n"
            f"- status: {protect_transcript_text(receipt['status'])}\n\n"
            f"### Prompt\n{protect_transcript_text(prompt)}\n\n### Response\n{protect_transcript_text(receipt['response'])}\n\n### Error\n{protect_transcript_text(error)}\n"
        )
        with path.open("a", encoding="utf-8", newline="\n") as transcript:
            transcript.write(entry)
        receipt["transcript_path"] = str(path)
    except Exception as exc:
        receipt["transcript_error"] = str(exc)
    return receipt
def run_agy_prompt(
    prompt: str,
    conversation_id: str = "",
    model: str = "",
    timeout_seconds: int = 90,
    executable: str = "",
    workspace_path: str = "",
    no_transcript: bool = False,
    project_id: str = "",
    lane_id: str = "",
) -> dict[str, Any]:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")
    resolved_workspace = validate_workspace_boundary(workspace_path)
    if not Path(resolved_workspace).is_dir():
        raise ValueError(f"workspace_path must be an existing directory: {resolved_workspace}")

    policy = resolve_model_policy(model=model, lane_id=lane_id, executable=executable, for_rpc=False)
    selected_model = policy.model_id
    selected_source = policy.source
    selected_reason = policy.reason

    selected_project_id, selected_project_source = ("", "") if conversation_id else select_agy_project(resolved_workspace, project_id)
    started = time.monotonic()
    try:
        resolved_executable = resolve_agy_executable(executable)
    except OSError as exc:
        return finalize_agy_receipt(agy_receipt(
            error={"code": "agy_unavailable", "message": str(exc)},
            error_code="agy_unavailable",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            elapsed_seconds=time.monotonic() - started,
        ), prompt, no_transcript, selected_project_id, selected_project_source)
    command = [
        resolved_executable,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        selected_model,
        "--add-dir",
        resolved_workspace,
        "--print-timeout",
        f"{max(1, timeout_seconds - 5)}s",
    ]
    if selected_project_id:
        command.extend(["--project", selected_project_id])
    if conversation_id:
        command.extend(["--conversation", conversation_id])
    popen_options: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "cwd": resolved_workspace,
    }
    if os.name == "nt":
        popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **popen_options)
    except OSError as exc:
        return finalize_agy_receipt(agy_receipt(
            error={"code": "agy_unavailable", "message": str(exc)},
            error_code="agy_unavailable",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            elapsed_seconds=time.monotonic() - started,
        ), prompt, no_transcript, selected_project_id, selected_project_source)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        terminated = terminate_process_tree(process)
        return finalize_agy_receipt(agy_receipt(
            conversation_id=conversation_id,
            status="TIMEOUT",
            error={
                "code": "deadline_exceeded" if terminated else "kill_failed",
                "message": f"agy exceeded {timeout_seconds} seconds",
            },
            error_code="deadline_exceeded" if terminated else "kill_failed",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            exit_code=process.poll(),
            timed_out=True,
            elapsed_seconds=time.monotonic() - started,
        ), prompt, no_transcript, selected_project_id, selected_project_source)
    elapsed = time.monotonic() - started
    try:
        raw = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        return finalize_agy_receipt(agy_receipt(
            conversation_id=conversation_id,
            error={"code": "invalid_agy_json", "message": stderr.strip() or "agy did not produce JSON output"},
            error_code="invalid_agy_json",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            exit_code=process.returncode,
            elapsed_seconds=elapsed,
        ), prompt, no_transcript, selected_project_id, selected_project_source)
    if not isinstance(raw, dict):
        return finalize_agy_receipt(agy_receipt(
            conversation_id=conversation_id,
            error={"code": "invalid_agy_receipt", "message": "agy JSON output must be an object"},
            error_code="invalid_agy_receipt",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            exit_code=process.returncode,
            elapsed_seconds=elapsed,
        ), prompt, no_transcript, selected_project_id, selected_project_source)
    raw_error = raw.get("error")
    error_text = str(raw_error or stderr).strip()
    if "unknown model" in error_text.lower() or "invalid model" in error_text.lower():
        invalidate_model_catalog_cache()
    status = str(raw.get("status") or ("SUCCESS" if process.returncode == 0 else "ERROR")).upper()
    error_code = ""
    if "timeout waiting for response" in error_text.lower():
        error_code = "agy_response_timeout"
    elif process.returncode != 0 or status != "SUCCESS":
        error_code = "agy_failed"
    if process.returncode != 0:
        status = "ERROR"
    error: Any = raw_error
    if error_code and not error:
        error = {"code": error_code, "message": stderr.strip() or f"agy exited with code {process.returncode}"}
    return finalize_agy_receipt(
        agy_receipt(
            conversation_id=str(raw.get("conversation_id") or conversation_id),
            status=status,
            response=str(raw.get("response") or ""),
            error=error,
            error_code=error_code,
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            exit_code=process.returncode,
            elapsed_seconds=elapsed,
        ),
        prompt,
        no_transcript,
        selected_project_id,
        selected_project_source,
    )

def service_uri(session: AntigravitySession, method: str) -> str:
    return SERVICE_PREFIX.format(port=session.http_port, method=method)


def invoke_rpc(method: str, body: dict[str, Any], session: AntigravitySession | None = None, deadline: float | None = None) -> Any:
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
    if deadline is None:
        timeout = 30.0
    else:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("RPC deadline exceeded before request dispatch")
        timeout = min(30.0, remaining)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            message = "session expired or is not authorized; rediscover the local session"
        else:
            message = f"HTTP {exc.code}"
        raise RuntimeError(f"Antigravity RPC {method} failed: {message}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or isinstance(exc, TimeoutError):
            message = "request timed out; check that Antigravity is running and retry"
        else:
            message = "local session is unavailable; rediscover the session and retry"
        raise RuntimeError(f"Antigravity RPC {method} failed: {message}") from exc

    if not data:
        return {}
    return json.loads(data.decode("utf-8"))


def new_cascade(
    workspace_paths: list[str] | None = None,
    model: str = "",
    cascade_id: str = "",
    session: AntigravitySession | None = None,
    deadline: float | None = None,
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

    response = invoke_rpc("StartCascade", body, session, deadline)
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
    deadline: float | None = None,
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
    return invoke_rpc("SendUserCascadeMessage", body, session, deadline)


def _rpc_receipt(
    *,
    cascade_id: str,
    marker: str,
    status: str,
    response: str,
    error: str | None,
    model: str,
    model_source: str = "",
    model_reason: str = "",
    workspace_path: str,
    started: float,
    timed_out: bool = False,
    delivery_state: str = "NOT_SENT",
    safe_to_fallback: bool = True,
    request_id: str = "",
    request_id_source: str = "provided",
    mission_id: str = "",
    lane_id: str = "",
    owner_id: str = "",
    lane_epoch: int = 0,
    lane_state: str = "",
) -> dict[str, Any]:
    terminal = status in {"COMPLETED", "ERROR", "CONFLICT"}
    return {
        "transport": "rpc",
        "legacy": False,
        "private": True,
        "conversation_id": cascade_id,
        "cascade_id": cascade_id,
        "marker": marker,
        "request_id": request_id,
        "request_id_source": request_id_source,
        "mission_id": mission_id,
        "lane_id": lane_id,
        "owner_id": owner_id,
        "lane_epoch": lane_epoch,
        "lane_state": lane_state or ("ACTIVE" if owner_id else "UNBOUND"),
        "status": status,
        "delivery_state": delivery_state,
        "safe_to_fallback": safe_to_fallback,
        "retryable": not terminal,
        "response": response,
        "error": error,
        "model": model,
        "model_source": model_source,
        "model_reason": model_reason,
        "workspace_path": workspace_path,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "usable": status == "COMPLETED",
        "visibility": "hub_visible" if status == "COMPLETED" else "not_verified",
        "visibility_evidence": (
            "native cascade indexed by Antigravity Hub"
            if status == "COMPLETED"
            else "RPC attempt did not complete"
        ),
        "fallback_used": False,
        "attempted_transports": ["rpc"],
        "resume_command": f"rpc cascade {cascade_id}" if cascade_id else "",
    }


def _reconcile_delivery(
    cascade_id: str,
    marker: str,
    deadline: float,
    session: AntigravitySession,
    model: str,
    workspace_path: str,
    started: float,
    request_id: str,
    request_id_source: str,
    mission_id: str,
    lane_id: str,
    model_source: str = "",
    model_reason: str = "",
    owner_id: str = "",
    lane_epoch: int = 0,
    lane_state: str = "",
) -> dict[str, Any]:
    try:
        outcome = wait_trajectory_outcome(
            cascade_id,
            re.escape(marker),
            session=session,
            deadline=deadline,
        )
        if outcome.get("matched"):
            return _rpc_receipt(
                cascade_id=cascade_id,
                marker=marker,
                status="COMPLETED",
                response=str(outcome.get("response") or ""),
                error=None,
                model=model,
                model_source=model_source,
                model_reason=model_reason,
                workspace_path=workspace_path,
                started=started,
                delivery_state="COMPLETED",
                safe_to_fallback=False,
                request_id=request_id,
                request_id_source=request_id_source,
                mission_id=mission_id,
                lane_id=lane_id,
                owner_id=owner_id,
                lane_epoch=lane_epoch,
                lane_state=lane_state,
            )
        failure = str(outcome.get("failure") or "")
        if failure and classify_predispatch_failure(failure) == HealthState.INPUT_REQUIRED:
            return _rpc_receipt(
                cascade_id=cascade_id,
                marker=marker,
                status="INPUT_REQUIRED",
                response=str(outcome.get("response") or ""),
                error=failure,
                model=model,
                model_source=model_source,
                model_reason=model_reason,
                workspace_path=workspace_path,
                started=started,
                delivery_state="INPUT_REQUIRED",
                safe_to_fallback=False,
                request_id=request_id,
                request_id_source=request_id_source,
                mission_id=mission_id,
                lane_id=lane_id,
                owner_id=owner_id,
                lane_epoch=lane_epoch,
                lane_state=lane_state,
            )
        return _rpc_receipt(
            cascade_id=cascade_id,
            marker=marker,
            status="ACCEPTED_PENDING",
            response=str(outcome.get("response") or ""),
            error=str(outcome.get("failure") or "") or None,
            model=model,
            model_source=model_source,
            model_reason=model_reason,
            workspace_path=workspace_path,
            started=started,
            timed_out=True,
            delivery_state="ACCEPTED_PENDING",
            safe_to_fallback=False,
            request_id=request_id,
            request_id_source=request_id_source,
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )
    except Exception as exc:
        return _rpc_receipt(
            cascade_id=cascade_id,
            marker=marker,
            status="DELIVERY_UNKNOWN",
            response="",
            error=str(exc),
            model=model,
            model_source=model_source,
            model_reason=model_reason,
            workspace_path=workspace_path,
            started=started,
            delivery_state="DELIVERY_UNKNOWN",
            safe_to_fallback=False,
            request_id=request_id,
            request_id_source=request_id_source,
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )


def run_visible_rpc_prompt(
    prompt: str,
    *,
    conversation_id: str = "",
    model: str = "",
    timeout_seconds: int = 90,
    workspace_path: str = "",
    request_id: str = "",
    mission_id: str = "",
    lane_id: str = "",
    journal_path: str = "",
    executable: str = "",
    owner_id: str = "",
    lane_epoch: int = 0,
    lane_lease_seconds: float = 60.0,
    lane_quota: int = -1,
) -> dict[str, Any]:
    """Send one idempotent Hub-native prompt; ambiguous delivery never falls back."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    import uuid

    started = time.monotonic()
    deadline = started + timeout_seconds
    resolved_workspace = validate_workspace_boundary(workspace_path)

    policy = resolve_model_policy(
        model=model,
        lane_id=lane_id,
        executable=executable,
        for_rpc=True,
    )
    selected_model = policy.model_id
    selected_source = policy.source
    selected_reason = policy.reason

    effective_owner_id = owner_id.strip() if owner_id else ""
    lane_state = "ACTIVE" if effective_owner_id else "UNBOUND"
    if effective_owner_id and (not mission_id.strip() or not lane_id.strip()):
        raise ValueError("owner_id coordination requires non-empty mission_id and lane_id")

    if not _GLOBAL_CIRCUIT_BREAKER.allow_request():
        return _rpc_receipt(
            cascade_id="",
            marker="",
            status="UNAVAILABLE",
            response="",
            error="Circuit breaker is OPEN; pre-dispatch request rejected fast",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            started=started,
            delivery_state="NOT_SENT",
            safe_to_fallback=True,
            request_id=request_id.strip() or str(uuid.uuid4()),
            request_id_source="provided" if request_id.strip() else "generated",
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=effective_owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )

    effective_request_id = request_id.strip() or str(uuid.uuid4())
    request_id_source = "provided" if request_id.strip() else "generated"
    cascade_id = conversation_id.strip() or str(uuid.uuid4())
    marker = f"ANTIGRAVITY_BRIDGE_MARKER_{uuid.uuid4().hex}"
    journal = RequestJournal(journal_path)
    fingerprint = request_fingerprint(
        prompt,
        conversation_id,
        model,
        resolved_workspace,
        mission_id,
        lane_id,
    )
    claim = journal.claim(effective_request_id, fingerprint)

    if claim["kind"] == "conflict":
        return _rpc_receipt(
            cascade_id="",
            marker="",
            status="CONFLICT",
            response="",
            error="request_id was already used with different request content",
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            started=started,
            delivery_state="CONFLICT",
            safe_to_fallback=False,
            request_id=effective_request_id,
            request_id_source=request_id_source,
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=effective_owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )

    if claim["kind"] == "replay":
        saved = claim.get("receipt") or {}
        prior_state = str(saved.get("delivery_state") or claim.get("state") or "")
        if prior_state not in DELIVERY_PENDING:
            saved["replayed"] = True
            return saved

        cascade_id = str(saved.get("cascade_id") or claim.get("cascade_id") or "")
        marker = str(saved.get("marker") or claim.get("marker") or "")
        if not cascade_id or not marker:
            return _rpc_receipt(
                cascade_id=cascade_id,
                marker=marker,
                status="IN_PROGRESS",
                response="",
                error="an identical request is already being prepared",
                model=selected_model,
                model_source=selected_source,
                model_reason=selected_reason,
                workspace_path=resolved_workspace,
                started=started,
                delivery_state="IN_PROGRESS",
                safe_to_fallback=False,
                request_id=effective_request_id,
                request_id_source=request_id_source,
                mission_id=mission_id,
                lane_id=lane_id,
                owner_id=effective_owner_id,
                lane_epoch=lane_epoch,
                lane_state=lane_state,
            )
        try:
            session = get_session_info()
        except Exception:
            return _rpc_receipt(
                cascade_id=cascade_id,
                marker=marker,
                status="DELIVERY_UNKNOWN",
                response="",
                error="delivery is pending and session discovery failed",
                model=selected_model,
                model_source=selected_source,
                model_reason=selected_reason,
                workspace_path=resolved_workspace,
                started=started,
                delivery_state="DELIVERY_UNKNOWN",
                safe_to_fallback=False,
                request_id=effective_request_id,
                request_id_source=request_id_source,
                mission_id=mission_id,
                lane_id=lane_id,
                owner_id=effective_owner_id,
                lane_epoch=lane_epoch,
                lane_state=lane_state,
            )
        receipt = _reconcile_delivery(
            cascade_id,
            marker,
            deadline,
            session,
            selected_model,
            resolved_workspace,
            started,
            effective_request_id,
            request_id_source,
            mission_id,
            lane_id,
            model_source=selected_source,
            model_reason=selected_reason,
            owner_id=effective_owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )
        journal.finish(effective_request_id, receipt)
        if receipt.get("delivery_state") == "COMPLETED":
            _GLOBAL_CIRCUIT_BREAKER.record_success()
        return receipt

    if effective_owner_id:
        auth = journal.authorize_lane_prompt(
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=effective_owner_id,
            epoch=lane_epoch,
            lease_seconds=lane_lease_seconds,
            quota=lane_quota,
        )
        if not auth["authorized"]:
            receipt = _rpc_receipt(
                cascade_id="",
                marker="",
                status=auth["status"],
                response="",
                error=auth.get("error"),
                model=selected_model,
                model_source=selected_source,
                model_reason=selected_reason,
                workspace_path=resolved_workspace,
                started=started,
                delivery_state="NOT_SENT",
                safe_to_fallback=False,
                request_id=effective_request_id,
                request_id_source=request_id_source,
                mission_id=mission_id,
                lane_id=lane_id,
                owner_id=effective_owner_id,
                lane_epoch=auth.get("epoch", lane_epoch),
                lane_state=auth.get("lane_state", "BUSY"),
            )
            journal.finish(effective_request_id, receipt)
            return receipt
        lane_epoch = auth.get("epoch", lane_epoch)
        lane_state = auth.get("lane_state", "ACTIVE")

    # Persist caller-visible IDs before StartCascade so a Start timeout is recoverable.
    journal.prepare_delivery(effective_request_id, cascade_id, marker, state="PREPARING")
    try:
        session = get_session_info()
        if not conversation_id.strip():
            new_cascade(
                [resolved_workspace],
                model=selected_model,
                cascade_id=cascade_id,
                session=session,
                deadline=deadline,
            )
    except Exception as exc:
        failure_class = classify_predispatch_failure(exc)
        if failure_class == HealthState.UNAVAILABLE:
            _GLOBAL_CIRCUIT_BREAKER.record_failure(failure_class)
        receipt = _rpc_receipt(
            cascade_id=cascade_id,
            marker=marker,
            status=failure_class if failure_class == HealthState.INPUT_REQUIRED else "ERROR",
            response="",
            error=str(exc),
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            started=started,
            delivery_state="INPUT_REQUIRED" if failure_class == HealthState.INPUT_REQUIRED else "NOT_SENT",
            safe_to_fallback=failure_class != HealthState.INPUT_REQUIRED,
            request_id=effective_request_id,
            request_id_source=request_id_source,
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=effective_owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )
        journal.finish(effective_request_id, receipt)
        return receipt

    journal.prepare_delivery(effective_request_id, cascade_id, marker, state="DELIVERING")
    marked_prompt = (
        f"{prompt.rstrip()}\n\n"
        f"Please finish your reply with this exact marker on its own line: {marker}"
    )
    try:
        send_message(
            cascade_id,
            marked_prompt,
            model=selected_model,
            session=session,
            deadline=deadline,
        )
    except Exception as exc:
        _GLOBAL_CIRCUIT_BREAKER.record_failure("DELIVERY_UNKNOWN")
        receipt = _rpc_receipt(
            cascade_id=cascade_id,
            marker=marker,
            status="DELIVERY_UNKNOWN",
            response="",
            error=str(exc),
            model=selected_model,
            model_source=selected_source,
            model_reason=selected_reason,
            workspace_path=resolved_workspace,
            started=started,
            delivery_state="DELIVERY_UNKNOWN",
            safe_to_fallback=False,
            request_id=effective_request_id,
            request_id_source=request_id_source,
            mission_id=mission_id,
            lane_id=lane_id,
            owner_id=effective_owner_id,
            lane_epoch=lane_epoch,
            lane_state=lane_state,
        )
        journal.finish(effective_request_id, receipt)
        return receipt

    receipt = _reconcile_delivery(
        cascade_id,
        marker,
        deadline,
        session,
        selected_model,
        resolved_workspace,
        started,
        effective_request_id,
        request_id_source,
        mission_id,
        lane_id,
        model_source=selected_source,
        model_reason=selected_reason,
        owner_id=effective_owner_id,
        lane_epoch=lane_epoch,
        lane_state=lane_state,
    )
    if receipt.get("delivery_state") == "COMPLETED":
        _GLOBAL_CIRCUIT_BREAKER.record_success()
    journal.finish(effective_request_id, receipt)
    return receipt


def run_prompt(
    prompt: str,
    *,
    transport: str = "auto",
    conversation_id: str = "",
    model: str = "",
    timeout_seconds: int = 90,
    executable: str = "",
    workspace_path: str = "",
    no_transcript: bool = False,
    project_id: str = "",
    request_id: str = "",
    mission_id: str = "",
    lane_id: str = "",
    journal_path: str = "",
    owner_id: str = "",
    lane_epoch: int = 0,
    lane_lease_seconds: float = 60.0,
    lane_quota: int = -1,
) -> dict[str, Any]:
    if transport not in {"auto", "rpc", "agy"}:
        raise ValueError("transport must be one of: auto, rpc, agy")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than zero")

    deadline = time.monotonic() + timeout_seconds
    if transport in {"auto", "rpc"}:
        rpc_receipt = run_visible_rpc_prompt(
            prompt,
            conversation_id=conversation_id,
            model=model,
            timeout_seconds=deadline - time.monotonic(),
            workspace_path=workspace_path,
            request_id=request_id,
            mission_id=mission_id,
            lane_id=lane_id,
            journal_path=journal_path,
            executable=executable,
            owner_id=owner_id,
            lane_epoch=lane_epoch,
            lane_lease_seconds=lane_lease_seconds,
            lane_quota=lane_quota,
        )
        if (
            transport == "rpc"
            or rpc_receipt["usable"]
            or not rpc_receipt.get("safe_to_fallback", True)
        ):
            return rpc_receipt

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            rpc_receipt["fallback_skipped"] = "global_deadline_exceeded"
            return rpc_receipt

        agy_receipt_value = run_agy_prompt(
            prompt,
            model=model,
            timeout_seconds=remaining,
            executable=executable,
            workspace_path=workspace_path,
            no_transcript=no_transcript,
            project_id=project_id,
            lane_id=lane_id,
        )
        agy_receipt_value.update(
            {
                "request_id": rpc_receipt.get("request_id", request_id),
                "request_id_source": rpc_receipt.get("request_id_source", "provided"),
                "mission_id": mission_id,
                "lane_id": lane_id,
                "delivery_state": str(agy_receipt_value.get("status") or "ERROR"),
                "safe_to_fallback": False,
                "retryable": False,
                "fallback_used": True,
                "attempted_transports": ["rpc", "agy"],
                "rpc_cascade_id": rpc_receipt.get("cascade_id", ""),
                "rpc_failure": rpc_receipt.get("error"),
                "fallback_continuation": (
                    "new_conversation" if conversation_id else "native_agy"
                ),
                "visibility": "not_verified",
                "visibility_evidence": "agy fallback is not a Hub-native visible cascade",
            }
        )
        if agy_receipt_value.get("request_id"):
            RequestJournal(journal_path).finish(
                str(agy_receipt_value["request_id"]),
                agy_receipt_value,
            )
        return agy_receipt_value

    import uuid

    direct_request_id = request_id.strip() or str(uuid.uuid4())
    direct_receipt = run_agy_prompt(
        prompt,
        conversation_id=conversation_id,
        model=model,
        timeout_seconds=timeout_seconds,
        executable=executable,
        workspace_path=workspace_path,
        no_transcript=no_transcript,
        project_id=project_id,
        lane_id=lane_id,
    )
    direct_receipt.update(
        {
            "request_id": direct_request_id,
            "request_id_source": "provided" if request_id.strip() else "generated",
            "mission_id": mission_id,
            "lane_id": lane_id,
            "delivery_state": "COMPLETED" if direct_receipt.get("usable") else str(direct_receipt.get("status") or "ERROR"),
            "safe_to_fallback": False,
            "retryable": False,
            "delivery_guarantee": "best_effort_no_persistent_deduplication",
        }
    )
    return direct_receipt

def get_trajectory(cascade_id: str, verbosity: int = 2, session: AntigravitySession | None = None, deadline: float | None = None) -> Any:
    envelope = invoke_rpc("GetCascadeTrajectory", {"cascadeId": cascade_id, "verbosity": verbosity}, session, deadline)
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
    deadline: float | None = None,
) -> dict[str, Any]:
    deadline = deadline if deadline is not None else time.monotonic() + timeout_seconds
    last_trajectory: Any = None
    last_response = ""
    last_error = ""
    last_combined = ""
    compiled = re.compile(pattern)

    while True:
        last_trajectory = get_trajectory(cascade_id, session=session, deadline=deadline)
        last_response = latest_planner_response_text(last_trajectory)
        last_error = latest_error_text(last_trajectory)
        last_combined = "\n".join([last_response, last_error])

        if last_error:
            return {
                "cascadeId": cascade_id,
                "pattern": pattern,
                "matched": False,
                "timedOut": False,
                "trajectory": last_trajectory,
                "response": last_response,
                "failure": last_error,
                "observedText": last_combined,
            }

        if compiled.search(last_response):
            return {
                "cascadeId": cascade_id,
                "pattern": pattern,
                "matched": True,
                "timedOut": False,
                "trajectory": last_trajectory,
                "response": last_response,
                "failure": "",
                "observedText": last_combined,
            }
        if time.monotonic() >= deadline:
            break
        time.sleep(min(poll_interval_seconds, max(0.0, deadline-time.monotonic())))

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
    sys.stdout.buffer.write((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Talk to a locally logged-in Antigravity session.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    discover = subparsers.add_parser("discover")
    discover.add_argument("--show-secret", action="store_true")

    prompt = subparsers.add_parser("prompt", help="Run a Hub-visible RPC prompt with agy fallback.")
    prompt.add_argument("--prompt", required=True)
    prompt.add_argument("--conversation", default="")
    prompt.add_argument("--model", default="")
    prompt.add_argument("--transport", choices=["auto", "rpc", "agy"], default="auto")
    prompt.add_argument("--timeout-seconds", type=int, default=90)
    prompt.add_argument("--agy-executable", default="")
    prompt.add_argument("--no-transcript", action="store_true")
    prompt.add_argument("--project-id", default="")
    prompt.add_argument("--request-id", default="", help="Keep this value for retries to avoid duplicate delivery.")
    prompt.add_argument("--mission-id", default="")
    prompt.add_argument("--lane-id", default="")
    prompt.add_argument("--owner-id", default="")
    prompt.add_argument("--lane-epoch", type=int, default=0)
    prompt.add_argument("--lane-lease-seconds", type=float, default=60.0)
    prompt.add_argument("--lane-quota", type=int, default=-1)
    prompt.add_argument("--workspace-path", default=os.getcwd())

    lane = subparsers.add_parser("lane", help="Manage lane leases and coordination.")
    lane_sub = lane.add_subparsers(dest="lane_action", required=True)

    c_claim = lane_sub.add_parser("claim")
    c_claim.add_argument("--mission-id", required=True)
    c_claim.add_argument("--lane-id", required=True)
    c_claim.add_argument("--owner-id", required=True)
    c_claim.add_argument("--lease-seconds", type=float, default=60.0)
    c_claim.add_argument("--quota", type=int, default=-1)
    c_claim.add_argument("--epoch", type=int, default=0)
    c_claim.add_argument("--journal-path", default="")

    c_renew = lane_sub.add_parser("renew")
    c_renew.add_argument("--mission-id", required=True)
    c_renew.add_argument("--lane-id", required=True)
    c_renew.add_argument("--owner-id", required=True)
    c_renew.add_argument("--epoch", type=int, default=0)
    c_renew.add_argument("--lease-seconds", type=float, default=60.0)
    c_renew.add_argument("--journal-path", default="")

    c_cancel = lane_sub.add_parser("cancel")
    c_cancel.add_argument("--mission-id", required=True)
    c_cancel.add_argument("--lane-id", required=True)
    c_cancel.add_argument("--journal-path", default="")

    c_release = lane_sub.add_parser("release")
    c_release.add_argument("--mission-id", required=True)
    c_release.add_argument("--lane-id", required=True)
    c_release.add_argument("--owner-id", required=True)
    c_release.add_argument("--epoch", type=int, default=0)
    c_release.add_argument("--journal-path", default="")

    start = subparsers.add_parser("start")
    start.add_argument("--workspace-path", default=os.getcwd())
    start.add_argument("--opening-prompt", required=True)
    start.add_argument("--model", default="")
    start.add_argument("--wait-pattern", default="")
    start.add_argument("--timeout-seconds", type=int, default=90)
    start.add_argument("--allow-timeout", action="store_true")
    start.add_argument("--include-trajectory", action="store_true")

    send = subparsers.add_parser("send")
    send.add_argument("--cascade-id", required=True)
    send.add_argument("--text", required=True)
    send.add_argument("--model", default="")
    send.add_argument("--wait-pattern", default="")
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

    health = subparsers.add_parser("health", help="Run read-only health assessment.")
    health.add_argument("--journal-path", default="")
    health.add_argument("--workspace-path", default=os.getcwd())
    health.add_argument("--no-probe", action="store_true")
    health.add_argument("--restart", action="store_true", default=False)

    return parser


def run(args: argparse.Namespace) -> Any:
    if args.action == "health":
        h_res = assess_health(journal_path=args.journal_path, probe=not args.no_probe)
        pid = h_res["details"].get("process_id", 0)
        rec = get_process_ownership(pid)
        decision = assess_recovery_decision(
            h_res["status"],
            h_res["details"].get("has_pending_delivery", False),
            process_record=rec,
        )
        rec_dict = asdict(decision)
        if args.restart:
            exec_res = execute_recovery_restart(decision, rec, dry_run=True)
            rec_dict["execution"] = exec_res
        return {
            "status": h_res["status"],
            "details": h_res["details"],
            "circuit_breaker": _GLOBAL_CIRCUIT_BREAKER.current_state(),
            "recovery": rec_dict,
        }
    if args.action == "lane":
        journal = RequestJournal(args.journal_path)
        if args.lane_action == "claim":
            return journal.claim_lane_lease(
                mission_id=args.mission_id,
                lane_id=args.lane_id,
                owner_id=args.owner_id,
                lease_seconds=args.lease_seconds,
                initial_quota=args.quota,
                epoch=args.epoch,
            )
        elif args.lane_action == "renew":
            return journal.renew_lane_lease(
                mission_id=args.mission_id,
                lane_id=args.lane_id,
                owner_id=args.owner_id,
                epoch=args.epoch,
                lease_seconds=args.lease_seconds,
            )
        elif args.lane_action == "cancel":
            return journal.cancel_lane(
                mission_id=args.mission_id,
                lane_id=args.lane_id,
            )
        elif args.lane_action == "release":
            return journal.release_lane_lease(
                mission_id=args.mission_id,
                lane_id=args.lane_id,
                owner_id=args.owner_id,
                epoch=args.epoch,
            )
    if args.action == "prompt":
        return run_prompt(
            args.prompt,
            conversation_id=args.conversation,
            model=args.model,
            transport=args.transport,
            timeout_seconds=args.timeout_seconds,
            executable=args.agy_executable,
            workspace_path=args.workspace_path,
            no_transcript=args.no_transcript,
            project_id=args.project_id,
            request_id=args.request_id,
            mission_id=args.mission_id,
            lane_id=args.lane_id,
            owner_id=args.owner_id,
            lane_epoch=args.lane_epoch,
            lane_lease_seconds=args.lane_lease_seconds,
            lane_quota=args.lane_quota,
        )
    session = get_session_info()
    if args.action == "discover":
        return session.public_dict(show_secret=args.show_secret)
    if args.action == "start":
        pattern = args.wait_pattern.strip() if getattr(args, "wait_pattern", None) else ""
        if not pattern:
            marker = f"ANTIGRAVITY_BRIDGE_MARKER_{uuid.uuid4().hex}"
            prompt = f"{args.opening_prompt.rstrip()}\n\nPlease finish your reply with this exact marker on its own line: {marker}"
            pattern = re.escape(marker)
        else:
            prompt = args.opening_prompt

        cascade = new_cascade([args.workspace_path], model=args.model, session=session)
        send_message(cascade["cascadeId"], prompt, model=args.model, session=session)
        outcome = wait_trajectory_outcome(cascade["cascadeId"], pattern, args.timeout_seconds, session=session)
        if (outcome.get("timedOut") or outcome.get("failure")) and not args.allow_timeout:
            err_msg = outcome.get("failure") or f"Action 'start' timed out waiting for pattern {pattern} in cascade {cascade['cascadeId']}. Re-run with --allow-timeout to inspect partial output."
            raise RuntimeError(err_msg)
        return {
            "action": "start",
            "cascadeId": cascade["cascadeId"],
            "workspacePath": args.workspace_path,
            **compact_outcome(outcome, args.include_trajectory),
        }
    if args.action == "send":
        pattern = args.wait_pattern.strip() if getattr(args, "wait_pattern", None) else ""
        if not pattern:
            marker = f"ANTIGRAVITY_BRIDGE_MARKER_{uuid.uuid4().hex}"
            text = f"{args.text.rstrip()}\n\nPlease finish your reply with this exact marker on its own line: {marker}"
            pattern = re.escape(marker)
        else:
            text = args.text

        send_message(args.cascade_id, text, model=args.model, omit_requested_model=args.omit_requested_model, session=session)
        outcome = wait_trajectory_outcome(args.cascade_id, pattern, args.timeout_seconds, session=session)
        if (outcome.get("timedOut") or outcome.get("failure")) and not args.allow_timeout:
            err_msg = outcome.get("failure") or f"Action 'send' timed out waiting for pattern {pattern} in cascade {args.cascade_id}. Re-run with --allow-timeout to inspect partial output."
            raise RuntimeError(err_msg)
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

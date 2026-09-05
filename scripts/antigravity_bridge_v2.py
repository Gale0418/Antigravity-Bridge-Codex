#!/usr/bin/env python3
"""Progress-aware compatibility front door for Antigravity Bridge Codex.

The mature transport and delivery journal remain in ``antigravity_bridge``.
This module replaces only the trajectory watchdog and enriches receipts with
handoff-safety facts so long research tasks are not mistaken for dead agents.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import antigravity_bridge as bridge

_MIN_IDLE_SECONDS = 90.0
_MAX_IDLE_SECONDS = 600.0
_EWMA_ALPHA = 0.35
_GAP_MULTIPLIER = 4.0
_GAP_PADDING_SECONDS = 30.0

_SUPERVISOR_BY_CASCADE: dict[str, dict[str, Any]] = {}
_ORIGINAL_RUN_PROMPT = bridge.run_prompt


class _RustSupervisor:
    """One persistent Rust watchdog per wait call; never spawn per poll."""

    def __init__(self, started_ms: int, metrics: dict[str, int]) -> None:
        self.process: subprocess.Popen[str] | None = None
        for candidate in _rust_supervisor_candidates():
            if not candidate.is_file():
                continue
            try:
                process = subprocess.Popen(
                    [str(candidate)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.process = process
                self._write(
                    f"start {started_ms} {metrics['steps']} {metrics['response_bytes']} "
                    f"{metrics['tool_events']} {metrics['error_bytes']}"
                )
                if self._read().strip() != "READY":
                    self.close()
                return
            except OSError:
                self.close()
        self.process = None

    @property
    def available(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def observe(self, now_ms: int, metrics: dict[str, int], delivery: str) -> str:
        if not self.available:
            return ""
        try:
            self._write(
                f"observe {now_ms} {metrics['steps']} {metrics['response_bytes']} "
                f"{metrics['tool_events']} {metrics['error_bytes']} {delivery}"
            )
            line = self._read().strip()
            if not line.startswith("STATE "):
                return ""
            return line.split(None, 2)[1]
        except (OSError, BrokenPipeError):
            self.close()
            return ""

    def _write(self, line: str) -> None:
        if self.process is None or self.process.stdin is None:
            raise BrokenPipeError("Rust supervisor stdin is unavailable")
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def _read(self) -> str:
        if self.process is None or self.process.stdout is None:
            return ""
        return self.process.stdout.readline()

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.write("quit\n")
                process.stdin.flush()
        except OSError:
            pass
        try:
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except OSError:
                pass


def _rust_supervisor_candidates() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    suffix = ".exe" if os.name == "nt" else ""
    candidates = [root / "bin" / f"abc-supervisor{suffix}"]
    if os.environ.get("ANTIGRAVITY_BRIDGE_DEV_RUST", "").strip() == "1":
        candidates.append(root / "rust" / "target" / "release" / f"abc-supervisor{suffix}")
    return candidates


def _trajectory_steps(trajectory: Any) -> list[dict[str, Any]]:
    if not isinstance(trajectory, dict):
        return []
    raw = trajectory.get("steps")
    if not isinstance(raw, list):
        return []
    return [step for step in raw if isinstance(step, dict)]


def _meaningful_signature(trajectory: Any) -> tuple[str, dict[str, int]]:
    steps = _trajectory_steps(trajectory)
    response = bridge.latest_planner_response_text(trajectory)
    errors = bridge.latest_error_text(trajectory)
    tool_events = sum(
        1
        for step in steps
        if any(token in str(step.get("type") or "").upper() for token in ("TOOL", "SEARCH", "COMMAND", "BROWSER", "FILE"))
    )
    payload = {
        "steps": len(steps),
        "response_bytes": len(response.encode("utf-8", errors="replace")),
        "tool_events": tool_events,
        "error_bytes": len(errors.encode("utf-8", errors="replace")),
    }
    identity = {
        **payload,
        "tail_types": [str(step.get("type") or "") for step in steps[-8:]],
        "response_tail": response[-2048:],
        "error_tail": errors[-1024:],
    }
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return digest, payload


def _adaptive_idle_seconds(ewma_gap: float | None, minimum: float = _MIN_IDLE_SECONDS) -> float:
    minimum = max(1.0, min(_MIN_IDLE_SECONDS, minimum))
    if ewma_gap is None:
        return minimum
    return max(
        minimum,
        min(_MAX_IDLE_SECONDS, _GAP_MULTIPLIER * ewma_gap + _GAP_PADDING_SECONDS),
    )


def _record_supervisor(cascade_id: str, **values: Any) -> None:
    if cascade_id not in _SUPERVISOR_BY_CASCADE and len(_SUPERVISOR_BY_CASCADE) >= 256:
        _SUPERVISOR_BY_CASCADE.pop(next(iter(_SUPERVISOR_BY_CASCADE)))
    existing = _SUPERVISOR_BY_CASCADE.setdefault(cascade_id, {})
    existing.update(values)


def wait_trajectory_outcome(
    cascade_id: str,
    pattern: str,
    timeout_seconds: int = 90,
    poll_interval_seconds: int = 3,
    session: Any = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Wait for completion using *idle since meaningful progress*, not wall time.

    ``deadline`` from the legacy caller is treated as the initial response
    budget. Once dispatch has happened, observable trajectory progress refreshes
    the idle watchdog. When the response slice ends while work is still active,
    the bridge yields a safe non-terminal snapshot instead of declaring the remote
    writer dead or blocking the harness indefinitely.
    """

    started = time.monotonic()
    legacy_budget = max(1.0, (deadline - started) if deadline is not None else float(timeout_seconds))
    response_deadline = started + legacy_budget
    previous_supervisor = dict(_SUPERVISOR_BY_CASCADE.get(cascade_id) or {})
    last_progress = float(previous_supervisor.get("last_progress_monotonic", started))
    last_signature = str(previous_supervisor.get("signature") or "")
    ewma_gap_value = previous_supervisor.get("ewma_gap_seconds")
    ewma_gap: float | None = float(ewma_gap_value) if isinstance(ewma_gap_value, (int, float)) else None
    last_trajectory: Any = None
    last_response = ""
    last_error = ""
    last_combined = ""
    progress_count = int(previous_supervisor.get("progress_count", 0) or 0)
    compiled = re.compile(pattern)
    interval = max(0.05, min(float(poll_interval_seconds), 10.0))
    initial_metrics = {"steps": 0, "response_bytes": 0, "tool_events": 0, "error_bytes": 0}
    rust_supervisor = _RustSupervisor(int(started * 1000), initial_metrics)

    try:
        while True:
            now = time.monotonic()
            idle_threshold = _adaptive_idle_seconds(ewma_gap, legacy_budget)
            rpc_deadline = now + min(30.0, max(1.0, idle_threshold - (now - last_progress)))
            last_trajectory = bridge.get_trajectory(cascade_id, session=session, deadline=rpc_deadline)
            last_response = bridge.latest_planner_response_text(last_trajectory)
            last_error = bridge.latest_error_text(last_trajectory)
            last_combined = "\n".join([last_response, last_error])
            signature, metrics = _meaningful_signature(last_trajectory)

            if signature != last_signature:
                if last_signature:
                    gap = max(0.0, now - last_progress)
                    if gap > 0:
                        ewma_gap = gap if ewma_gap is None else _EWMA_ALPHA * gap + (1.0 - _EWMA_ALPHA) * ewma_gap
                last_signature = signature
                last_progress = now
                progress_count += 1
                supervisor_state = "ACTIVE"
            else:
                idle_age = max(0.0, now - last_progress)
                supervisor_state = "SUSPECT" if idle_age >= idle_threshold * 0.65 else "QUIET"

            rust_state = rust_supervisor.observe(int(now * 1000), metrics, "IN_PROGRESS")
            if rust_state:
                supervisor_state = rust_state

            _record_supervisor(
                cascade_id,
                state=supervisor_state,
                idle_age_seconds=round(max(0.0, now - last_progress), 3),
                idle_threshold_seconds=round(idle_threshold, 3),
                progress_count=progress_count,
                metrics=metrics,
                signature=last_signature,
                last_progress_monotonic=last_progress,
                ewma_gap_seconds=ewma_gap,
                remote_may_resume=True,
            )

            if last_error:
                _record_supervisor(cascade_id, state="INPUT_REQUIRED" if bridge.classify_predispatch_failure(last_error) == bridge.HealthState.INPUT_REQUIRED else "ERROR")
                return {
                    "cascadeId": cascade_id,
                    "pattern": pattern,
                    "matched": False,
                    "timedOut": False,
                    "trajectory": last_trajectory,
                    "response": last_response,
                    "failure": last_error,
                    "observedText": last_combined,
                    "supervisorState": _SUPERVISOR_BY_CASCADE[cascade_id]["state"],
                }

            if compiled.search(last_response):
                _record_supervisor(cascade_id, state="DONE", remote_may_resume=False)
                return {
                    "cascadeId": cascade_id,
                    "pattern": pattern,
                    "matched": True,
                    "timedOut": False,
                    "trajectory": last_trajectory,
                    "response": last_response,
                    "failure": "",
                    "observedText": last_combined,
                    "supervisorState": "DONE",
                }

            now = time.monotonic()
            idle_age = max(0.0, now - last_progress)
            idle_threshold = _adaptive_idle_seconds(ewma_gap, legacy_budget)
            if idle_age >= idle_threshold:
                _record_supervisor(
                    cascade_id,
                    state="STALLED",
                    idle_age_seconds=round(idle_age, 3),
                    idle_threshold_seconds=round(idle_threshold, 3),
                )
                break

            if now >= response_deadline:
                # The response slice ended, but the task is still alive. Yield a
                # nonterminal snapshot so Codex stays responsive and can reconcile
                # this same request_id later without spawning a second writer.
                _record_supervisor(cascade_id, state="ACTIVE_PENDING")
                return {
                    "cascadeId": cascade_id,
                    "pattern": pattern,
                    "matched": False,
                    "timedOut": True,
                    "trajectory": last_trajectory,
                    "response": last_response,
                    "failure": "",
                    "observedText": last_combined,
                    "supervisorState": "ACTIVE_PENDING",
                    "progressObserved": progress_count > 0,
                }

            adaptive_poll = interval if ewma_gap is None else max(interval, min(10.0, ewma_gap / 3.0))
            time.sleep(min(adaptive_poll, max(0.0, idle_threshold - idle_age)))

        return {
            "cascadeId": cascade_id,
            "pattern": pattern,
            "matched": False,
            "timedOut": True,
            "trajectory": last_trajectory,
            "response": last_response,
            "failure": last_error,
            "observedText": last_combined,
            "supervisorState": "STALLED",
            "progressObserved": progress_count > 0,
        }
    finally:
        rust_supervisor.close()


def _handoff_facts(receipt: dict[str, Any]) -> dict[str, Any]:
    delivery = str(receipt.get("delivery_state") or receipt.get("status") or "").upper()
    cascade_id = str(receipt.get("cascade_id") or receipt.get("conversation_id") or "")
    supervisor = dict(_SUPERVISOR_BY_CASCADE.get(cascade_id) or {})
    state = str(supervisor.get("state") or "UNKNOWN").upper()

    ambiguous = delivery in {
        "PREPARING",
        "IN_PROGRESS",
        "DELIVERING",
        "ACCEPTED_PENDING",
        "INPUT_REQUIRED",
        "DELIVERY_UNKNOWN",
    }
    write_safe = bool(
        delivery == "NOT_SENT"
        and state in {"STALLED", "ERROR", "UNKNOWN"}
        and receipt.get("safe_to_fallback", False)
    )
    remote_may_resume = ambiguous or bool(supervisor.get("remote_may_resume", False))
    return {
        "supervisor_state": state,
        "supervisor": supervisor,
        "may_handoff_read": True,
        "may_handoff_write": write_safe,
        "remote_may_resume": remote_may_resume,
        "handoff_reason": (
            "delivery may still be accepted or resume; same-workspace second writer is fenced"
            if ambiguous
            else "request is proven NOT_SENT and supervisor permits takeover"
            if write_safe
            else "handoff write is not proven safe"
        ),
    }


def run_prompt(*args: Any, **kwargs: Any) -> dict[str, Any]:
    receipt = _ORIGINAL_RUN_PROMPT(*args, **kwargs)
    if not isinstance(receipt, dict):
        raise RuntimeError("Antigravity prompt returned an invalid receipt")
    receipt.update(_handoff_facts(receipt))
    return receipt


# Patch only the orchestration surface. Transport, idempotency journal and RPC
# semantics stay in the mature module until they are independently ported.
bridge.wait_trajectory_outcome = wait_trajectory_outcome
bridge.run_prompt = run_prompt


def main(argv: list[str] | None = None) -> int:
    original = bridge.run_prompt
    bridge.run_prompt = run_prompt
    try:
        return bridge.main(argv)
    finally:
        bridge.run_prompt = original


if __name__ == "__main__":
    raise SystemExit(main())

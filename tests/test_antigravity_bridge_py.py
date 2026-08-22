from __future__ import annotations

import importlib.util
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "antigravity_bridge.py"
INSTALLER_PATH = REPO_ROOT / "scripts" / "install.py"

spec = importlib.util.spec_from_file_location("antigravity_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


def load_installer_module():
    installer_spec = importlib.util.spec_from_file_location("antigravity_installer", INSTALLER_PATH)
    installer = importlib.util.module_from_spec(installer_spec)
    sys.modules[installer_spec.name] = installer
    installer_spec.loader.exec_module(installer)
    return installer

TEST_TMP_ROOT = Path(
    os.environ.get(
        "ANTIGRAVITY_TEST_TMP_ROOT",
        str(Path(tempfile.gettempdir()) / "antigravity-bridge-codex-tests"),
    )
)


def fresh_test_dir(name: str) -> Path:
    path = TEST_TMP_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


class AntigravityBridgePythonTests(unittest.TestCase):
    def test_mcp_auto_launch_requires_boolean(self):
        server_spec = importlib.util.spec_from_file_location("antigravity_mcp_bool", REPO_ROOT / "mcp" / "antigravity_bridge_server.py")
        server = importlib.util.module_from_spec(server_spec)
        server_spec.loader.exec_module(server)
        result = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "antigravity_prompt", "arguments": {"prompt": "x", "auto_launch": "false"}},
            }
        )
        self.assertTrue(result["result"]["isError"])
        self.assertIn("must be a boolean", result["result"]["content"][0]["text"])

    def test_gui_launch_command_has_platform_specific_non_shell_branches(self):
        with patch.dict(os.environ, {"ANTIGRAVITY_GUI_PATH": "C:\\Apps\\Antigravity.exe"}, clear=False), patch.object(
            Path, "is_file", return_value=True
        ):
            self.assertEqual(
                bridge.resolve_gui_launch_command("Windows"),
                ["C:\\Apps\\Antigravity.exe"],
            )
        with patch.dict(os.environ, {"ANTIGRAVITY_GUI_PATH": ""}, clear=False):
            self.assertEqual(
                bridge.resolve_gui_launch_command("Windows"),
                ["explorer.exe", r"shell:AppsFolder\Google.Antigravity"],
            )
        with patch.dict(os.environ, {"ANTIGRAVITY_GUI_PATH": ""}, clear=False):
            self.assertEqual(bridge.resolve_gui_launch_command("macOS"), ["open", "-a", "Antigravity"])
        with patch.dict(os.environ, {"DISPLAY": ":99"}, clear=False), patch.object(Path, "is_file", return_value=True):
            self.assertEqual(bridge.resolve_gui_launch_command("Linux", "/usr/bin/antigravity"), ["/usr/bin/antigravity"])

    def test_prepare_session_launches_only_after_pre_dispatch_unavailable(self):
        fake_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        launched = []
        with patch.object(
            bridge,
            "get_session_info",
            side_effect=[RuntimeError("connection refused"), RuntimeError("logs unavailable")],
        ), patch.object(bridge, "launch_antigravity_gui", side_effect=lambda **kwargs: launched.append(kwargs) or {"status": "LAUNCHED"}), patch.object(
            bridge,
            "wait_for_session_ready",
            return_value=(fake_session, {"status": bridge.HealthState.HEALTHY, "probe": True}),
        ) as wait:
            session, info = bridge.prepare_session_for_dispatch(
                auto_launch=True,
                auto_launch_timeout_seconds=2,
                auto_launch_poll_interval_seconds=0.01,
                gui_path="fake",
                platform_name="Windows",
                gui_launcher=lambda command: None,
                process_scanner=lambda: False,
            )
        self.assertIs(session, fake_session)
        self.assertTrue(info["attempted"])
        self.assertEqual(len(launched), 1)
        wait.assert_called_once()

    def test_prepare_session_never_launches_second_app_for_live_but_unready_process(self):
        fake_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        with patch.object(bridge, "get_session_info", return_value=fake_session), patch.object(
            bridge, "is_process_alive", return_value=True
        ), patch.object(bridge, "invoke_rpc", side_effect=RuntimeError("connection refused")), patch.object(
            bridge,
            "wait_for_session_ready",
            return_value=(fake_session, {"status": bridge.HealthState.HEALTHY, "probe": True}),
        ), patch.object(bridge, "launch_antigravity_gui") as launch:
            session, info = bridge.prepare_session_for_dispatch(
                auto_launch=True,
                auto_launch_timeout_seconds=2,
                auto_launch_poll_interval_seconds=0.01,
                gui_path="fake",
                platform_name="Windows",
            )
        self.assertIs(session, fake_session)
        self.assertFalse(info["attempted"])
        launch.assert_not_called()

    def test_prepare_session_does_not_launch_for_input_required(self):
        fake_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        with patch.object(bridge, "get_session_info", return_value=fake_session), patch.object(
            bridge, "is_process_alive", return_value=True
        ), patch.object(bridge, "invoke_rpc", side_effect=RuntimeError("HTTP 401 unauthorized")), patch.object(
            bridge, "launch_antigravity_gui"
        ) as launch:
            session, info = bridge.prepare_session_for_dispatch(
                auto_launch=True,
                auto_launch_timeout_seconds=2,
                auto_launch_poll_interval_seconds=0.01,
                gui_path="fake",
                platform_name="Windows",
            )
        self.assertIsNone(session)
        self.assertEqual(info["status"], bridge.HealthState.INPUT_REQUIRED)
        launch.assert_not_called()

    def test_gui_launch_lock_allows_only_one_owner(self):
        root = fresh_test_dir("gui-launch-lock")
        lock_path = root / "gui-launch.lock"
        first, first_info = bridge.acquire_gui_launch_lock(str(lock_path))
        second, second_info = bridge.acquire_gui_launch_lock(str(lock_path))
        try:
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertEqual(first_info["status"], "ACQUIRED")
            self.assertEqual(second_info["status"], "BUSY")
        finally:
            bridge.release_gui_launch_lock(first)

    def test_half_written_launch_lock_is_busy_until_stale(self):
        root = fresh_test_dir("gui-launch-half-lock")
        lock_path = root / "gui-launch.lock"
        lock_path.write_text("{\"pid\":", encoding="utf-8")
        lock, info = bridge.acquire_gui_launch_lock(str(lock_path), stale_seconds=60)
        self.assertIsNone(lock)
        self.assertEqual(info["status"], "BUSY")

    def test_lock_recheck_waits_when_app_appears_before_launch(self):
        root = fresh_test_dir("gui-launch-race")
        fake_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        lock_path = root / "gui-launch.lock"
        with patch.object(
            bridge,
            "get_session_info",
            side_effect=[RuntimeError("connection refused"), RuntimeError("logs unavailable"), fake_session],
        ), patch.object(bridge, "acquire_gui_launch_lock", return_value=(lock_path, {"status": "ACQUIRED"})), patch.object(
            bridge, "is_process_alive", return_value=True
        ), patch.object(bridge, "wait_for_session_ready", return_value=(fake_session, {"status": bridge.HealthState.HEALTHY})), patch.object(
            bridge, "launch_antigravity_gui"
        ) as launch:
            session, info = bridge.prepare_session_for_dispatch(
                auto_launch=True,
                auto_launch_timeout_seconds=1,
                auto_launch_poll_interval_seconds=0.01,
                gui_path="fake",
                platform_name="Windows",
                process_scanner=lambda: False,
            )
        self.assertIs(session, fake_session)
        self.assertTrue(info.get("coalesced"))
        launch.assert_not_called()

    def test_lock_recheck_scans_when_discovery_pid_is_stale(self):
        root = fresh_test_dir("gui-launch-stale-session")
        stale_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        lock_path = root / "gui-launch.lock"
        with patch.object(bridge, "get_session_info", return_value=stale_session), patch.object(
            bridge, "is_process_alive", return_value=False
        ), patch.object(bridge, "acquire_gui_launch_lock", return_value=(lock_path, {"status": "ACQUIRED"})), patch.object(
            bridge, "wait_for_session_ready", return_value=(None, {"status": bridge.HealthState.UNAVAILABLE})
        ), patch.object(bridge, "launch_antigravity_gui") as launch:
            session, info = bridge.prepare_session_for_dispatch(
                auto_launch=True,
                auto_launch_timeout_seconds=1,
                auto_launch_poll_interval_seconds=0.01,
                gui_path="",
                platform_name="Windows",
                process_scanner=lambda: True,
            )
        self.assertIsNone(session)
        self.assertTrue(info["coalesced"])
        self.assertFalse(info["attempted"])
        launch.assert_not_called()

    def test_wait_for_session_ready_propagates_input_required(self):
        fake_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        session, info = bridge.wait_for_session_ready(
            1,
            discover=lambda: fake_session,
            alive=lambda _pid: True,
            probe=lambda _session, _deadline: (_ for _ in ()).throw(RuntimeError("HTTP 401 unauthorized")),
        )
        self.assertIsNone(session)
        self.assertEqual(info["status"], bridge.HealthState.INPUT_REQUIRED)

    def test_wait_for_session_ready_retries_startup_http_400(self):
        fake_session = bridge.AntigravitySession("token", "", 0, 1234, 4321, "", "")
        probes = iter([RuntimeError("HTTP 400"), {"ok": True}])

        def probe(_session, _deadline):
            outcome = next(probes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        session, info = bridge.wait_for_session_ready(
            1,
            poll_interval_seconds=0.01,
            discover=lambda: fake_session,
            alive=lambda _pid: True,
            probe=probe,
        )
        self.assertIs(session, fake_session)
        self.assertEqual(info["status"], bridge.HealthState.HEALTHY)

    def test_windows_unknown_process_scan_blocks_launch(self):
        with patch.object(bridge, "get_session_info", side_effect=RuntimeError("connection refused")), patch.object(
            bridge, "wait_for_session_ready", return_value=(None, {"status": bridge.HealthState.UNAVAILABLE})
        ) as wait, patch.object(bridge, "launch_antigravity_gui") as launch:
            session, info = bridge.prepare_session_for_dispatch(
                auto_launch=True,
                auto_launch_timeout_seconds=1,
                auto_launch_poll_interval_seconds=0.01,
                gui_path="fake",
                platform_name="Windows",
                process_scanner=lambda: None,
            )
        self.assertIsNone(session)
        self.assertIsNone(info["process_scan"])
        wait.assert_called_once()
        launch.assert_not_called()

    def test_best_effort_native_cleanup_ignores_launch_oserror(self):
        installer = load_installer_module()
        with patch.object(installer.subprocess, "run", side_effect=OSError("missing executable")):
            installer.run_native_best_effort(Path("codex"), "plugin", "remove", "legacy")

    def test_installer_rejects_missing_required_items(self):
        installer = load_installer_module()
        source = fresh_test_dir("installer-missing-source")
        (source / "SKILL.md").write_text("fixture", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "scripts, mcp"):
            installer.validate_source_items(
                source,
                ("SKILL.md", "scripts", "mcp"),
                "skill",
            )

    def test_transactional_sync_restores_previous_install_on_copy_failure(self):
        installer = load_installer_module()
        root = fresh_test_dir("installer-rollback")
        source = root / "source"
        destination = root / "installed"
        source.mkdir()
        destination.mkdir()
        (source / "first.txt").write_text("new", encoding="utf-8")
        (source / "second.txt").write_text("new", encoding="utf-8")
        (destination / "previous.txt").write_text("keep", encoding="utf-8")

        original_copy = installer.copy_fresh_item
        calls = 0

        def fail_second_copy(source_path, destination_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated copy failure")
            original_copy(source_path, destination_path)

        with patch.object(installer, "copy_fresh_item", side_effect=fail_second_copy):
            with self.assertRaisesRegex(OSError, "simulated copy failure"):
                installer.sync_items_transactional(
                    source,
                    destination,
                    ("first.txt", "second.txt"),
                )

        self.assertEqual((destination / "previous.txt").read_text(encoding="utf-8"), "keep")
        self.assertFalse((destination / "first.txt").exists())

    def test_installer_copies_skill_and_plugin_payload_to_isolated_codex_home(self):
        installer = load_installer_module()
        codex_home = fresh_test_dir("installer-codex-home")

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home)}), patch.object(
            installer, "get_codex_executable", return_value=None
        ):
            self.assertEqual(installer.main(), 0)

        skill_root = codex_home / "skills" / "antigravity-bridge-codex"
        plugin_root = (
            codex_home
            / "local-marketplaces"
            / "antigravity-bridge-codex"
            / "plugins"
            / "antigravity-bridge-codex"
        )
        self.assertTrue((skill_root / "SKILL.md").is_file())
        self.assertTrue((plugin_root / "SKILL.md").is_file())
        normalized_skill_manifest = json.loads((skill_root / ".mcp.json").read_text(encoding="utf-8"))
        self.assertEqual(
            normalized_skill_manifest["mcpServers"]["antigravity-bridge-codex"]["command"],
            str(Path(sys.executable).resolve()),
        )
    def test_session_parser_extracts_csrf_ports_pid(self):
        main_log = """
        argv --csrf_token 11111111-2222-3333-4444-555555555555
        Local: https://127.0.0.1:54589/
        """
        language_log = """
        started language server process with pid 9568
        listening on port at 54589 for HTTPS
        listening on port at 54590 for HTTP
        """

        session = bridge.session_from_text(main_log, language_log)

        self.assertEqual(session["csrf_token"], "11111111-2222-3333-4444-555555555555")
        self.assertEqual(session["local_url"], "https://127.0.0.1:54589/")
        self.assertEqual(session["https_port"], 54589)
        self.assertEqual(session["http_port"], 54590)
        self.assertEqual(session["process_id"], 9568)

    def test_default_mac_log_candidates_include_live_and_snapshot_paths(self):
        home = fresh_test_dir("mac-log-candidates")
        snapshot = home / "Library" / "Application Support" / "Antigravity" / "logs" / "20260630T010203"
        snapshot.mkdir(parents=True)

        candidates = bridge.default_log_path_candidates("macOS", home_directory=home)

        main_candidates = [str(path) for path in candidates["main_log_candidates"]]
        language_candidates = [str(path) for path in candidates["language_server_log_candidates"]]
        self.assertIn(str(home / "Library" / "Logs" / "Antigravity" / "main.log"), main_candidates)
        self.assertIn(str(snapshot / "main.log"), main_candidates)
        self.assertIn(str(snapshot / "ls-main.log"), language_candidates)

    def test_file_uri_conversion_supports_windows_and_posix_but_rejects_unc(self):
        self.assertEqual(
            bridge.convert_to_file_uri(r"D:\MyGame\Project A"),
            "file:///D:/MyGame/Project%20A",
        )
        self.assertEqual(
            bridge.convert_to_file_uri("/Volumes/MyGame/Project A"),
            "file:///Volumes/MyGame/Project%20A",
        )
        with self.assertRaisesRegex(RuntimeError, "UNC paths are currently not supported"):
            bridge.convert_to_file_uri(r"\\server\share\project")

    def test_latest_trajectory_extractors_read_steps_array(self):
        trajectory = {
            "steps": [
                {"type": "CORTEX_STEP_TYPE_PLANNER_RESPONSE", "plannerResponse": {"response": "old"}},
                {
                    "type": "CORTEX_STEP_TYPE_ERROR_MESSAGE",
                    "errorMessage": {"error": {"shortError": "temporary failure"}},
                },
                {"type": "CORTEX_STEP_TYPE_PLANNER_RESPONSE", "plannerResponse": {"response": "new"}},
            ]
        }

        self.assertEqual(bridge.latest_planner_response_text(trajectory), "new")
        self.assertEqual(bridge.latest_error_text(trajectory), "temporary failure")

    def test_compact_outcome_omits_raw_trajectory_by_default(self):
        outcome = {
            "cascadeId": "abc",
            "pattern": "OK",
            "matched": True,
            "timedOut": False,
            "trajectory": {"steps": [{"large": "payload"}]},
            "response": "OK",
            "failure": "",
            "observedText": "OK",
        }

        compact = bridge.compact_outcome(outcome)

        self.assertNotIn("trajectory", compact)
        self.assertEqual(compact["response"], "OK")
        self.assertEqual(compact["observedText"], "OK")

    def test_recent_model_selection_reads_model_and_enum(self):
        tmp = fresh_test_dir("recent-model-selection")
        db = tmp / "conversation.db"
        db.write_bytes(
            b"model_name gemini-2.5-pro preview data "
            b"model_enum MODEL_PLACEHOLDER_M36 "
        )
        os.utime(db, (time.time(), time.time()))

        selection = bridge.find_recent_model_selection(conversation_directory=tmp)

        self.assertEqual(selection.model_id, "gemini-2.5-pro")
        self.assertEqual(selection.model_enum, "MODEL_PLACEHOLDER_M36")

    def test_mcp_stdio_server_recovery_path(self):
        server_path = REPO_ROOT / "mcp" / "antigravity_bridge_server.py"
        home = fresh_test_dir("mcp-discover-home")
        self._write_fake_antigravity_logs(home)
        process = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._isolated_home_env(home),
        )
        try:
            process.stdin.write(b"\xff\n")
            process.stdin.flush()
            parse_error = json.loads(self._read_mcp_line(process).decode("utf-8"))
            process.stdin.write(b"[]\n")
            process.stdin.flush()
            invalid_request = json.loads(self._read_mcp_line(process).decode("utf-8"))
            initialize = self._mcp_request(process, 1, "initialize")
            tools = self._mcp_request(process, 2, "tools/list")
            discover = self._mcp_request(
                process,
                3,
                "tools/call",
                {"name": "antigravity_discover", "arguments": {"show_secret": False}},
            )
        finally:
            process.kill()
            process.communicate(timeout=5)

        self.assertEqual(parse_error["error"]["code"], -32700)
        self.assertEqual(invalid_request["error"]["code"], -32600)
        self.assertEqual(initialize["result"]["serverInfo"]["name"], "antigravity-bridge-codex")
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        self.assertIn("antigravity_discover", tool_names)
        self.assertIn("antigravity_smoke", tool_names)
        self.assertIn("antigravity_start", tool_names)
        self.assertIn("antigravity_send", tool_names)
        self.assertIn("antigravity_trajectory", tool_names)

        discover_result = json.loads(discover["result"]["content"][0]["text"])
        self.assertFalse(discover["result"]["isError"])
        self.assertEqual(discover_result["csrf_token"], "<redacted>")
        self.assertEqual(discover_result["http_port"], 54590)

    def test_mcp_tools_call_validates_request_before_discovering_session(self):
        server_path = REPO_ROOT / "mcp" / "antigravity_bridge_server.py"
        home = fresh_test_dir("mcp-no-session-home")
        process = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._isolated_home_env(home),
        )
        try:
            missing_argument = self._mcp_request(
                process,
                1,
                "tools/call",
                {"name": "antigravity_trajectory", "arguments": {}},
            )
            unknown_tool = self._mcp_request(
                process,
                2,
                "tools/call",
                {"name": "not_a_real_tool", "arguments": {}},
            )
        finally:
            process.kill()
            process.communicate(timeout=5)

        missing_argument_error = json.loads(missing_argument["result"]["content"][0]["text"])
        unknown_tool_error = json.loads(unknown_tool["result"]["content"][0]["text"])
        self.assertTrue(missing_argument["result"]["isError"])
        self.assertEqual(missing_argument_error["error"], "Missing required string argument: cascade_id")
        self.assertTrue(unknown_tool["result"]["isError"])
        self.assertEqual(unknown_tool_error["error"], "Unknown tool: not_a_real_tool")

    def _write_fake_antigravity_logs(self, home: Path) -> None:
        main_log = """
        argv --csrf_token 11111111-2222-3333-4444-555555555555
        Local: https://127.0.0.1:54589/
        """
        language_log = """
        started language server process with pid 9568
        listening on port at 54589 for HTTPS
        listening on port at 54590 for HTTP
        """
        log_directories = [
            home / "AppData" / "Roaming" / "Antigravity" / "logs",
            home / "Library" / "Logs" / "Antigravity",
        ]
        for log_directory in log_directories:
            log_directory.mkdir(parents=True)
            (log_directory / "main.log").write_text(main_log, encoding="utf-8")
            (log_directory / "language_server.log").write_text(language_log, encoding="utf-8")

    def _isolated_home_env(self, home: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
        env["APPDATA"] = str(home / "AppData" / "Roaming")
        return env

    def _read_mcp_line(self, process: subprocess.Popen, timeout_seconds: float = 5.0) -> bytes:
        import threading

        result: queue.Queue[bytes] = queue.Queue(maxsize=1)
        reader = threading.Thread(target=lambda: result.put(process.stdout.readline()), daemon=True)
        reader.start()
        try:
            line = result.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            raise AssertionError(f"MCP server did not answer within {timeout_seconds}s; exit={process.poll()}") from exc
        if not line:
            raise AssertionError("MCP server closed stdout before returning a response")
        return line

    def _mcp_request(self, process: subprocess.Popen, request_id: int, method: str, params: dict | None = None) -> dict:
        req = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            req["params"] = params
        payload = json.dumps(req, separators=(",", ":")).encode("utf-8")
        process.stdin.write(payload + b"\n")
        process.stdin.flush()

        line = self._read_mcp_line(process)
        return json.loads(line.decode("utf-8"))



class AntigravityRegressionRestorationTests(unittest.TestCase):
    """Coverage restored after the interrupted MC-003 writer replaced older tests."""

    def setUp(self):
        self.policy_patcher = patch.object(
            bridge,
            "resolve_model_policy",
            return_value=bridge.ModelPolicyResult(
                bridge.DEFAULT_AGY_MODEL,
                "default",
                "deterministic regression default",
                bridge.KNOWN_MODEL_ENUMS[bridge.DEFAULT_AGY_MODEL],
            ),
        )
        self.policy_patcher.start()
        self.addCleanup(self.policy_patcher.stop)

    def _successful_process(self, response="ok", conversation_id="conversation-1"):
        process = MagicMock()
        process.communicate.return_value = (
            json.dumps(
                {
                    "status": "SUCCESS",
                    "response": response,
                    "conversation_id": conversation_id,
                }
            ),
            "",
        )
        process.returncode = 0
        return process

    def test_mcp_prompt_success_receipt_is_not_error(self):
        server_spec = importlib.util.spec_from_file_location(
            "antigravity_mcp_success",
            REPO_ROOT / "mcp" / "antigravity_bridge_server.py",
        )
        server = importlib.util.module_from_spec(server_spec)
        server_spec.loader.exec_module(server)
        receipt = {"status": "COMPLETED", "delivery_state": "COMPLETED", "usable": True}
        with patch.object(server.bridge, "run_prompt", return_value=receipt):
            result = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "antigravity_prompt", "arguments": {"prompt": "x"}},
                }
            )
        self.assertFalse(result["result"]["isError"])

    def test_mcp_prompt_agy_error_receipt_is_error(self):
        server_spec = importlib.util.spec_from_file_location(
            "antigravity_mcp_error",
            REPO_ROOT / "mcp" / "antigravity_bridge_server.py",
        )
        server = importlib.util.module_from_spec(server_spec)
        server_spec.loader.exec_module(server)
        receipt = {"status": "ERROR", "delivery_state": "ERROR", "usable": False}
        with patch.object(server.bridge, "run_prompt", return_value=receipt):
            result = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "antigravity_prompt", "arguments": {"prompt": "x"}},
                }
            )
        self.assertTrue(result["result"]["isError"])

    def test_resolve_agy_executable_prefers_explicit_path(self):
        root = fresh_test_dir("resolve-agy-explicit")
        executable = root / "agy.exe"
        executable.write_bytes(b"")
        with patch.dict(os.environ, {"ANTIGRAVITY_AGY_PATH": str(root / "other.exe")}):
            self.assertEqual(bridge.resolve_agy_executable(str(executable)), str(executable.resolve()))

    def test_resolve_model_selection_maps_verified_default_enum(self):
        with patch.object(bridge, "find_recent_model_selection", return_value=bridge.ModelSelection()):
            selection = bridge.resolve_model_selection(bridge.DEFAULT_AGY_MODEL)
        self.assertEqual(selection.model_enum, bridge.KNOWN_MODEL_ENUMS[bridge.DEFAULT_AGY_MODEL])

    def test_send_message_emits_minimal_declarative_planner_config(self):
        selection = bridge.ModelSelection("gemini-test", "MODEL_PLACEHOLDER_M71")
        with patch.object(bridge, "resolve_model_selection", return_value=selection), patch.object(
            bridge, "invoke_rpc", return_value={}
        ) as invoke_rpc:
            bridge.send_message(
                "cascade-1",
                "hello",
                model="gemini-test",
                omit_requested_model=True,
                session=object(),
            )
            omit_body = invoke_rpc.call_args.args[1]
            self.assertNotIn("cascadeConfig", omit_body)

            bridge.send_message(
                "cascade-1",
                "hello",
                model="gemini-test",
                session=object(),
            )
            configured_body = invoke_rpc.call_args.args[1]
            planner = configured_body["cascadeConfig"]["plannerConfig"]
            self.assertEqual(planner["declarativeMixinConfig"], {})
            self.assertEqual(planner["requestedModel"]["model"], "MODEL_PLACEHOLDER_M71")
            self.assertNotIn("planModel", planner)

    def test_run_agy_prompt_nonzero_exit_is_error(self):
        root = fresh_test_dir("agy-nonzero")
        process = MagicMock()
        process.communicate.return_value = (json.dumps({"status": "ERROR", "error": "bad"}), "bad")
        process.returncode = 2
        with patch.object(bridge, "resolve_agy_executable", return_value="agy.exe"), patch.object(
            bridge.subprocess, "Popen", return_value=process
        ):
            receipt = bridge.run_agy_prompt("x", workspace_path=str(root), no_transcript=True)
        self.assertEqual(receipt["status"], "ERROR")
        self.assertEqual(receipt["exit_code"], 2)

    def test_run_agy_prompt_invalid_json_is_error(self):
        root = fresh_test_dir("agy-invalid-json")
        process = MagicMock()
        process.communicate.return_value = ("not-json", "parse failed")
        process.returncode = 0
        with patch.object(bridge, "resolve_agy_executable", return_value="agy.exe"), patch.object(
            bridge.subprocess, "Popen", return_value=process
        ):
            receipt = bridge.run_agy_prompt("x", workspace_path=str(root), no_transcript=True)
        self.assertEqual(receipt["error_code"], "invalid_agy_json")

    def test_run_agy_prompt_timeout_terminates_tree(self):
        root = fresh_test_dir("agy-timeout")
        process = MagicMock()
        process.communicate.side_effect = subprocess.TimeoutExpired("agy", 1)
        process.poll.return_value = -9
        with patch.object(bridge, "resolve_agy_executable", return_value="agy.exe"), patch.object(
            bridge.subprocess, "Popen", return_value=process
        ), patch.object(bridge, "terminate_process_tree", return_value=True) as terminate:
            receipt = bridge.run_agy_prompt(
                "x", workspace_path=str(root), timeout_seconds=1, no_transcript=True
            )
        terminate.assert_called_once_with(process)
        self.assertTrue(receipt["timed_out"])
        self.assertEqual(receipt["error_code"], "deadline_exceeded")

    def test_run_agy_prompt_success_scopes_workspace(self):
        root = fresh_test_dir("agy-success-scope")
        process = self._successful_process()
        with patch.object(bridge, "resolve_agy_executable", return_value="agy.exe"), patch.object(
            bridge.subprocess, "Popen", return_value=process
        ) as popen:
            receipt = bridge.run_agy_prompt("x", workspace_path=str(root), no_transcript=True)
        command = popen.call_args.args[0]
        self.assertEqual(receipt["status"], "SUCCESS")
        self.assertEqual(command[command.index("--add-dir") + 1], str(root.resolve()))

    def test_run_agy_prompt_project_only_for_new_conversation(self):
        root = fresh_test_dir("agy-project")
        first = self._successful_process(conversation_id="new-conversation")
        second = self._successful_process(conversation_id="existing")
        with patch.object(bridge, "resolve_agy_executable", return_value="agy.exe"), patch.object(
            bridge, "select_agy_project", return_value=("project-1", "explicit")
        ), patch.object(bridge.subprocess, "Popen", side_effect=[first, second]) as popen:
            bridge.run_agy_prompt("x", workspace_path=str(root), project_id="project-1", no_transcript=True)
            bridge.run_agy_prompt(
                "x",
                conversation_id="existing",
                workspace_path=str(root),
                project_id="project-1",
                no_transcript=True,
            )
        self.assertIn("--project", popen.call_args_list[0].args[0])
        self.assertNotIn("--project", popen.call_args_list[1].args[0])

    def test_run_agy_prompt_writes_transcript(self):
        root = fresh_test_dir("agy-transcript")
        transcript_root = root / "transcripts"
        process = self._successful_process(conversation_id="transcript-1")
        with patch.dict(os.environ, {"ANTIGRAVITY_BRIDGE_TRANSCRIPT_DIR": str(transcript_root)}), patch.object(
            bridge, "resolve_agy_executable", return_value="agy.exe"
        ), patch.object(bridge.subprocess, "Popen", return_value=process):
            receipt = bridge.run_agy_prompt("hello", workspace_path=str(root))
        self.assertTrue(Path(receipt["transcript_path"]).is_file())

    def test_run_prompt_auto_falls_back_only_after_not_sent(self):
        root = fresh_test_dir("auto-fallback-journal")
        rpc = {"usable": False, "safe_to_fallback": True, "status": "ERROR", "request_id": "r1"}
        agy = {"usable": True, "status": "SUCCESS", "conversation_id": "c1"}
        with patch.object(bridge, "run_visible_rpc_prompt", return_value=rpc), patch.object(
            bridge, "run_agy_prompt", return_value=agy
        ) as agy_prompt:
            receipt = bridge.run_prompt(
                "x",
                transport="auto",
                workspace_path=str(root),
                journal_path=str(root / "journal.sqlite3"),
            )
        agy_prompt.assert_called_once()
        self.assertTrue(receipt["fallback_used"])

    def test_run_prompt_auto_keeps_successful_rpc(self):
        rpc = {"usable": True, "safe_to_fallback": False, "status": "COMPLETED"}
        with patch.object(bridge, "run_visible_rpc_prompt", return_value=rpc), patch.object(
            bridge, "run_agy_prompt"
        ) as agy_prompt:
            receipt = bridge.run_prompt("x", transport="auto")
        agy_prompt.assert_not_called()
        self.assertIs(receipt, rpc)

    def test_wait_trajectory_outcome_surfaces_error_step(self):
        trajectory = {
            "steps": [
                {
                    "type": "CORTEX_STEP_TYPE_ERROR_MESSAGE",
                    "errorMessage": {"error": {"shortError": "Internal Error"}},
                }
            ]
        }
        with patch.object(bridge, "get_trajectory", return_value=trajectory):
            outcome = bridge.wait_trajectory_outcome(
                "cascade-error",
                r"NEVER",
                timeout_seconds=1,
                poll_interval_seconds=0.01,
                session=object(),
            )
        self.assertFalse(outcome["matched"])
        self.assertEqual(outcome["failure"], "Internal Error")


class AntigravityRequestJournalTests(unittest.TestCase):
    def setUp(self):
        bridge._GLOBAL_CIRCUIT_BREAKER.reset()
        self.model_policy_patcher = patch.object(
            bridge,
            "resolve_model_policy",
            return_value=bridge.ModelPolicyResult(
                bridge.DEFAULT_AGY_MODEL,
                "default",
                "deterministic request-journal test default",
                bridge.KNOWN_MODEL_ENUMS[bridge.DEFAULT_AGY_MODEL],
            ),
        )
        self.model_policy_patcher.start()
        self.addCleanup(self.model_policy_patcher.stop)
        self.addCleanup(bridge._GLOBAL_CIRCUIT_BREAKER.reset)

    def _rpc_mocks(self):
        return (
            patch.object(bridge, "get_session_info", return_value=object()),
            patch.object(bridge, "fetch_model_catalog", return_value=[]),
            patch.object(bridge, "new_cascade", return_value={"cascadeId": "cascade-1"}),
            patch.object(bridge, "send_message"),
            patch.object(bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}),
        )

    def test_not_sent_claim_is_atomically_reset_for_retry_but_terminal_replays(self):
        root = fresh_test_dir("request-not-sent-retry")
        journal = bridge.RequestJournal(str(root / "requests.sqlite3"))
        fingerprint = bridge.request_fingerprint("hello", "", "", str(root.resolve()), "", "")
        self.assertEqual(journal.claim("retry-key", fingerprint)["kind"], "new")
        journal.prepare_delivery("retry-key", "old-cascade", "old-marker", state="PREPARING")
        journal.finish("retry-key", {"status": "ERROR", "delivery_state": "NOT_SENT", "cascade_id": "old-cascade", "marker": "old-marker"})

        retry = journal.claim("retry-key", fingerprint)
        self.assertEqual(retry["kind"], "retry")
        self.assertEqual(retry["state"], "IN_PROGRESS")
        with journal._connect_db() as db:
            row = db.execute("SELECT state,cascade_id,marker,receipt FROM requests WHERE request_id=?", ("retry-key",)).fetchone()
        self.assertEqual(row, ("IN_PROGRESS", "", "", ""))

        journal.finish("retry-key", {"status": "COMPLETED", "delivery_state": "COMPLETED", "cascade_id": "new-cascade"})
        terminal = journal.claim("retry-key", fingerprint)
        self.assertEqual(terminal["kind"], "replay")

    def test_fresh_rpc_conversation_calls_start_cascade_once(self):
        root = fresh_test_dir("fresh-rpc-cascade")
        journal_path = str(root / "requests.sqlite3")
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cascade-fresh-1"}
        ) as new_cascade, patch.object(
            bridge, "send_message"
        ) as send_message, patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            receipt = bridge.run_visible_rpc_prompt("hello fresh", conversation_id="", journal_path=journal_path, workspace_path=str(root))

        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertEqual(new_cascade.call_count, 1)
        self.assertEqual(send_message.call_count, 1)
        self.assertFalse(send_message.call_args.kwargs.get("omit_requested_model", False))

    def test_continuation_rpc_conversation_does_not_call_start_cascade(self):
        root = fresh_test_dir("continuation-rpc-cascade")
        journal_path = str(root / "requests.sqlite3")
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade"
        ) as new_cascade, patch.object(
            bridge, "send_message"
        ) as send_message, patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            receipt = bridge.run_visible_rpc_prompt("hello turn 2", conversation_id="existing-cascade-999", journal_path=journal_path, workspace_path=str(root))

        self.assertEqual(receipt["status"], "COMPLETED")
        self.assertEqual(receipt["cascade_id"], "existing-cascade-999")
        new_cascade.assert_not_called()
        self.assertEqual(send_message.call_count, 1)
        self.assertEqual(send_message.call_args.args[0], "existing-cascade-999")
        self.assertFalse(send_message.call_args.kwargs.get("omit_requested_model", False))

    def test_turn_a_then_turn_b_cannot_return_stale_a(self):
        root = fresh_test_dir("turn-a-then-b")
        journal_path = str(root / "requests.sqlite3")
        waited_patterns = []

        def track_wait(cascade_id, pattern, session=None, deadline=None):
            waited_patterns.append(pattern)
            return {"matched": True, "timedOut": False, "response": f"response for {pattern}", "failure": ""}

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "send_message"
        ), patch.object(
            bridge, "wait_trajectory_outcome", side_effect=track_wait
        ):
            rec_a = bridge.run_visible_rpc_prompt("Turn A", conversation_id="cas-100", journal_path=journal_path, workspace_path=str(root))
            rec_b = bridge.run_visible_rpc_prompt("Turn B", conversation_id="cas-100", journal_path=journal_path, workspace_path=str(root))

        self.assertEqual(rec_a["status"], "COMPLETED")
        self.assertEqual(rec_b["status"], "COMPLETED")
        self.assertNotEqual(rec_a["marker"], rec_b["marker"])
        self.assertEqual(len(waited_patterns), 2)
        self.assertNotEqual(waited_patterns[0], waited_patterns[1])

    def test_send_timeout_does_not_fallback_to_agy(self):
        root = fresh_test_dir("send-timeout")
        journal_path = str(root / "requests.sqlite3")
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-timeout"}
        ), patch.object(
            bridge, "send_message", side_effect=TimeoutError("socket timeout after send")
        ), patch.object(
            bridge, "run_agy_prompt"
        ) as agy:
            receipt = bridge.run_prompt("hello timeout", transport="auto", journal_path=journal_path, workspace_path=str(root))

        self.assertEqual(receipt["status"], "DELIVERY_UNKNOWN")
        self.assertFalse(receipt["safe_to_fallback"])
        agy.assert_not_called()

    def test_same_request_replay_does_not_send_again(self):
        root = fresh_test_dir("replay-no-resend")
        journal_path = str(root / "requests.sqlite3")

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-replay"}
        ), patch.object(
            bridge, "send_message"
        ) as send_message, patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            rec1 = bridge.run_visible_rpc_prompt("hello replay", request_id="fixed-req-id-123", journal_path=journal_path, workspace_path=str(root))
            rec2 = bridge.run_visible_rpc_prompt("hello replay", request_id="fixed-req-id-123", journal_path=journal_path, workspace_path=str(root))

        self.assertEqual(rec1["status"], "COMPLETED")
        self.assertEqual(rec2["status"], "COMPLETED")
        self.assertTrue(rec2.get("replayed", False))
        self.assertEqual(send_message.call_count, 1)

    def test_concurrent_same_request_id_sends_once(self):
        import threading

        root = fresh_test_dir("request-concurrency")
        journal_path = str(root / "requests.sqlite3")
        barrier = threading.Barrier(2)
        send_entered = threading.Event()
        one_finished = threading.Event()
        release_send = threading.Event()
        receipts = []
        failures = []

        def blocked_send(*_args, **_kwargs):
            send_entered.set()
            self.assertTrue(release_send.wait(timeout=5))

        def observe_reconciliation(*_args, **_kwargs):
            return {"matched": True, "timedOut": False, "response": "done", "failure": ""}

        def invoke() -> None:
            try:
                barrier.wait(timeout=5)
                receipts.append(
                    bridge.run_visible_rpc_prompt(
                        "hello",
                        request_id="concurrent-key",
                        journal_path=journal_path,
                        workspace_path=str(root),
                    )
                )
                one_finished.set()
            except Exception as exc:  # pragma: no cover - assertion reported below
                failures.append(exc)

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cascade-concurrent"}
        ), patch.object(bridge, "send_message", side_effect=blocked_send) as send, patch.object(
            bridge, "wait_trajectory_outcome", side_effect=observe_reconciliation
        ):
            first = threading.Thread(target=invoke)
            second = threading.Thread(target=invoke)
            first.start()
            second.start()
            self.assertTrue(send_entered.wait(timeout=5))
            self.assertTrue(one_finished.wait(timeout=5))
            release_send.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(send.call_count, 1)
        self.assertEqual(len(receipts), 2)

    def test_same_key_replays_and_conflicts_without_second_send(self):
        root = fresh_test_dir("request-journal")
        journal = str(root / "requests.sqlite3")
        patches = self._rpc_mocks()
        with patches[0], patches[1], patches[2], patches[3] as send, patches[4]:
            first = bridge.run_visible_rpc_prompt("hello", request_id="key-1", journal_path=journal, workspace_path=str(root))
            replay = bridge.run_visible_rpc_prompt("hello", request_id="key-1", journal_path=journal, workspace_path=str(root))
            conflict = bridge.run_visible_rpc_prompt("different", request_id="key-1", journal_path=journal, workspace_path=str(root))
        self.assertEqual(first["status"], "COMPLETED")
        self.assertTrue(replay["replayed"])
        self.assertEqual(conflict["status"], "CONFLICT")
        self.assertEqual(send.call_count, 1)

    def test_pending_same_key_only_reconciles_existing_marker(self):
        root = fresh_test_dir("request-pending")
        journal_path = str(root / "requests.sqlite3")
        journal = bridge.RequestJournal(journal_path)
        journal.claim("key-2", bridge.request_fingerprint("hello", "", "", str(root.resolve()), "", ""))
        journal.prepare_delivery("key-2", "cascade-existing", "MARKER")
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(bridge, "send_message") as send, patch.object(bridge, "launch_antigravity_gui") as launch, patch.object(bridge, "wait_trajectory_outcome", return_value={"matched": False, "timedOut": True, "response": "", "failure": ""}):
            receipt = bridge.run_visible_rpc_prompt("hello", request_id="key-2", journal_path=journal_path, workspace_path=str(root), auto_launch=True)
        send.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(receipt["status"], "ACCEPTED_PENDING")
        self.assertFalse(receipt["safe_to_fallback"])

    def test_print_json_writes_utf8_even_when_text_console_is_cp950(self):
        import io
        class FakeStdout:
            encoding = "cp950"
            buffer = io.BytesIO()
        fake = FakeStdout()
        with patch.object(bridge.sys, "stdout", fake):
            bridge.print_json({"emoji": "\U0001f600"})
        self.assertEqual(json.loads(fake.buffer.getvalue().decode("utf-8"))["emoji"], "\U0001f600")

    def test_mcp_nonterminal_delivery_is_not_tool_error(self):
        server_spec = importlib.util.spec_from_file_location("antigravity_mcp_pending", REPO_ROOT / "mcp" / "antigravity_bridge_server.py")
        server = importlib.util.module_from_spec(server_spec)
        server_spec.loader.exec_module(server)
        receipt = {"status": "DELIVERY_UNKNOWN", "delivery_state": "DELIVERY_UNKNOWN", "usable": False}
        with patch.object(server.bridge, "run_prompt", return_value=receipt):
            result = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "antigravity_prompt", "arguments": {"prompt": "x"}}})
        self.assertFalse(result["result"]["isError"])

    def test_start_timeout_preserves_pre_generated_cascade_for_retry(self):
        root = fresh_test_dir("start-timeout")
        journal_path = str(root / "requests.sqlite3")
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade", side_effect=TimeoutError("start timeout")
        ) as start:
            receipt = bridge.run_visible_rpc_prompt(
                "hello", request_id="start-key", journal_path=journal_path, workspace_path=str(root)
            )
        self.assertEqual(receipt["status"], "ERROR")
        self.assertEqual(receipt["delivery_state"], "NOT_SENT")
        self.assertTrue(receipt["safe_to_fallback"])
        self.assertTrue(receipt["cascade_id"])
        self.assertEqual(start.call_args.kwargs["cascade_id"], receipt["cascade_id"])

    def test_global_deadline_skips_agy_fallback(self):
        rpc_receipt = {"usable": False, "safe_to_fallback": True, "status": "ERROR"}
        with patch.object(bridge, "run_visible_rpc_prompt", return_value=rpc_receipt), patch.object(
            bridge.time, "monotonic", side_effect=[0.0, 1.0, 1.0]
        ), patch.object(bridge, "run_agy_prompt") as agy:
            receipt = bridge.run_prompt("hello", transport="auto", timeout_seconds=1)
        agy.assert_not_called()
        self.assertEqual(receipt["fallback_skipped"], "global_deadline_exceeded")

    def test_send_timeout_after_acceptance_never_falls_back_or_resends(self):
        root = fresh_test_dir("send-after-accept")
        journal_path = str(root / "requests.sqlite3")
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cascade-accepted"}
        ), patch.object(
            bridge, "send_message", side_effect=TimeoutError("send timed out after accept")
        ) as send, patch.object(
            bridge, "run_agy_prompt"
        ) as agy:
            first = bridge.run_prompt(
                "hello",
                transport="auto",
                request_id="after-accept-key",
                journal_path=journal_path,
                workspace_path=str(root),
            )
            self.assertEqual(first["status"], "DELIVERY_UNKNOWN")
            self.assertFalse(first["safe_to_fallback"])
            self.assertEqual(send.call_count, 1)
            agy.assert_not_called()

            with patch.object(
                bridge,
                "wait_trajectory_outcome",
                return_value={"matched": True, "timedOut": False, "response": "done", "failure": ""},
            ):
                retry = bridge.run_prompt(
                    "hello",
                    transport="auto",
                    request_id="after-accept-key",
                    journal_path=journal_path,
                    workspace_path=str(root),
                )

        self.assertEqual(retry["status"], "COMPLETED")
        self.assertEqual(send.call_count, 1)
        agy.assert_not_called()

    def test_expired_deadline_never_opens_rpc_socket(self):
        session = bridge.AntigravitySession("token", "", 0, 12345, 0, "", "")
        with patch.object(bridge.time, "monotonic", return_value=10.0), patch.object(
            bridge.urllib.request, "urlopen"
        ) as urlopen:
            with self.assertRaises(TimeoutError):
                bridge.get_trajectory("cas-expired", deadline=9.0, session=session)
        urlopen.assert_not_called()

    def test_non_positive_prompt_deadline_dispatches_nothing(self):
        with patch.object(bridge, "run_visible_rpc_prompt") as rpc, patch.object(bridge, "run_agy_prompt") as agy:
            with self.assertRaises(ValueError):
                bridge.run_prompt("hello", timeout_seconds=0)
        rpc.assert_not_called()
        agy.assert_not_called()

    def test_direct_agy_receipt_keeps_request_metadata_without_exactly_once_claim(self):
        root = fresh_test_dir("direct-agy")
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (json.dumps({"status": "SUCCESS", "response": "ok", "conversation_id": "c-1"}), "")
        mock_proc.returncode = 0

        with patch.object(bridge, "resolve_agy_executable", return_value="C:\\fake\\agy.exe"), patch.object(
            bridge, "fetch_model_catalog", return_value=[]
        ), patch.object(
            bridge.subprocess, "Popen", return_value=mock_proc
        ):
            receipt = bridge.run_prompt(
                "hello agy",
                transport="agy",
                request_id="direct-req-id",
                mission_id="m-1",
                lane_id="l-1",
                workspace_path=str(root),
            )

        self.assertEqual(receipt["status"], "SUCCESS")
        self.assertEqual(receipt["request_id"], "direct-req-id")
        self.assertEqual(receipt["mission_id"], "m-1")
        self.assertEqual(receipt["lane_id"], "l-1")
        self.assertEqual(receipt["delivery_guarantee"], "best_effort_no_persistent_deduplication")

    def test_journal_redacts_common_secrets(self):
        root = fresh_test_dir("redact-secrets")
        journal_path = str(root / "requests.sqlite3")
        journal = bridge.RequestJournal(journal_path)
        secret = "secret_1234567890abcdef"
        journal.claim("redact-key", "fingerprint")
        journal.finish(
            "redact-key",
            {
                "delivery_state": "COMPLETED",
                "response": f"Authorization: Bearer {secret}",
                "error": f"csrf_token={secret}",
            },
        )
        replay = journal.claim("redact-key", "fingerprint")
        persisted = json.dumps(replay["receipt"], ensure_ascii=False)
        self.assertNotIn(secret, persisted)
        self.assertIn("<redacted>", persisted)

    def test_mcp_conflict_is_error(self):
        server_spec = importlib.util.spec_from_file_location("antigravity_mcp_conflict", REPO_ROOT / "mcp" / "antigravity_bridge_server.py")
        server = importlib.util.module_from_spec(server_spec)
        server_spec.loader.exec_module(server)
        conflict = {"status": "CONFLICT", "delivery_state": "CONFLICT", "usable": False}
        with patch.object(server.bridge, "run_prompt", return_value=conflict):
            result = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "antigravity_prompt", "arguments": {"prompt": "x"}},
                }
            )
        self.assertTrue(result["result"]["isError"])

    def test_legacy_start_and_send_auto_generate_marker_when_wait_pattern_omitted(self):
        session = bridge.AntigravitySession("token", "", 0, 12345, 0, "", "")
        with patch.object(bridge, "get_session_info", return_value=session), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-legacy-1"}
        ), patch.object(
            bridge, "send_message"
        ) as send, patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "done", "failure": ""}
        ):
            res_start = bridge.run(
                bridge.build_parser().parse_args(["start", "--opening-prompt", "hello legacy start"])
            )
            res_send = bridge.run(
                bridge.build_parser().parse_args(["send", "--cascade-id", "cas-legacy-1", "--text", "hello legacy send"])
            )

        self.assertTrue(res_start["matched"])
        self.assertTrue(res_send["matched"])
        self.assertIn("ANTIGRAVITY_BRIDGE_MARKER_", send.call_args_list[0].args[1])
        self.assertFalse(send.call_args_list[0].kwargs.get("omit_requested_model", False))
        self.assertFalse(send.call_args_list[1].kwargs.get("omit_requested_model", False))

    def test_normalize_mcp_manifest_resolves_absolute_args_and_cwd(self):
        installer = load_installer_module()
        root = fresh_test_dir("mcp-manifest-norm")
        manifest_path = root / ".mcp.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "antigravity-bridge-codex": {
                            "command": "python",
                            "args": ["./mcp/antigravity_bridge_server.py"],
                            "cwd": ".",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        installer.normalize_mcp_manifest(manifest_path)
        server = json.loads(manifest_path.read_text(encoding="utf-8"))["mcpServers"]["antigravity-bridge-codex"]
        self.assertEqual(server["command"], installer.resolve_mcp_python_command())
        self.assertTrue(Path(server["args"][0]).is_absolute())
        self.assertEqual(Path(server["args"][0]), (root / "mcp" / "antigravity_bridge_server.py").resolve())
        self.assertEqual(Path(server["cwd"]), root.resolve())


class AntigravityModelPolicyTests(unittest.TestCase):
    def test_parse_model_catalog_output_handles_leading_noise_json(self):
        noisy_json = "Noise prefix...\nProgress 50%\n" + json.dumps(
            {"command": {"data": {"models": [{"id": "gemini-3.6-pro", "label": "Gemini 3.6 Pro"}]}}}
        )
        models = bridge.parse_model_catalog_output(noisy_json)
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "gemini-3.6-pro")

    def test_parse_model_catalog_output_falls_back_to_tsv(self):
        tsv_data = "ID\tLABEL\ngemini-2.5-pro\tGemini 2.5 Pro\ngemini-2.5-flash\tGemini 2.5 Flash"
        models = bridge.parse_model_catalog_output(tsv_data)
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]["id"], "gemini-2.5-pro")

    def test_model_policy_precedence(self):
        bridge.invalidate_model_catalog_cache()
        root = fresh_test_dir("policy-precedence")

        # 1. Explicit model
        p1 = bridge.resolve_model_policy(model="gemini-3.1-pro", lane_id="main")
        self.assertEqual(p1.model_id, "gemini-3.1-pro")
        self.assertEqual(p1.source, "explicit")

        # 2. ANTIGRAVITY_MODEL env
        with patch.dict(os.environ, {"ANTIGRAVITY_MODEL": "gemini-2.5-flash"}):
            p2 = bridge.resolve_model_policy(model="", lane_id="main")
            self.assertEqual(p2.model_id, "gemini-2.5-flash")
            self.assertEqual(p2.source, "environment")

        # 3. Catalog resolution
        with patch.object(
            bridge, "fetch_model_catalog", return_value=[{"id": "gemini-2.5-pro", "label": "Pro"}]
        ), patch.object(
            bridge, "find_recent_model_selection", return_value=bridge.ModelSelection()
        ):
            p3 = bridge.resolve_model_policy(model="", lane_id="main", for_rpc=False)
            self.assertEqual(p3.model_id, "gemini-2.5-pro")
            self.assertEqual(p3.source, "catalog")

        # 4. Default fallback when catalog empty and recent empty
        with patch.object(bridge, "fetch_model_catalog", return_value=[]), patch.object(
            bridge, "find_recent_model_selection", return_value=bridge.ModelSelection()
        ):
            p4 = bridge.resolve_model_policy(model="", lane_id="main", for_rpc=False)
            self.assertEqual(p4.model_id, bridge.DEFAULT_AGY_MODEL)
            self.assertEqual(p4.source, "default")

    def test_model_policy_gemini_filtering_exclusion_ranking(self):
        catalog = [
            {"id": "gpt-4o", "label": "GPT 4o"},
            {"id": "gemini-3.1-pro-preview", "label": "Excluded Gemini 3.1 Pro"},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"id": "gemini-3.6-pro", "label": "Gemini 3.6 Pro"},
            {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash"},
        ]
        filtered = bridge.filter_and_rank_catalog_models(catalog, lane_id="main")
        ids = [m["id"] for m in filtered]
        self.assertNotIn("gpt-4o", ids)
        self.assertNotIn("gemini-3.1-pro-preview", ids)
        self.assertEqual(ids[0], "gemini-3.6-pro")

        # Flash ranking for main lane: high > medium > low
        flash_models = [
            {"id": "gemini-3.6-flash-low", "label": "Flash Low"},
            {"id": "gemini-3.6-flash-medium", "label": "Flash Medium"},
            {"id": "gemini-3.6-flash-high", "label": "Flash High"},
        ]
        main_flash = bridge.filter_and_rank_catalog_models(flash_models, lane_id="main")
        self.assertEqual(main_flash[0]["id"], "gemini-3.6-flash-high")

        # Flash ranking for worker lane: medium > high > low
        worker_flash = bridge.filter_and_rank_catalog_models(flash_models, lane_id="worker")
        self.assertEqual(worker_flash[0]["id"], "gemini-3.6-flash-medium")
        self.assertEqual(worker_flash[1]["id"], "gemini-3.6-flash-high")
        self.assertEqual(worker_flash[2]["id"], "gemini-3.6-flash-low")

    def test_model_catalog_cache_behavior_and_invalidation(self):
        bridge.invalidate_model_catalog_cache()
        call_count = [0]

        def fake_run(*args, **kwargs):
            call_count[0] += 1
            cmd = args[0]
            if "--version" in cmd:
                res = MagicMock()
                res.returncode = 0
                res.stdout = "agy 2.4.3"
                return res
            res = MagicMock()
            res.returncode = 0
            res.stdout = '{"models": [{"id": "gemini-2.5-pro", "label": "Pro"}]}'
            return res

        with patch.object(bridge, "resolve_agy_executable", return_value="C:\\fake\\agy.exe"), patch.object(
            bridge.subprocess, "run", side_effect=fake_run
        ):
            # First fetch fills cache (version check + models fetch = 2 calls)
            cat1 = bridge.fetch_model_catalog()
            self.assertEqual(len(cat1), 1)
            self.assertEqual(call_count[0], 2)

            # Second fetch uses cache without any subprocess calls
            cat2 = bridge.fetch_model_catalog()
            self.assertEqual(len(cat2), 1)
            self.assertEqual(call_count[0], 2)

            # Invalidate cache
            bridge.invalidate_model_catalog_cache()

            # Third fetch calls subprocesses again
            cat3 = bridge.fetch_model_catalog()
            self.assertEqual(len(cat3), 1)
            self.assertEqual(call_count[0], 4)

    def test_receipt_provenance_exposes_model_source_and_reason(self):
        bridge.invalidate_model_catalog_cache()
        root = fresh_test_dir("receipt-provenance")
        journal_path = str(root / "requests.sqlite3")

        # agy receipt exposing provenance
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (json.dumps({"status": "SUCCESS", "response": "ok", "conversation_id": "c-1"}), "")
        mock_proc.returncode = 0

        with patch.object(bridge, "resolve_agy_executable", return_value="C:\\fake\\agy.exe"), patch.object(
            bridge.subprocess, "Popen", return_value=mock_proc
        ), patch.object(
            bridge, "fetch_model_catalog", return_value=[{"id": "gemini-2.5-pro", "label": "Pro"}]
        ):
            rec_agy = bridge.run_agy_prompt("hello", workspace_path=str(root))
            self.assertEqual(rec_agy["model"], "gemini-2.5-pro")
            self.assertEqual(rec_agy["model_source"], "catalog")
            self.assertIn("catalog selected", rec_agy["model_reason"])

        # Visible RPC receipt explaining RPC compatibility decision when catalog model has no proven RPC enum
        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[{"id": "gemini-2.5-pro", "label": "Pro"}]
        ), patch.object(
            bridge, "find_recent_model_selection", return_value=bridge.ModelSelection()
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-prov-1"}
        ), patch.object(
            bridge, "send_message"
        ), patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            rec_rpc = bridge.run_visible_rpc_prompt("hello rpc", conversation_id="", journal_path=journal_path, workspace_path=str(root))
            self.assertEqual(rec_rpc["model"], bridge.DEFAULT_AGY_MODEL)
            self.assertEqual(rec_rpc["model_source"], "default")
            self.assertIn("RPC compatibility fallback", rec_rpc["model_reason"])

    def test_pending_request_fingerprint_stable_across_catalog_changes(self):
        bridge.invalidate_model_catalog_cache()
        root = fresh_test_dir("fingerprint-stable-catalog")
        journal_path = str(root / "requests.sqlite3")

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[{"id": "gemini-2.5-flash", "label": "Flash"}]
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-stab-1"}
        ), patch.object(
            bridge, "send_message"
        ), patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": False, "timedOut": True, "response": "", "failure": ""}
        ):
            rec1 = bridge.run_visible_rpc_prompt("test prompt", request_id="req-stab-1", journal_path=journal_path, workspace_path=str(root))
            self.assertEqual(rec1["status"], "ACCEPTED_PENDING")

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[{"id": "gemini-2.5-pro", "label": "Pro"}]
        ), patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "reconciled ok", "failure": ""}
        ):
            rec2 = bridge.run_visible_rpc_prompt("test prompt", request_id="req-stab-1", journal_path=journal_path, workspace_path=str(root))
            self.assertNotEqual(rec2["status"], "CONFLICT")
            self.assertEqual(rec2["status"], "COMPLETED")
            self.assertEqual(rec2["response"], "reconciled ok")

    def test_run_prompt_default_model_reaches_catalog(self):
        bridge.invalidate_model_catalog_cache()
        root = fresh_test_dir("run-prompt-default-catalog")
        journal_path = str(root / "requests.sqlite3")

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "fetch_model_catalog", return_value=[{"id": bridge.DEFAULT_AGY_MODEL, "label": "Verified Flash High"}]
        ) as mock_fetch, patch.object(
            bridge, "find_recent_model_selection", return_value=bridge.ModelSelection()
        ), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-def-cat"}
        ), patch.object(
            bridge, "send_message"
        ), patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            rec = bridge.run_prompt("test prompt", journal_path=journal_path, workspace_path=str(root))
            self.assertEqual(rec["status"], "COMPLETED")
            self.assertEqual(rec["model"], bridge.DEFAULT_AGY_MODEL)
            self.assertEqual(rec["model_source"], "catalog")
            self.assertTrue(mock_fetch.called)


class AntigravityHealthAndCircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        bridge._GLOBAL_CIRCUIT_BREAKER.reset()
        bridge.clear_process_ownership()

    def tearDown(self):
        bridge._GLOBAL_CIRCUIT_BREAKER.reset()
        bridge.clear_process_ownership()

    def test_circuit_breaker_state_transitions(self):
        cb = bridge.CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
        t0 = 1000.0
        self.assertEqual(cb.current_state(t0), bridge.CircuitState.CLOSED)
        self.assertTrue(cb.allow_request(t0))

        cb.record_failure("UNAVAILABLE", t0)
        cb.record_failure("UNAVAILABLE", t0 + 1)
        self.assertEqual(cb.current_state(t0 + 1), bridge.CircuitState.CLOSED)

        cb.record_failure("UNAVAILABLE", t0 + 2)
        self.assertEqual(cb.current_state(t0 + 2), bridge.CircuitState.OPEN)
        self.assertFalse(cb.allow_request(t0 + 2))

        # Before cooldown
        self.assertEqual(cb.current_state(t0 + 20), bridge.CircuitState.OPEN)

        # After cooldown
        self.assertEqual(cb.current_state(t0 + 33), bridge.CircuitState.HALF_OPEN)
        self.assertTrue(cb.allow_request(t0 + 33))

        # Trial probe succeeds
        cb.record_success(t0 + 34)
        self.assertEqual(cb.current_state(t0 + 34), bridge.CircuitState.CLOSED)

    def test_circuit_breaker_ignores_input_required_and_delivery_unknown(self):
        cb = bridge.CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
        for _ in range(5):
            cb.record_failure("INPUT_REQUIRED")
            cb.record_failure("DELIVERY_UNKNOWN")
        self.assertEqual(cb.failure_count, 0)
        self.assertEqual(cb.current_state(), bridge.CircuitState.CLOSED)

    def test_predispatch_failure_classification_is_conservative(self):
        self.assertEqual(
            bridge.classify_predispatch_failure("HTTP 403: permission required"),
            bridge.HealthState.INPUT_REQUIRED,
        )
        self.assertEqual(
            bridge.classify_predispatch_failure("connection refused"),
            bridge.HealthState.UNAVAILABLE,
        )
        self.assertEqual(
            bridge.classify_predispatch_failure("unexpected protocol shape"),
            bridge.HealthState.DEGRADED,
        )

    def test_health_assessment_states(self):
        tmp_dir = fresh_test_dir("health-assessment")
        try:
            empty_j_path = str(tmp_dir / "empty_journal.sqlite3")
            # 1. Healthy state
            mock_sess = bridge.AntigravitySession(
                csrf_token="tok",
                local_url="http://127.0.0.1:1234",
                https_port=1234,
                http_port=1235,
                process_id=99999,
                main_log_path="",
                language_server_log_path="",
            )
            with patch.object(bridge, "get_session_info", return_value=mock_sess), \
                 patch.object(bridge, "is_process_alive", return_value=True), \
                 patch.object(bridge, "invoke_rpc", return_value={}):
                res = bridge.assess_health(journal_path=empty_j_path, probe=True)
                self.assertEqual(res["status"], bridge.HealthState.HEALTHY)

            # 2. Unavailable state (session discovery fails)
            with patch.object(bridge, "get_session_info", side_effect=RuntimeError("no log")):
                res = bridge.assess_health(journal_path=empty_j_path, probe=False)
                self.assertEqual(res["status"], bridge.HealthState.UNAVAILABLE)

            # 3. Input required state (permission/auth error)
            with patch.object(bridge, "get_session_info", return_value=mock_sess), \
                 patch.object(bridge, "is_process_alive", return_value=True), \
                 patch.object(bridge, "invoke_rpc", side_effect=RuntimeError("HTTP 401: expired or is not authorized")):
                res = bridge.assess_health(journal_path=empty_j_path, probe=True)
                self.assertEqual(res["status"], bridge.HealthState.INPUT_REQUIRED)

            # 4. Delivery unknown state (journal has in-flight request)
            j_path = str(tmp_dir / "journal.sqlite3")
            j = bridge.RequestJournal(j_path)
            j.claim("req-1", "fp-1")
            j.prepare_delivery("req-1", "cas-1", "mark-1", state="DELIVERING")
            with patch.object(bridge, "get_session_info", side_effect=RuntimeError("no log")):
                res = bridge.assess_health(journal_path=j_path, probe=False)
                self.assertEqual(res["status"], bridge.HealthState.DELIVERY_UNKNOWN)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_recovery_decision_matrix(self):
        # 1. INPUT_REQUIRED -> REQUIRE_USER
        dec = bridge.assess_recovery_decision(bridge.HealthState.INPUT_REQUIRED, False)
        self.assertEqual(dec.action, "REQUIRE_USER")
        self.assertFalse(dec.allowed)

        # 2. DELIVERY_UNKNOWN -> NONE
        dec = bridge.assess_recovery_decision(bridge.HealthState.DELIVERY_UNKNOWN, True)
        self.assertEqual(dec.action, "NONE")
        self.assertFalse(dec.allowed)

        # 3. Unowned process -> REQUIRE_USER
        dec = bridge.assess_recovery_decision(bridge.HealthState.UNAVAILABLE, False, process_record=None)
        self.assertEqual(dec.action, "REQUIRE_USER")
        self.assertFalse(dec.allowed)

        # An ownership record alone is not live process revalidation.
        owned_only = bridge.ProcessOwnershipRecord(executable="/path/to/agy.exe", process_id=123, start_token="tok1")
        dec = bridge.assess_recovery_decision(
            bridge.HealthState.UNAVAILABLE,
            False,
            process_record=owned_only,
        )
        self.assertEqual(dec.action, "REQUIRE_USER")
        self.assertFalse(dec.allowed)

        # 4. Process mismatch -> REQUIRE_USER
        rec = bridge.ProcessOwnershipRecord(executable="/path/to/agy.exe", process_id=123, start_token="tok1")
        mismatched_info = {"executable": "/path/to/other.exe", "process_id": 123, "start_token": "tok1"}
        dec = bridge.assess_recovery_decision(bridge.HealthState.UNAVAILABLE, False, process_record=rec, current_process_info=mismatched_info)
        self.assertEqual(dec.action, "REQUIRE_USER")
        self.assertFalse(dec.allowed)

        # 5. Owned unavailable process -> RESTART allowed
        matched_info = {"executable": str(Path("/path/to/agy.exe").resolve()), "process_id": 123, "start_token": "tok1"}
        rec_matched = bridge.ProcessOwnershipRecord(executable=str(Path("/path/to/agy.exe").resolve()), process_id=123, start_token="tok1")
        dec = bridge.assess_recovery_decision(bridge.HealthState.UNAVAILABLE, False, process_record=rec_matched, current_process_info=matched_info)
        self.assertEqual(dec.action, "RESTART")
        self.assertTrue(dec.allowed)

    def test_execute_recovery_restart_dry_run_safety_and_revalidation(self):
        rec = bridge.ProcessOwnershipRecord(executable=str(Path("/bin/agy").resolve()), process_id=555, start_token="st-123")
        cur_info = {"executable": str(Path("/bin/agy").resolve()), "process_id": 555, "start_token": "st-123"}
        dec = bridge.assess_recovery_decision(bridge.HealthState.UNAVAILABLE, False, process_record=rec, current_process_info=cur_info)
        self.assertTrue(dec.allowed)

        # Dry run execution check
        exec_res = bridge.execute_recovery_restart(dec, process_record=rec, dry_run=True, current_process_info=cur_info)
        self.assertFalse(exec_res["executed"])
        self.assertTrue(exec_res["dry_run"])
        self.assertTrue(exec_res["allowed"])
        self.assertEqual(exec_res["action"], "RESTART")

        # Revalidation failure right before action
        changed_info = {"executable": str(Path("/bin/agy").resolve()), "process_id": 999, "start_token": "st-123"}
        exec_res_failed = bridge.execute_recovery_restart(dec, process_record=rec, dry_run=True, current_process_info=changed_info)
        self.assertFalse(exec_res_failed["allowed"])
        self.assertEqual(exec_res_failed["action"], "REQUIRE_USER")

        # Non-dry execution is deliberately unavailable and must never claim success.
        exec_res_real = bridge.execute_recovery_restart(
            dec,
            process_record=rec,
            dry_run=False,
            current_process_info=cur_info,
        )
        self.assertFalse(exec_res_real["executed"])
        self.assertFalse(exec_res_real["allowed"])
        self.assertEqual(exec_res_real["action"], "REQUIRE_USER")

    def test_predispatch_circuit_breaker_open_blocks_rpc(self):
        bridge._GLOBAL_CIRCUIT_BREAKER.state = bridge.CircuitState.OPEN
        bridge._GLOBAL_CIRCUIT_BREAKER.failure_count = 3
        bridge._GLOBAL_CIRCUIT_BREAKER.last_failure_time = time.monotonic()
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            j_path = str(tmp_dir / "journal.sqlite3")
            with patch.object(
                bridge,
                "resolve_model_policy",
                return_value=bridge.ModelPolicyResult(
                    bridge.DEFAULT_AGY_MODEL,
                    "default",
                    "circuit test",
                    bridge.KNOWN_MODEL_ENUMS[bridge.DEFAULT_AGY_MODEL],
                ),
            ):
                rec = bridge.run_visible_rpc_prompt("hello", journal_path=j_path, workspace_path=str(tmp_dir))
            self.assertEqual(rec["status"], "UNAVAILABLE")
            self.assertEqual(rec["delivery_state"], "NOT_SENT")
            self.assertTrue(rec["safe_to_fallback"])
            self.assertIn("Circuit breaker is OPEN", rec["error"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_health_cli_subcommand_is_read_only(self):
        root = fresh_test_dir("health-cli")
        journal_path = str(root / "journal.sqlite3")
        session = bridge.AntigravitySession("token", "", 0, 12345, 99999, "", "")
        with patch.object(bridge, "get_session_info", return_value=session), patch.object(
            bridge, "is_process_alive", return_value=True
        ):
            result = bridge.run(
                bridge.build_parser().parse_args(
                    ["health", "--no-probe", "--journal-path", journal_path]
                )
            )
        self.assertEqual(result["status"], bridge.HealthState.HEALTHY)
        self.assertEqual(result["recovery"]["action"], "NONE")


class AntigravityLaneCoordinationTests(unittest.TestCase):
    def setUp(self):
        bridge._GLOBAL_CIRCUIT_BREAKER.reset()
        self.policy_patcher = patch.object(
            bridge,
            "resolve_model_policy",
            return_value=bridge.ModelPolicyResult(
                bridge.DEFAULT_AGY_MODEL,
                "default",
                "deterministic lane test default",
                bridge.KNOWN_MODEL_ENUMS[bridge.DEFAULT_AGY_MODEL],
            ),
        )
        self.policy_patcher.start()
        self.addCleanup(self.policy_patcher.stop)
        self.addCleanup(bridge._GLOBAL_CIRCUIT_BREAKER.reset)

    def test_lane_lease_lifecycle_and_claim(self):
        root = fresh_test_dir("lane-lifecycle")
        journal = bridge.RequestJournal(str(root / "journal.sqlite3"))

        # Initial claim
        res1 = journal.claim_lane_lease("mission-1", "lane-A", "worker-1", lease_seconds=10.0, initial_quota=5)
        self.assertEqual(res1["kind"], "granted")
        self.assertEqual(res1["owner_id"], "worker-1")
        self.assertEqual(res1["epoch"], 1)
        self.assertEqual(res1["quota_remaining"], 5)

        # Renew lease
        res2 = journal.renew_lane_lease("mission-1", "lane-A", "worker-1", epoch=1, lease_seconds=20.0)
        self.assertEqual(res2["kind"], "renewed")

        # Release lease
        res3 = journal.release_lane_lease("mission-1", "lane-A", "worker-1", epoch=1)
        self.assertEqual(res3["kind"], "released")
        self.assertEqual(res3["lane_state"], "EXPIRED")

    def test_lane_epoch_fencing_and_competing_owners(self):
        root = fresh_test_dir("lane-fencing")
        journal = bridge.RequestJournal(str(root / "journal.sqlite3"))

        # Owner 1 claims lease
        journal.claim_lane_lease("mission-1", "lane-A", "owner-1", lease_seconds=100.0)

        # Owner 2 tries to claim same unexpired lease -> busy
        res_comp = journal.claim_lane_lease("mission-1", "lane-A", "owner-2", lease_seconds=100.0)
        self.assertEqual(res_comp["kind"], "busy")
        self.assertEqual(res_comp["lane_state"], "BUSY")

        # Owner 1 with wrong epoch -> fenced
        res_fenced = journal.renew_lane_lease("mission-1", "lane-A", "owner-1", epoch=99)
        self.assertEqual(res_fenced["kind"], "fenced")

        # High-level prompt dispatch attempt by competing owner -> LANE_BUSY, NOT_SENT
        with patch.object(bridge, "get_session_info", return_value=object()):
            rec = bridge.run_visible_rpc_prompt(
                "hello from competitor",
                journal_path=str(root / "journal.sqlite3"),
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-2",
                lane_epoch=1,
            )
            self.assertEqual(rec["status"], "LANE_BUSY")
            self.assertEqual(rec["delivery_state"], "NOT_SENT")
            self.assertFalse(rec["safe_to_fallback"])

    def test_lane_lease_expiry_takeover(self):
        root = fresh_test_dir("lane-expiry")
        journal = bridge.RequestJournal(str(root / "journal.sqlite3"))

        # Owner 1 claims lease with 0.01s expiry
        journal.claim_lane_lease("mission-1", "lane-A", "owner-1", lease_seconds=0.01)
        time.sleep(0.05)

        # Owner 2 claims expired lease -> taken_over with epoch increment
        res_takeover = journal.claim_lane_lease("mission-1", "lane-A", "owner-2", lease_seconds=10.0)
        self.assertEqual(res_takeover["kind"], "taken_over")
        self.assertEqual(res_takeover["owner_id"], "owner-2")
        self.assertEqual(res_takeover["epoch"], 2)

    def test_lane_cancellation(self):
        root = fresh_test_dir("lane-cancel")
        journal_path = str(root / "journal.sqlite3")
        journal = bridge.RequestJournal(journal_path)

        journal.claim_lane_lease("mission-1", "lane-A", "owner-1")
        journal.cancel_lane("mission-1", "lane-A")

        with patch.object(bridge, "get_session_info", return_value=object()):
            rec = bridge.run_visible_rpc_prompt(
                "hello cancelled lane",
                journal_path=journal_path,
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-1",
                lane_epoch=1,
            )
            self.assertEqual(rec["status"], "CANCELLED")
            self.assertEqual(rec["delivery_state"], "NOT_SENT")
            self.assertFalse(rec["safe_to_fallback"])
            self.assertEqual(rec["lane_state"], "CANCELLED")

    def test_lane_quota_exhaustion(self):
        root = fresh_test_dir("lane-quota")
        journal_path = str(root / "journal.sqlite3")

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-q1"}
        ), patch.object(
            bridge, "send_message"
        ), patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            # First prompt: quota=1, succeeds and consumes 1 quota (remaining 0)
            rec1 = bridge.run_visible_rpc_prompt(
                "prompt 1",
                journal_path=journal_path,
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-1",
                lane_quota=1,
            )
            self.assertEqual(rec1["status"], "COMPLETED")

            # Second prompt: quota exhausted
            rec2 = bridge.run_visible_rpc_prompt(
                "prompt 2",
                journal_path=journal_path,
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-1",
                lane_epoch=1,
            )
            self.assertEqual(rec2["status"], "QUOTA_EXCEEDED")
            self.assertEqual(rec2["delivery_state"], "NOT_SENT")
            self.assertEqual(rec2["lane_state"], "EXHAUSTED")

    def test_lane_quota_is_not_consumed_when_auto_launch_stops_before_dispatch(self):
        root = fresh_test_dir("lane-quota-auto-launch-not-sent")
        journal_path = str(root / "journal.sqlite3")
        journal = bridge.RequestJournal(journal_path)
        journal.claim_lane_lease("mission-1", "lane-A", "owner-1", initial_quota=1)
        with patch.object(
            bridge,
            "prepare_session_for_dispatch",
            return_value=(None, {"enabled": True, "attempted": True, "status": bridge.HealthState.UNAVAILABLE}),
        ):
            rec = bridge.run_visible_rpc_prompt(
                "prompt blocked before dispatch",
                request_id="quota-not-sent",
                journal_path=journal_path,
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-1",
                lane_epoch=1,
                auto_launch=True,
            )
        self.assertEqual(rec["delivery_state"], "NOT_SENT")
        with journal._connect_db() as db:
            remaining = db.execute(
                "SELECT quota_remaining FROM lane_leases WHERE mission_id=? AND lane_id=?",
                ("mission-1", "lane-A"),
            ).fetchone()[0]
        self.assertEqual(remaining, 1)

    def test_lane_replay_does_not_consume_quota_twice(self):
        root = fresh_test_dir("lane-replay-quota")
        journal_path = str(root / "journal.sqlite3")

        with patch.object(bridge, "get_session_info", return_value=object()), patch.object(
            bridge, "new_cascade", return_value={"cascadeId": "cas-q-rep"}
        ), patch.object(
            bridge, "send_message"
        ), patch.object(
            bridge, "wait_trajectory_outcome", return_value={"matched": True, "timedOut": False, "response": "ok", "failure": ""}
        ):
            # Send initial prompt with request_id="req-q-1", quota=1
            rec1 = bridge.run_visible_rpc_prompt(
                "same prompt",
                request_id="req-q-1",
                journal_path=journal_path,
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-1",
                lane_quota=1,
            )
            self.assertEqual(rec1["status"], "COMPLETED")

            # Replay same request_id -> replay does NOT consume quota or fail
            rec_replay = bridge.run_visible_rpc_prompt(
                "same prompt",
                request_id="req-q-1",
                journal_path=journal_path,
                workspace_path=str(root),
                mission_id="mission-1",
                lane_id="lane-A",
                owner_id="owner-1",
            )
            self.assertTrue(rec_replay.get("replayed"))
            self.assertEqual(rec_replay["status"], "COMPLETED")

    def test_independent_lanes_proceed_concurrently(self):
        root = fresh_test_dir("independent-lanes")
        journal_path = str(root / "journal.sqlite3")

        journal = bridge.RequestJournal(journal_path)
        resA = journal.claim_lane_lease("m-1", "lane-A", "owner-A")
        resB = journal.claim_lane_lease("m-1", "lane-B", "owner-B")

        self.assertEqual(resA["kind"], "granted")
        self.assertEqual(resB["kind"], "granted")

    def test_active_lane_requires_exact_epoch_even_for_same_owner(self):
        root = fresh_test_dir("lane-exact-epoch")
        journal = bridge.RequestJournal(str(root / "journal.sqlite3"))
        journal.claim_lane_lease("m-1", "lane-A", "owner-A")
        result = journal.authorize_lane_prompt("m-1", "lane-A", "owner-A", epoch=0)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["status"], "LANE_BUSY")

    def test_coordination_requires_mission_and_lane(self):
        root = fresh_test_dir("lane-required-identity")
        with self.assertRaisesRegex(ValueError, "mission_id and lane_id"):
            bridge.run_visible_rpc_prompt(
                "x",
                owner_id="owner-A",
                workspace_path=str(root),
                journal_path=str(root / "journal.sqlite3"),
            )

    def test_lane_denial_never_falls_back_to_agy(self):
        root = fresh_test_dir("lane-no-fallback")
        journal_path = str(root / "journal.sqlite3")
        bridge.RequestJournal(journal_path).claim_lane_lease(
            "m-1", "lane-A", "owner-A", lease_seconds=60
        )
        with patch.object(bridge, "run_agy_prompt") as agy:
            receipt = bridge.run_prompt(
                "x",
                transport="auto",
                mission_id="m-1",
                lane_id="lane-A",
                owner_id="owner-B",
                lane_epoch=1,
                workspace_path=str(root),
                journal_path=journal_path,
            )
        self.assertEqual(receipt["status"], "LANE_BUSY")
        self.assertFalse(receipt["safe_to_fallback"])
        agy.assert_not_called()

    def test_cli_lane_subcommands(self):
        root = fresh_test_dir("cli-lane")
        journal_path = str(root / "journal.sqlite3")

        # Claim
        c_res = bridge.run(
            bridge.build_parser().parse_args([
                "lane", "claim", "--mission-id", "m-1", "--lane-id", "lane-x", "--owner-id", "o-1", "--journal-path", journal_path
            ])
        )
        self.assertEqual(c_res["kind"], "granted")

        # Renew
        r_res = bridge.run(
            bridge.build_parser().parse_args([
                "lane", "renew", "--mission-id", "m-1", "--lane-id", "lane-x", "--owner-id", "o-1", "--epoch", "1", "--journal-path", journal_path
            ])
        )
        self.assertEqual(r_res["kind"], "renewed")

        # Release
        rel_res = bridge.run(
            bridge.build_parser().parse_args([
                "lane", "release", "--mission-id", "m-1", "--lane-id", "lane-x", "--owner-id", "o-1", "--epoch", "1", "--journal-path", journal_path
            ])
        )
        self.assertEqual(rel_res["kind"], "released")

        # Cancel
        can_res = bridge.run(
            bridge.build_parser().parse_args([
                "lane", "cancel", "--mission-id", "m-1", "--lane-id", "lane-x", "--journal-path", journal_path
            ])
        )
        self.assertEqual(can_res["kind"], "cancelled")


class AntigravityPermissionBoundaryTests(unittest.TestCase):
    def test_workspace_boundary_accepts_descendant_and_rejects_escape(self):
        root = fresh_test_dir("permission-workspace")
        allowed = root / "allowed"
        child = allowed / "child"
        sibling = root / "sibling"
        child.mkdir(parents=True)
        sibling.mkdir()
        with patch.dict(
            os.environ,
            {"ANTIGRAVITY_ALLOWED_WORKSPACES": str(allowed)},
            clear=False,
        ):
            self.assertEqual(bridge.validate_workspace_boundary(str(child)), str(child.resolve()))
            with self.assertRaises(PermissionError):
                bridge.validate_workspace_boundary(str(sibling))

    def test_workspace_boundary_rejects_missing_directory_before_dispatch(self):
        root = fresh_test_dir("permission-missing-workspace")
        with patch.object(bridge, "get_session_info") as discover:
            with self.assertRaisesRegex(ValueError, "existing directory"):
                bridge.run_visible_rpc_prompt(
                    "x",
                    workspace_path=str(root / "missing"),
                    journal_path=str(root / "journal.sqlite3"),
                )
        discover.assert_not_called()

    def test_permission_wait_is_input_required_and_never_fallback(self):
        outcome = {
            "matched": False,
            "timedOut": False,
            "response": "",
            "failure": "HTTP 403 permission approval required",
        }
        with patch.object(bridge, "wait_trajectory_outcome", return_value=outcome):
            receipt = bridge._reconcile_delivery(
                "cascade-1",
                "marker-1",
                time.monotonic() + 5,
                object(),
                bridge.DEFAULT_AGY_MODEL,
                str(REPO_ROOT),
                time.monotonic(),
                "request-1",
                "provided",
                "mission-1",
                "lane-1",
            )
        self.assertEqual(receipt["status"], "INPUT_REQUIRED")
        self.assertEqual(receipt["delivery_state"], "INPUT_REQUIRED")
        self.assertFalse(receipt["safe_to_fallback"])

    def test_health_reports_input_required_from_journal(self):
        root = fresh_test_dir("permission-health")
        journal_path = str(root / "journal.sqlite3")
        journal = bridge.RequestJournal(journal_path)
        journal.claim("request-1", "fingerprint")
        journal.finish(
            "request-1",
            {"status": "INPUT_REQUIRED", "delivery_state": "INPUT_REQUIRED"},
        )
        with patch.object(bridge, "get_session_info", side_effect=RuntimeError("no log")):
            result = bridge.assess_health(journal_path=journal_path, probe=False)
        self.assertEqual(result["status"], bridge.HealthState.INPUT_REQUIRED)

    def test_mcp_input_required_is_nonterminal_not_error(self):
        server_spec = importlib.util.spec_from_file_location(
            "antigravity_mcp_input_required",
            REPO_ROOT / "mcp" / "antigravity_bridge_server.py",
        )
        server = importlib.util.module_from_spec(server_spec)
        server_spec.loader.exec_module(server)
        receipt = {
            "status": "INPUT_REQUIRED",
            "delivery_state": "INPUT_REQUIRED",
            "usable": False,
        }
        with patch.object(server.bridge, "run_prompt", return_value=receipt):
            result = server.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "antigravity_prompt", "arguments": {"prompt": "x"}},
                }
            )
        self.assertFalse(result["result"]["isError"])


if __name__ == "__main__":
    unittest.main()

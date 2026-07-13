from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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

TEST_TMP_ROOT = REPO_ROOT / ".tmp" / "python-tests"


def fresh_test_dir(name: str) -> Path:
    path = TEST_TMP_ROOT / name
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


class AntigravityBridgePythonTests(unittest.TestCase):
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

    def _mcp_request(self, process: subprocess.Popen, request_id: int, method: str, params: dict | None = None) -> dict:
        req = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            req["params"] = params
        payload = json.dumps(req, separators=(",", ":")).encode("utf-8")
        process.stdin.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
        process.stdin.flush()

        headers = {}
        while True:
            line = process.stdout.readline()
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("ascii").partition(":")
            headers[key.lower()] = value.strip()
        length = int(headers["content-length"])
        return json.loads(process.stdout.read(length).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

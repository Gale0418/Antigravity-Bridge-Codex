import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "antigravity_bridge.py"

spec = importlib.util.spec_from_file_location("antigravity_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


class AntigravityBridgePythonTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
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
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "conversation.db"
            db.write_bytes(
                b"model_name gemini-2.5-pro preview data "
                b"model_enum MODEL_PLACEHOLDER_M36 "
            )
            os.utime(db, (time.time(), time.time()))

            selection = bridge.find_recent_model_selection(conversation_directory=tmp)

        self.assertEqual(selection.model_id, "gemini-2.5-pro")
        self.assertEqual(selection.model_enum, "MODEL_PLACEHOLDER_M36")


if __name__ == "__main__":
    unittest.main()

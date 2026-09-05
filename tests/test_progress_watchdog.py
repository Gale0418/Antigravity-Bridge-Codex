from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from unittest.mock import patch


def load_v2(fake_bridge):
    sys.modules["antigravity_bridge"] = fake_bridge
    spec = importlib.util.spec_from_file_location(
        "antigravity_bridge_v2", "scripts/antigravity_bridge_v2.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ProgressWatchdogTests(unittest.TestCase):
    def fake_bridge(self):
        fake = types.SimpleNamespace()
        fake.HealthState = types.SimpleNamespace(INPUT_REQUIRED="INPUT_REQUIRED")
        fake.classify_predispatch_failure = lambda _error: "ERROR"
        fake.latest_planner_response_text = lambda trajectory: trajectory.get("response", "")
        fake.latest_error_text = lambda trajectory: trajectory.get("error", "")
        fake.run_prompt = lambda *args, **kwargs: {
            "status": "ACCEPTED_PENDING",
            "delivery_state": "ACCEPTED_PENDING",
            "cascade_id": "c1",
            "safe_to_fallback": False,
        }
        fake.main = lambda argv=None: 0
        return fake

    def test_progress_refreshes_idle_watchdog(self):
        fake = self.fake_bridge()
        trajectories = iter([
            {"steps": [{"type": "SEARCH"}], "response": ""},
            {"steps": [{"type": "SEARCH"}, {"type": "TOOL"}], "response": ""},
            {"steps": [{"type": "SEARCH"}, {"type": "TOOL"}], "response": "DONE"},
        ])
        fake.get_trajectory = lambda *args, **kwargs: next(trajectories)
        module = load_v2(fake)
        clock = iter([0, 0, 0, 80, 80, 80, 160, 160, 160, 160])
        with patch.object(module.time, "monotonic", side_effect=lambda: next(clock)), patch.object(
            module.time, "sleep", return_value=None
        ):
            result = module.wait_trajectory_outcome("c1", "DONE", timeout_seconds=90, poll_interval_seconds=1)
        self.assertTrue(result["matched"])
        self.assertEqual(result["supervisorState"], "DONE")

    def test_ambiguous_delivery_never_allows_write_handoff(self):
        fake = self.fake_bridge()
        fake.get_trajectory = lambda *args, **kwargs: {"steps": [], "response": ""}
        module = load_v2(fake)
        module._SUPERVISOR_BY_CASCADE["c1"] = {"state": "STALLED", "remote_may_resume": True}
        facts = module._handoff_facts(
            {
                "delivery_state": "DELIVERY_UNKNOWN",
                "cascade_id": "c1",
                "safe_to_fallback": False,
            }
        )
        self.assertTrue(facts["may_handoff_read"])
        self.assertFalse(facts["may_handoff_write"])
        self.assertTrue(facts["remote_may_resume"])


if __name__ == "__main__":
    unittest.main()

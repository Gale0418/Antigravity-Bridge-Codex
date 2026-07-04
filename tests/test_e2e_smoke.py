#!/usr/bin/env python3
"""
Python E2E Smoke Integration Test for Antigravity Bridge.
"""

import unittest
from pathlib import Path
import sys

# Add scripts directory to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "scripts"))

from antigravity_bridge import default_log_path_candidates, get_platform

class TestE2ESmoke(unittest.TestCase):
    def test_platform_detection(self):
        platform_name = get_platform()
        self.assertIn(platform_name, ["Windows", "macOS", "Linux"])

    def test_default_log_candidates(self):
        candidates = default_log_path_candidates()
        self.assertIn("platform", candidates)
        self.assertIn("main_log_candidates", candidates)
        self.assertIn("language_server_log_candidates", candidates)
        self.assertGreater(len(candidates["main_log_candidates"]), 0)

if __name__ == "__main__":
    unittest.main()

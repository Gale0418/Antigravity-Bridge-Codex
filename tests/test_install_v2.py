from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


def load_module():
    spec = importlib.util.spec_from_file_location("install_v2", "scripts/install_v2.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallV2Tests(unittest.TestCase):
    def test_trust_capsule_is_idempotent_and_preserves_user_text(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            agents = home / "AGENTS.md"
            agents.write_text("# User rules\nKeep this.\n", encoding="utf-8")
            module.install_trust_capsule(home)
            first = agents.read_text(encoding="utf-8")
            module.install_trust_capsule(home)
            second = agents.read_text(encoding="utf-8")
            self.assertEqual(first, second)
            self.assertIn("Keep this.", second)
            self.assertEqual(second.count(module.START_MARKER), 1)
            self.assertEqual(second.count(module.END_MARKER), 1)

    def test_incomplete_managed_block_fails_closed(self):
        module = load_module()
        with self.assertRaises(RuntimeError):
            module._replace_managed_block(module.START_MARKER + "\nbroken", module.TRUST_BODY)


if __name__ == "__main__":
    unittest.main()

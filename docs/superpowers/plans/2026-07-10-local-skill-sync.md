# Local Skill Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Antigravity installer and synchronize all maintained Skill packages to local Codex locations.

**Architecture:** Validate the installation logic in a temporary `CODEX_HOME`, correct only the source-root calculation, then call existing package installers. Confirm source and installed payloads through file hashes rather than timestamps.

**Tech Stack:** Python 3, PowerShell 7, Codex local marketplace/plugin commands, unittest.

## Global Constraints

- Preserve user-owned files outside installer-declared payloads.
- Use UTF-8 for all file operations.
- Do not manually copy plugin cache directories.

---

### Task 1: Prevent Antigravity installer regressions

**Files:**
- Modify: `tests/test_antigravity_bridge_py.py`
- Modify: `scripts/install.py`

**Interfaces:**
- Consumes: `main() -> int` and `get_codex_executable(codex_home) -> Path | None` from `scripts/install.py`.
- Produces: an installer that copies `SKILL.md` to both `$CODEX_HOME/skills/antigravity-bridge-codex` and the local marketplace plugin package.

- [ ] **Step 1: Write the failing test**

```python
def test_installer_copies_skill_and_plugin_payload_to_isolated_codex_home(self):
    install_module = load_install_module()
    with patched_environment(CODEX_HOME=temporary_home), patch.object(install_module, "get_codex_executable", return_value=None):
        self.assertEqual(install_module.main(), 0)
    self.assertTrue((temporary_home / "skills" / "antigravity-bridge-codex" / "SKILL.md").exists())
    self.assertTrue((temporary_home / "local-marketplaces" / "antigravity-bridge-codex" / "plugins" / "antigravity-bridge-codex" / "SKILL.md").exists())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_antigravity_bridge_py.AntigravityBridgePythonTests.test_installer_copies_skill_and_plugin_payload_to_isolated_codex_home -v`

Expected: FAIL because the installer resolves source files beneath `scripts/`.

- [ ] **Step 3: Correct the source root**

```python
source_root = Path(__file__).resolve().parent.parent
```

- [ ] **Step 4: Run the focused test and complete Antigravity regression suite**

Run: `python -m unittest tests.test_antigravity_bridge_py -v`

Expected: all tests pass.

### Task 2: Refresh local Skill installations

**Files:**
- Runtime targets: `C:\Users\USER\.codex\skills\mission-center`
- Runtime targets: `C:\Users\USER\.codex\skills\codex-game-studios`
- Runtime targets: `C:\Users\USER\.codex\skills\antigravity-bridge-codex`

- [ ] **Step 1: Run official installers and publisher**

Run the existing Mission Center and Game Studios installers, the Mission Center local publisher, and the corrected Antigravity installer.

- [ ] **Step 2: Hash verify every declared payload item**

Run a PowerShell SHA-256 comparison between each source payload declaration and its installed destination; verify active Mission Center and Antigravity plugin cache `SKILL.md` hashes match source.

- [ ] **Step 3: Commit**

```bash
git add scripts/install.py tests/test_antigravity_bridge_py.py docs/superpowers/specs/2026-07-10-local-skill-sync-design.md docs/superpowers/plans/2026-07-10-local-skill-sync.md
git commit -m "fix: synchronize Antigravity skill installer"
```

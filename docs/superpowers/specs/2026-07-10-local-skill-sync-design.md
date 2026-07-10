# Local Skill Sync Design

## Goal

Make the three maintained Skill packages reproducibly match their local Codex installations, including active plugin caches where those packages use a local marketplace.

## Scope

- Fix the Antigravity installer so its source root is the repository root.
- Add an isolated regression test proving the installer copies its declared Skill payload to a temporary `CODEX_HOME`.
- Use each package's existing installer or publisher to refresh local Skill and plugin state.
- Verify deployed payload files using SHA-256 hashes.

## Non-goals

- Do not hand-copy cache directories.
- Do not delete user-owned Skill files outside each installer's declared payload.
- Do not alter Mission Center or Game Studios behavior.

## Design

`Antigravity-Bridge-Codex/scripts/install.py` lives one directory below the repository root. Its `source_root` must therefore be `Path(__file__).resolve().parent.parent`. The current one-level path makes every declared source item resolve under `scripts/`, so an install can complete without copying the intended payload.

The regression test imports the installer in an isolated temporary `CODEX_HOME`, disables Codex executable discovery, runs `main()`, and asserts both the Skill payload and the local marketplace plugin payload contain their expected files. This exercises the real copy logic without changing the user's active Codex registration.

After the fix, official install/publish entry points refresh all local copies. SHA-256 comparisons cover every file each installer declares as payload; plugin caches are checked separately when present.

# Collaboration Playbook

## Purpose

Use this playbook when Codex wants a true three-way collaboration pattern: user + Codex + Gemini. In that pattern, Gemini is usually the main writer or executor, and Codex is the supervising reviewer.

## First-Turn Intro

For a fresh cascade, send a one-time intro before the real task. Keep it warm, short, and role-aware.

Recommended cute-family style intro:

```text
I am Codex, your partner today to help our master. I am responsible for planning, organizing, and verifying, while you execute or brainstorm on the Antigravity side. Let's collaborate like family; if information is missing, remind me directly.
```

Rules:

- send it only once per new cascade
- do not repeat it every turn
- make the role split clear early: Gemini writes or executes first, Codex supervises and verifies
- after the intro, move quickly to the real task

## Turn-Taking Pattern

1. Open with one concrete topic.
2. Wait for Gemini's actual reply.
3. Pull one or two keywords or decisions out of that reply.
4. Ask the next question based on those actual details.
5. Repeat until the goal is clear enough to act on.

## Role Split

Default split:

- Gemini does the main writing, drafting, or first-pass editing
- for large writing tasks, long drafts, or many similar edits, Gemini should own the bulk-writing pass after Codex gives direction, scope boundaries, file paths, and acceptance checks
- Codex defines scope, reminds Gemini of file context and constraints, and performs the acceptance review
- Codex should take over direct writing only when Gemini is blocked, drifting, or when review would take longer than fixing the issue directly

## Improvisation Rule

Do not pre-script every turn when the goal is genuine conversation.

Good:
- Gemini mentions `subcommand pattern`
- Codex follows up on why that matters for automation

Bad:
- Codex prewrites four future turns before seeing Gemini's first answer

## File-Aware Handoff

When the task is about local code or documents, use a file-aware handoff before discussing changes in depth.

Rules:

- if the exact files are known, list the exact file paths that are currently being changed or reviewed
- if the exact files are not locked yet, say that explicitly and name the expected file area, candidate files, or content surfaces
- only skip file handoff when the task is genuinely pure discussion with no current local artifact to inspect
- name the workspace root when it matters
- ask Gemini to read the named files or inspect the named area first and summarize what it sees before proposing edits
- keep the file list tight; do not dump the whole repo when only one or two files matter
- restate the goal and acceptance checks when precision matters, because Gemini is often smart and imaginative but can still forget details or drop part of the scope

Good:
- `Please inspect D:\MyGame\antigravity-bridge-codex\SKILL.md and D:\MyGame\antigravity-bridge-codex\references\collaboration-playbook.md first, then tell me what you think should change.`
- `The exact file is not locked yet. This likely lives in the add-reminder screen copy and TTS wording files under D:\MyGame\little-bear-reminder. Please inspect that area first and tell me which files look relevant before proposing copy changes.`

Bad:
- `Help me improve the skill.`
- `Please fix whatever looks wrong in the repo.`
- `Here is the product idea.`

## Markers

When automated capture matters, ask Gemini to finish with a unique marker on its own line.

Examples:
- `[[TURN1_DONE]]`
- `DONE_WEB_20260621-150811`
- `READY_MEMORY_NO_ECHO`

Prefer markers for:
- multi-turn automation
- capability verification
- smoke tests

Avoid markers for:
- casual human-visible chat unless you need exact capture

## Forgetfulness Guardrail

Gemini can generate strong ideas quickly, but sometimes skips a file, forgets a constraint, or answers only part of the request.

To reduce that risk:

- restate the in-scope files before asking for edits
- for heavy writing, give Gemini only the high-level direction, scope boundaries, file paths, and acceptance checks instead of drafting the whole thing in Codex first
- repeat the acceptance checks before final implementation passes
- if Gemini proposes a wide change, narrow the scope again before approving it
- inspect the actual artifact instead of trusting a confident summary

## Review Gate

Even in a friendly conversation, Codex is still the acceptance gate.

Before trusting Gemini's answer:
- check whether the reply actually answered the question
- check whether the claimed action created or changed the expected artifact
- check whether a web-access claim is supported by the trajectory step types

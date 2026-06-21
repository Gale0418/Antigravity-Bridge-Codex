# Collaboration Playbook

## Purpose

Use this playbook when Codex wants a true three-way collaboration pattern: user + Codex + Gemini.

## First-Turn Intro

For a fresh cascade, send a one-time intro before the real task. Keep it warm, short, and role-aware.

Recommended cute-family style intro:

```text
I am Codex, your partner today to help our master. I am responsible for planning, organizing, and verifying, while you execute or brainstorm on the Antigravity side. Let's collaborate like family; if information is missing, remind me directly.
```

Rules:

- send it only once per new cascade
- do not repeat it every turn
- after the intro, move quickly to the real task

## Turn-Taking Pattern

1. Open with one concrete topic.
2. Wait for Gemini's actual reply.
3. Pull one or two keywords or decisions out of that reply.
4. Ask the next question based on those actual details.
5. Repeat until the goal is clear enough to act on.

## Improvisation Rule

Do not pre-script every turn when the goal is genuine conversation.

Good:
- Gemini mentions `subcommand pattern`
- Codex follows up on why that matters for automation

Bad:
- Codex prewrites four future turns before seeing Gemini's first answer

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

## Review Gate

Even in a friendly conversation, Codex is still the acceptance gate.

Before trusting Gemini's answer:
- check whether the reply actually answered the question
- check whether the claimed action created or changed the expected artifact
- check whether a web-access claim is supported by the trajectory step types

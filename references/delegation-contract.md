# Delegation Contract

## Purpose

Use this template whenever Codex delegates execution to Antigravity or Gemini CLI.

## Required Fields

### Goal

State one concrete outcome.

Example:
`Write a 1000-word traditional Chinese article explaining event sourcing to junior backend engineers.`

### Context

Include only the files, snippets, or facts needed to complete the task.

### Constraints

Spell out rules such as:

- preserve existing behavior
- no unrelated refactors
- use Traditional Chinese
- do not install packages
- do not run destructive commands

### Deliverables

Name the exact outputs expected:

- patch
- markdown draft
- test file
- summary
- command log

### Acceptance Checks

Write checks Codex can verify afterward.

Examples:

- article length is between 900 and 1100 words
- includes three concrete examples
- changed tests pass
- no files outside the target set were edited

### Stop Conditions

Tell the worker when to hand control back.

Examples:

- missing required tool
- test failure outside the requested scope
- ambiguity about conflicting requirements
- action would need elevated permissions

## Reusable Prompt Template

```text
You are the execution worker. Complete only the requested task.

Goal:
<one concrete outcome>

Context:
<files, snippets, facts>

Constraints:
<style, safety, scope, forbidden actions>

Deliverables:
<exact outputs expected>

Acceptance checks:
<what Codex will verify>

Stop conditions:
<when to stop and return control>

Return:
1. what you changed
2. evidence for the acceptance checks
3. open risks or uncertainties
```

## Packaging Notes

- Prefer one task packet per objective.
- If the task contains unrelated goals, split it before delegation.
- If acceptance checks are hard to write, the task is probably underspecified.

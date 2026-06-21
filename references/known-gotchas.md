# Known Gotchas

## Dynamic Session Data

Antigravity standalone app can restart and rotate all of these:

- CSRF token
- HTTPS port
- HTTP port
- language server pid

Always rediscover them from logs instead of reusing an old value.

## Required Model Field

When calling `SendUserCascadeMessage`, include:

```json
{
  "cascadeConfig": {
    "plannerConfig": {
      "requestedModel": {
        "model": "MODEL_PLACEHOLDER_M36"
      }
    }
  }
}
```

If omitted, expect:

```text
failed to construct executor: neither PlanModel nor RequestedModel specified. You must specify a valid model.
```

## New Trajectory Shape

Do not trust the old top-level `plannerResponse` or `failure` fields.

Read the current reply from the last step of type:
- `CORTEX_STEP_TYPE_PLANNER_RESPONSE`

Read the current error from the last step of type:
- `CORTEX_STEP_TYPE_ERROR_MESSAGE`

## Web Access Verification

A file containing a URL is not enough to prove real browsing.

For strong evidence, confirm the trajectory includes:
- `CORTEX_STEP_TYPE_SEARCH_WEB`

## UI Visibility

Background RPC success does not imply the Antigravity chat window will visibly open. The local language server can process a cascade entirely in the background.

## Workspace Binding

If the task should operate inside a specific folder, start the cascade with `workspaceUris`. Otherwise Gemini may still reply, but it will have weaker local context.

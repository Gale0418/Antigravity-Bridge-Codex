# Fast Streaming Event & Trajectory Monitoring Protocol

Guidelines for monitoring low-latency cascades and token streaming across the Antigravity Bridge.

## Trajectory Polling Optimization

1. **Compact Step Trajectory**:
   - Querying full conversation trajectories can return massive payloads.
   - Use `Wait-AntigravityTrajectoryMatch -Pattern 'MARKER'` to poll specifically for completion flags rather than pulling full step logs on every tick.
2. **Streaming Event Hooks**:
   - Trajectory steps of type `CORTEX_STEP_TYPE_PLANNER_RESPONSE` stream chunks incrementally in Antigravity.
   - When inspecting step replies, filter `trajectory.steps[]` by
     `CORTEX_STEP_TYPE_PLANNER_RESPONSE` and select the newest matching step;
     the final array element can be an unrelated event or error.
3. **Loopback WebSockets / RPC Gateway**:
   - Maintain `httpPort` and `httpsPort` from session discovery (`Get-AntigravitySessionInfo`).
   - If an RPC request times out, verify if Antigravity is waiting for a local UI prompt before resetting the cascade connection.

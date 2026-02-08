# Agent Step Sequencer State Schema

Minimal schema for persisted state. Survives gateway resets mid-step.

## Fields

| Field | Type | Description |
|-------|------|--------------|
| `plan` | object | Step definitions. `plan.steps`: object keyed by stepId, each `{ title, instruction }` |
| `stepQueue` | string[] | Ordered step IDs |
| `currentStep` | number | Index/cursor into stepQueue |
| `stepRuns` | object | Keyed by stepId. Each value: `{ status, tries, lastRunIso, error? }` |
| `stepDelayMinutes` | number | 0 = no delay between steps; 2 = 2 min delay. Default 0. |
| `blockers` | string[] | If stuck (optional) |
| `lastHeartbeatIso` | string | ISO timestamp when last check ran |
| `artifacts` | string[] | Paths to files created—for final summary |
| `status` | string | `IN_PROGRESS` or `DONE` (no active task) |

## Example

```json
{
  "plan": {
    "steps": {
      "step-1": {
        "title": "Research topic X",
        "instruction": "Research topic X and produce a concise summary"
      },
      "step-2": {
        "title": "Write research paper",
        "instruction": "Using the summary from step 1, write a research paper..."
      }
    }
  },
  "stepQueue": ["step-1", "step-2"],
  "currentStep": 0,
  "stepRuns": {
    "step-1": { "status": "DONE", "tries": 1, "lastRunIso": "2025-02-07T12:00:00Z" }
  },
  "stepDelayMinutes": 0,
  "blockers": [],
  "lastHeartbeatIso": "2025-02-07T13:00:00Z",
  "artifacts": ["/path/to/file1.txt"],
  "status": "IN_PROGRESS"
}
```

## Status Values

- `IN_PROGRESS`: step runner currently executing or queued
- `DONE`: step completed
- `FAILED`: step failed (runner marks this); `error` field used for troubleshoot prompt
- No active task: `status` = DONE → heartbeat does nothing

---
name: agent-step-sequencer
description: Multi-step scheduler for in-depth agent requests. Detects when user needs multiple steps, suggests plan and waits for confirmation, persists state, and runs heartbeat-aware flow. Use when requests have 3+ actions, sequential dependencies, output dependencies, or high scope/risk.
---

# Agent Step Sequencer

Multi-step scheduler for in-depth requests. Enables step-based actions with heartbeat integration—survives gateway reset mid-step.

## Core Pattern

1. **Interpret** when user request requires multiple steps
2. **Suggest** step plan, wait for confirmation
3. **Persist** state.json (with plan format)
4. **Agent invokes** `scripts/step-sequencer-check.py` immediately (no wait for heartbeat)
5. **Heartbeat** (e.g. every 5 min) also invokes the script—keeps sequencer aligned with email jobs and other heartbeat tasks

**Critical:** If gateway resets mid-step, next heartbeat reads state and resumes correctly.

---

## Plan Format

Agent builds a plan when user approves. During approval, agent asks: **Use 2-minute delay between steps?** Recommended for rate-limit–sensitive API calls. User chooses; agent sets `stepDelayMinutes` (0 or 2) in state. Each step has `title` and `instruction`:

```json
{
  "plan": {
    "steps": {
      "step-1": { "title": "Research topic X", "instruction": "Research topic X and produce a concise summary" },
      "step-2": { "title": "Write paper", "instruction": "Using the summary from step 1, write a research paper..." }
    }
  },
  "stepQueue": ["step-1", "step-2"],
  "currentStep": 0,
  "stepRuns": {},
  "stepDelayMinutes": 0,
  "status": "IN_PROGRESS"
}
```

- **title**: Human-readable label
- **instruction**: Full instruction for the agent (research, summarize, pull X from Y, etc.)

---

## Roles

- **Agent**: Builds plan, persists state; does not touch state during step execution. Takes prompts.
- **Runner** (`step-sequencer-runner.py`): Invokes agent with step instruction, waits for exit, marks DONE/FAILED. Applies stepDelayMinutes. On retry, agent gets troubleshoot prompt.
- **Check script** (`step-sequencer-check.py`): If work to do, invokes runner. Handles FAILED → retry (reset PENDING, invoke runner).
- **Heartbeat**: Invokes check script on schedule.

---

## How Agent Determines Multi-Step

**Agent must suggest before proceeding.** When MULTI_STEP, propose the step plan and wait for confirmation before executing.

```
MULTI_STEP =
  (action_count >= 3)
  OR has_sequential_language
  OR has_output_dependency
  OR high_scope_or_risk
  OR user_requests_steps
  OR contains_setup_keywords

SINGLE_STEP =
  (action_count == 1)
  AND NOT has_output_dependency
  AND immediate_execution

DECISION =
  IF MULTI_STEP THEN suggest_multi_step → wait for confirm → proceed
  ELSE single_step
```

**Definitions:**

| Criterion | Meaning |
|-----------|---------|
| `action_count` | Number of distinct actions (file edits, commands, etc.) |
| `has_sequential_language` | "then", "after", "first...then", "step 1" |
| `has_output_dependency` | Step B needs output from step A |
| `high_scope_or_risk` | Many files, destructive ops, migration |
| `user_requests_steps` | "step by step", "break this down", "one at a time" |
| `contains_setup_keywords` | "set up", "migrate", "implement from scratch", "full X", "complete Y" |

---

## State Schema

See [references/state-schema.md](references/state-schema.md). Key fields:

- `plan.steps`: step definitions (`title`, `instruction`)
- `stepQueue`, `currentStep`, `stepRuns`
- `stepDelayMinutes`: 0 = no delay; 2 = 2 min between steps
- `blockers`, `lastHeartbeatIso`, `artifacts`

---

## Heartbeat Flow

Heartbeat invokes `scripts/step-sequencer-check.py`. Agent also invokes it right after persisting state.

1. Read state.json
2. If no state or status=DONE → do nothing
3. If step FAILED → bump tries, reset to PENDING, invoke runner (immediate retry)
4. If step DONE → advance currentStep, invoke runner
5. If step PENDING or IN_PROGRESS → invoke runner
6. Update lastHeartbeatIso

Runner invokes agent (configurable via `STEP_AGENT_CMD`). Runner applies stepDelayMinutes.

---

## Failure Flow

1. Runner marks step FAILED, stores error in stepRuns
2. Runner invokes check script immediately (no heartbeat wait)
3. Check script bumps tries, resets status to PENDING, invokes runner
4. Runner invokes agent with troubleshoot prompt: "Step X failed (tries: N). Previous run ended with: [error]. Please troubleshoot and retry: [instruction]"
5. Repeats until DONE or max retries / blockers

---

## Flow Diagrams

### Check script → Runner

```mermaid
flowchart TD
    A[Heartbeat or Agent] --> B[step-sequencer-check.py]
    B --> C{Work to do?}
    C -->|No| D[Do nothing]
    C -->|Yes| E[Invoke runner]
    E --> F[step-sequencer-runner.py]
    F --> G[Invoke agent with instruction]
    G --> H{Agent exit}
    H -->|Success| I[Mark DONE]
    H -->|Fail| J[Mark FAILED, invoke check script]
    I --> K[Check advances or done]
    J --> B
```

### User flow (propose + persist)

```mermaid
flowchart TD
    U[User Request] --> V{Complex enough?}
    V -->|No| W[Execute directly]
    V -->|Yes| X[Propose step plan]
    X --> Y[User confirms]
    Y --> Z[Persist state.json with plan]
    Z --> AA[Agent invokes step-sequencer-check]
    AA --> AB[Runner invokes agent - step 1]
    AB --> AC[Heartbeat also invokes on schedule]
```

---

## Configuration

| Env | Description |
|-----|-------------|
| `STEP_AGENT_CMD` | Command to invoke agent (space-separated). Prompt appended as last arg. Default: `echo` |
| `STEP_RUNNER` | Path to step-sequencer-runner.py (optional) |
| `STEP_MAX_RETRIES` | Max retries on FAILED before adding to blockers. Default: 3 |

OpenClaw: Wire `STEP_AGENT_CMD` to OpenClaw's agent invocation (e.g. `openclaw ask`).

---

## Final Deliverables Step

When all steps complete:

- Confirm all requirements of the steps are met
- Produce summary with links or paths to any files created/written
- Mark state DONE → on subsequent heartbeats, scheduler does nothing

---

## Installation

```bash
clawhub install agent-step-sequencer
```

Manual copy:

```bash
cp -r agent-step-sequencer ~/.openclaw/skills/agent-step-sequencer
```

Wire heartbeat to invoke `scripts/step-sequencer-check.py`. Agent should invoke it immediately after persisting state.

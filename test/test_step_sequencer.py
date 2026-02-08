#!/usr/bin/env python3
"""
Automated tests for agent-step-sequencer check and runner.
Uses echo/false as agent commands for deterministic behavior.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add scripts to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
CHECK = SCRIPTS_DIR / "step-sequencer-check.py"
RUNNER = SCRIPTS_DIR / "step-sequencer-runner.py"


def run_check(state_path: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    env = env or os.environ.copy()
    return subprocess.run(
        [sys.executable, str(CHECK), str(state_path)],
        cwd=state_path.parent,
        env=env,
        capture_output=True,
        text=True,
    )


def load_state(state_path: Path) -> dict:
    with open(state_path) as f:
        return json.load(f)


def test_basic_flow_two_steps():
    """Check invokes runner, step 1 runs, then step 2, then DONE."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state = {
            "plan": {
                "steps": {
                    "step-1": {"title": "First", "instruction": "one"},
                    "step-2": {"title": "Second", "instruction": "two"},
                }
            },
            "stepQueue": ["step-1", "step-2"],
            "currentStep": 0,
            "stepRuns": {},
            "stepDelayMinutes": 0,
            "status": "IN_PROGRESS",
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        env = os.environ.copy()
        env["STEP_AGENT_CMD"] = "echo"

        # Run 1: execute step 1
        run_check(state_path, env)
        s = load_state(state_path)
        assert s["stepRuns"]["step-1"]["status"] == "DONE"
        assert s["currentStep"] == 0  # check hasn't advanced yet

        # Run 2: advance, execute step 2
        run_check(state_path, env)
        s = load_state(state_path)
        assert s["currentStep"] == 1
        assert s["stepRuns"]["step-2"]["status"] == "DONE"

        # Run 3: advance past step 2, runner no-op
        run_check(state_path, env)
        s = load_state(state_path)
        assert s["currentStep"] == 2

        # Run 4: detect all done, set status DONE
        run_check(state_path, env)
        s = load_state(state_path)
        assert s["status"] == "DONE"

    print("test_basic_flow_two_steps: OK")


def test_failure_marks_failed():
    """Agent returns non-zero -> step marked FAILED, error stored."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state = {
            "plan": {"steps": {"step-1": {"title": "Fail", "instruction": "x"}}},
            "stepQueue": ["step-1"],
            "currentStep": 0,
            "stepRuns": {},
            "stepDelayMinutes": 0,
            "status": "IN_PROGRESS",
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        env = os.environ.copy()
        env["STEP_AGENT_CMD"] = "false"  # always fails

        run_check(state_path, env)
        s = load_state(state_path)
        assert s["stepRuns"]["step-1"]["status"] == "FAILED"
        assert "error" in s["stepRuns"]["step-1"]

    print("test_failure_marks_failed: OK")


def test_retry_stops_at_max_retries():
    """On FAILED, retries until STEP_MAX_RETRIES, then adds to blockers."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state = {
            "plan": {"steps": {"step-1": {"title": "Fail", "instruction": "x"}}},
            "stepQueue": ["step-1"],
            "currentStep": 0,
            "stepRuns": {},
            "stepDelayMinutes": 0,
            "status": "IN_PROGRESS",
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        env = os.environ.copy()
        env["STEP_AGENT_CMD"] = "false"
        env["STEP_MAX_RETRIES"] = "2"

        run_check(state_path, env)
        s = load_state(state_path)
        assert s["stepRuns"]["step-1"]["status"] == "FAILED"
        assert s["stepRuns"]["step-1"]["tries"] >= 2
        assert "blockers" in s
        assert any("step-1" in b for b in s["blockers"])

    print("test_retry_stops_at_max_retries: OK")


def test_recovery_mid_flow():
    """State with step 1 DONE, step 2 PENDING -> runner picks up step 2."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state = {
            "plan": {
                "steps": {
                    "step-1": {"title": "Done", "instruction": "a"},
                    "step-2": {"title": "Next", "instruction": "b"},
                }
            },
            "stepQueue": ["step-1", "step-2"],
            "currentStep": 0,
            "stepRuns": {"step-1": {"status": "DONE", "tries": 1, "lastRunIso": "2025-01-01T00:00:00Z"}},
            "stepDelayMinutes": 0,
            "status": "IN_PROGRESS",
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        env = os.environ.copy()
        env["STEP_AGENT_CMD"] = "echo"

        run_check(state_path, env)
        s = load_state(state_path)
        assert s["currentStep"] == 1
        assert s["stepRuns"]["step-2"]["status"] == "DONE"

        run_check(state_path, env)  # advance past step 2
        run_check(state_path, env)  # set status DONE
        s = load_state(state_path)
        assert s["status"] == "DONE"

    print("test_recovery_mid_flow: OK")


def test_no_state_does_nothing():
    """No state file -> check exits 0, does nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "nonexistent.json"
        r = run_check(state_path)
        assert r.returncode == 0

    print("test_no_state_does_nothing: OK")


def test_done_state_does_nothing():
    """status=DONE -> check does nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state = {
            "plan": {"steps": {}},
            "stepQueue": [],
            "currentStep": 0,
            "stepRuns": {},
            "status": "DONE",
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        run_check(state_path)
        s = load_state(state_path)
        assert s["status"] == "DONE"

    print("test_done_state_does_nothing: OK")


def main():
    tests = [
        test_no_state_does_nothing,
        test_done_state_does_nothing,
        test_basic_flow_two_steps,
        test_failure_marks_failed,
        test_retry_stops_at_max_retries,
        test_recovery_mid_flow,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:
            failed.append((t.__name__, e))
            print(f"{t.__name__}: FAIL - {e}")

    if failed:
        print(f"\n{len(failed)}/{len(tests)} tests failed")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed")
    sys.exit(0)


if __name__ == "__main__":
    main()

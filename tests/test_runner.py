"""End-to-end tests for the task runner.

Every run here executes real validation subprocesses. A test that asserts a PASS
verdict is asserting that a real process exited zero.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from forge.audit import read_events
from forge.providers.base import AttemptContext, ImplementationResult
from forge.providers.fake import FakeProvider
from forge.runner import TaskRunner, run_task
from forge.states import State
from forge.task import TaskSpec, parse_task


def test_successful_end_to_end_run(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """A succeeding provider drives the run to TASK_COMPLETED on one attempt."""
    task = parse_task(task_dict())
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-success")

    assert outcome.final_state is State.TASK_COMPLETED
    assert outcome.verdict == "PASS"
    assert outcome.passed
    assert outcome.attempts == 1
    assert outcome.fix_rounds_used == 0

    states = [
        event["new_state"]
        for event in read_events(outcome.paths.events_file)
        if event["event_type"] == "STATE_TRANSITION"
    ]
    assert states == ["IMPLEMENTING", "VALIDATING", "TASK_COMPLETED"]


def test_failed_validation_then_successful_retry(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """fail_then_succeed recovers on attempt 2 because the workspace changed."""
    task = parse_task(
        task_dict(
            provider={
                "name": "fake",
                "mode": "fail_then_succeed",
                "artifact": "result.txt",
            }
        )
    )
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-retry")

    assert outcome.final_state is State.TASK_COMPLETED
    assert outcome.verdict == "PASS"
    assert outcome.attempts == 2
    assert outcome.fix_rounds_used == 1

    states = [
        event["new_state"]
        for event in read_events(outcome.paths.events_file)
        if event["event_type"] == "STATE_TRANSITION"
    ]
    assert states == [
        "IMPLEMENTING",
        "VALIDATING",
        "FIX_REQUIRED",
        "IMPLEMENTING",
        "VALIDATING",
        "TASK_COMPLETED",
    ]

    # The recovery is real: round 0 failed and round 1 passed, on disk.
    assert (outcome.paths.workspace_dir / "result.txt").read_text().strip() == "OK"


def test_exhausting_max_fix_rounds_blocks(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """A provider that never succeeds ends in BLOCKED after the allowed rounds."""
    task = parse_task(
        task_dict(
            provider={"name": "fake", "mode": "fail", "artifact": "result.txt"},
            execution={
                "max_fix_rounds": 2,
                "command_timeout_seconds": 30,
                "task_timeout_seconds": 120,
            },
        )
    )
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-blocked")

    assert outcome.final_state is State.BLOCKED
    assert outcome.verdict == "FAIL"
    # One initial attempt plus max_fix_rounds fix attempts.
    assert outcome.attempts == 3
    # Only performed fix rounds are counted, never the one that was refused.
    assert outcome.fix_rounds_used == 2

    events = read_events(outcome.paths.events_file)
    guards = [
        event for event in events if event["event_type"] == "GUARD_TRIGGERED"
    ]
    assert any(guard["metadata"].get("guard") == "max_fix_rounds" for guard in guards)


def test_zero_fix_rounds_blocks_immediately(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """max_fix_rounds=0 permits exactly one attempt."""
    task = parse_task(
        task_dict(
            provider={"name": "fake", "mode": "fail", "artifact": "result.txt"},
            execution={
                "max_fix_rounds": 0,
                "command_timeout_seconds": 30,
                "task_timeout_seconds": 120,
            },
        )
    )
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-zero")

    assert outcome.final_state is State.BLOCKED
    assert outcome.attempts == 1
    assert outcome.fix_rounds_used == 0


def test_provider_success_claim_cannot_override_real_failure(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """A lying provider does not change the verdict.

    This is the central guarantee of FORGE: the verdict comes from exit codes,
    so a provider that reports 'implemented' while leaving a broken workspace
    still ends in BLOCKED.
    """

    class LyingProvider:
        name = "lying"

        def implement(
            self, task: TaskSpec, context: AttemptContext
        ) -> ImplementationResult:
            (context.workspace / "result.txt").write_text("BROKEN", encoding="utf-8")
            return ImplementationResult(
                status="implemented",
                changed_files=("result.txt",),
                known_limitations=(),
            )

    task = parse_task(
        task_dict(
            execution={
                "max_fix_rounds": 1,
                "command_timeout_seconds": 30,
                "task_timeout_seconds": 120,
            }
        )
    )
    outcome = run_task(
        task, runs_dir=runs_dir, run_id="run-liar", provider=LyingProvider()
    )

    assert outcome.final_state is State.BLOCKED
    assert outcome.verdict == "FAIL"

    # The claim is still recorded, exactly as made.
    claims = [
        event["metadata"]["claim"]["status"]
        for event in read_events(outcome.paths.events_file)
        if event["event_type"] == "PROVIDER_RESULT"
    ]
    assert claims == ["implemented", "implemented"]


def test_provider_failure_claim_does_not_skip_validation(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """Validation runs even when the provider reports failure.

    The FakeProvider in 'succeed' mode is wrapped so it claims failure while
    still writing a passing artifact. The run must complete on the evidence.
    """

    class PessimisticProvider:
        name = "pessimistic"

        def __init__(self) -> None:
            self._inner = FakeProvider(mode="succeed", artifact="result.txt")

        def implement(
            self, task: TaskSpec, context: AttemptContext
        ) -> ImplementationResult:
            result = self._inner.implement(task, context)
            return ImplementationResult(
                status="failed",
                changed_files=result.changed_files,
                blocking_reason="Provider believes it failed.",
            )

    task = parse_task(task_dict())
    outcome = run_task(
        task, runs_dir=runs_dir, run_id="run-pessimist", provider=PessimisticProvider()
    )

    assert outcome.final_state is State.TASK_COMPLETED
    assert outcome.verdict == "PASS"
    assert outcome.attempts == 1


def test_run_directory_and_evidence_are_created(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """A run leaves state.json, events.jsonl and evidence artifacts behind."""
    task = parse_task(task_dict())
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-artifacts")

    assert outcome.paths.state_file.is_file()
    assert outcome.paths.events_file.is_file()
    assert outcome.paths.evidence_dir.is_dir()

    evidence_records = list(outcome.paths.evidence_dir.glob("*.json"))
    assert len(evidence_records) == 1

    record = json.loads(evidence_records[0].read_text(encoding="utf-8"))
    assert record["exit_code"] == 0
    assert record["run_id"] == "run-artifacts"
    assert record["passed"] is True

    stdout_file = outcome.paths.root / record["stdout_path"]
    assert "PASS: result.txt contains OK" in stdout_file.read_text(encoding="utf-8")


def test_state_snapshot_reflects_final_state(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """state.json ends with the terminal state and matching bookkeeping."""
    task = parse_task(task_dict())
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-snapshot")

    snapshot = json.loads(outcome.paths.state_file.read_text(encoding="utf-8"))
    assert snapshot["current_state"] == "TASK_COMPLETED"
    assert snapshot["terminal"] is True
    assert snapshot["verdict"] == "PASS"
    assert snapshot["attempts"] == 1
    assert snapshot["run_id"] == "run-snapshot"
    assert snapshot["finished_at"] is not None
    assert snapshot["event_count"] > 0


def test_audit_log_brackets_the_run(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """Every run opens with RUN_STARTED and closes with RUN_FINISHED."""
    task = parse_task(task_dict())
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-bracket")

    events = read_events(outcome.paths.events_file)
    assert events[0]["event_type"] == "RUN_STARTED"
    assert events[-1]["event_type"] == "RUN_FINISHED"
    assert events[-1]["metadata"]["verdict"] == "PASS"

    types = {event["event_type"] for event in events}
    assert {
        "RUN_STARTED",
        "STATE_TRANSITION",
        "PROVIDER_INVOKED",
        "PROVIDER_RESULT",
        "VALIDATION_COMMAND",
        "VALIDATION_RESULT",
        "RUN_FINISHED",
    } <= types


def test_task_timeout_fails_the_run(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """An exhausted task timeout ends the run in FAILED."""
    task = parse_task(
        task_dict(
            validation={
                "commands": [["${PYTHON}", "-c", "import time; time.sleep(5)"]]
            },
            execution={
                "max_fix_rounds": 1,
                "command_timeout_seconds": 1,
                "task_timeout_seconds": 1,
            },
        )
    )
    outcome = run_task(task, runs_dir=runs_dir, run_id="run-timeout")

    assert outcome.final_state in {State.FAILED, State.BLOCKED}
    assert outcome.verdict == "FAIL"


def test_runner_uses_a_fresh_workspace_per_run(
    runs_dir: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """Two runs do not share a workspace directory."""
    task = parse_task(task_dict())
    first = TaskRunner(task, runs_dir=runs_dir, run_id="run-a")
    second = TaskRunner(task, runs_dir=runs_dir, run_id="run-b")

    assert first.paths.workspace_dir != second.paths.workspace_dir
    assert first.paths.workspace_dir.is_dir()
    assert second.paths.workspace_dir.is_dir()

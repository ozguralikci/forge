"""Tests for the validation engine.

These tests launch real subprocesses. That is the point: the verdict must come
from a real exit code, so the engine is never tested against a mocked one.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from forge.audit import RunPaths
from forge.validation import ValidationEngine


def build_engine(runs_dir: Path, run_id: str = "run-test", timeout: int = 30):
    """Build an engine wired to a fresh run directory."""
    paths = RunPaths.create(runs_dir, run_id)
    return ValidationEngine(
        paths=paths, run_id=run_id, command_timeout_seconds=timeout
    ), paths


def test_passing_command_produces_evidence(runs_dir: Path) -> None:
    """A real zero-exit command is recorded as passing, with artifacts on disk."""
    engine, paths = build_engine(runs_dir)
    command = [sys.executable, "-c", "print('hello from validation')"]

    result = engine.run([command], round_index=0)

    assert result.passed
    assert len(result.commands) == 1

    evidence = result.commands[0]
    assert evidence.exit_code == 0
    assert evidence.timed_out is False
    assert evidence.passed
    assert evidence.duration_seconds >= 0
    assert evidence.started_at and evidence.ended_at
    assert evidence.run_id == "run-test"

    stdout_file = paths.root / evidence.stdout_path
    assert stdout_file.is_file()
    assert "hello from validation" in stdout_file.read_text(encoding="utf-8")

    record_files = list(paths.evidence_dir.glob("*.json"))
    assert len(record_files) == 1
    record = json.loads(record_files[0].read_text(encoding="utf-8"))
    assert record["exit_code"] == 0
    assert record["passed"] is True
    assert record["command"] == command


def test_failing_command_records_real_exit_code(runs_dir: Path) -> None:
    """A non-zero exit is captured verbatim, together with its stderr."""
    engine, paths = build_engine(runs_dir)
    command = [sys.executable, "-c", "import sys; sys.exit('deliberate failure')"]

    result = engine.run([command], round_index=0)

    assert not result.passed
    evidence = result.commands[0]
    assert evidence.exit_code == 1
    assert not evidence.passed

    stderr_file = paths.root / evidence.stderr_path
    assert "deliberate failure" in stderr_file.read_text(encoding="utf-8")


def test_specific_exit_code_is_preserved(runs_dir: Path) -> None:
    """The engine records the actual exit code, not a normalized boolean."""
    engine, _ = build_engine(runs_dir)
    command = [sys.executable, "-c", "import sys; sys.exit(42)"]

    result = engine.run([command], round_index=0)

    assert result.commands[0].exit_code == 42
    assert not result.passed


def test_validation_stops_at_first_failure(runs_dir: Path) -> None:
    """Later commands are not run once one has failed."""
    engine, _ = build_engine(runs_dir)
    commands = [
        [sys.executable, "-c", "import sys; sys.exit(3)"],
        [sys.executable, "-c", "print('should not run')"],
    ]

    result = engine.run(commands, round_index=0)

    assert not result.passed
    assert len(result.commands) == 1
    assert result.first_failure is not None
    assert result.first_failure.exit_code == 3


def test_all_commands_must_pass(runs_dir: Path) -> None:
    """A round passes only when every declared command exits zero."""
    engine, _ = build_engine(runs_dir)
    commands = [
        [sys.executable, "-c", "print('first')"],
        [sys.executable, "-c", "print('second')"],
    ]

    result = engine.run(commands, round_index=0)

    assert result.passed
    assert len(result.commands) == 2
    assert result.first_failure is None


def test_timeout_is_enforced_and_recorded(runs_dir: Path) -> None:
    """A command that overruns its timeout fails and is marked as timed out."""
    engine, _ = build_engine(runs_dir, timeout=1)
    command = [sys.executable, "-c", "import time; time.sleep(30)"]

    result = engine.run([command], round_index=0)

    assert not result.passed
    evidence = result.commands[0]
    assert evidence.timed_out is True
    assert evidence.exit_code is None
    assert evidence.launch_error is not None
    assert "timed out" in evidence.launch_error.lower()


def test_unlaunchable_command_fails_without_crashing(runs_dir: Path) -> None:
    """A command that cannot start is recorded as a failure, not an exception."""
    engine, _ = build_engine(runs_dir)

    result = engine.run([["forge-no-such-executable-xyz"]], round_index=0)

    assert not result.passed
    evidence = result.commands[0]
    assert evidence.launch_error is not None
    assert not evidence.passed


def test_commands_run_inside_the_workspace(runs_dir: Path) -> None:
    """Validation commands execute with the workspace as their working dir."""
    engine, paths = build_engine(runs_dir)
    (paths.workspace_dir / "marker.txt").write_text("present", encoding="utf-8")
    command = [
        sys.executable,
        "-c",
        "import pathlib, sys; sys.exit(0 if pathlib.Path('marker.txt').is_file() "
        "else 1)",
    ]

    result = engine.run([command], round_index=0)

    assert result.passed


def test_command_is_not_launched_when_the_budget_is_gone(runs_dir: Path) -> None:
    """With no task time left, the command is recorded as timed out, unlaunched."""
    engine, paths = build_engine(runs_dir)
    marker = paths.workspace_dir / "launched.txt"
    command = [
        sys.executable,
        "-c",
        "import pathlib; pathlib.Path('launched.txt').write_text('ran')",
    ]

    result = engine.run(
        [command], round_index=0, task_time_remaining=lambda: 0.0
    )

    assert not result.passed
    evidence = result.commands[0]
    assert evidence.timed_out is True
    assert evidence.exit_code is None
    assert evidence.duration_seconds == 0.0
    assert evidence.launch_error is not None
    assert "not launched" in evidence.launch_error

    # The proof that it never ran: the command's side effect is absent.
    assert not marker.exists()

    # Evidence artifacts are still written, in the usual shape.
    assert (paths.root / evidence.stdout_path).is_file()
    assert (paths.root / evidence.stderr_path).is_file()
    assert len(list(paths.evidence_dir.glob("*.json"))) == 1


def test_budget_is_shared_across_commands_in_a_round(runs_dir: Path) -> None:
    """The whole round shares one budget; commands cannot each consume it.

    Three commands sleep 0.6s each under a 1.0s task budget and a much larger
    per-command timeout. If the remaining budget were recomputed only once, all
    three would be granted ~1.0s, all would pass, and the round would run for
    ~1.8s - overrunning the deadline. Sharing the budget stops it early.
    """
    engine, _ = build_engine(runs_dir, timeout=30)
    deadline = time.monotonic() + 1.0
    sleeper = [sys.executable, "-c", "import time; time.sleep(0.6)"]

    started = time.monotonic()
    result = engine.run(
        [sleeper, sleeper, sleeper],
        round_index=0,
        task_time_remaining=lambda: deadline - time.monotonic(),
    )
    elapsed = time.monotonic() - started

    assert not result.passed, "the round must not pass by overrunning the budget"
    assert len(result.commands) < 3, "the round must stop before running every command"
    assert result.commands[-1].timed_out is True
    # Generous bound: the unfixed behaviour takes ~1.8s+, the fixed one ~1.0s.
    assert elapsed < 1.6, f"round overran the shared budget ({elapsed:.2f}s)"


def test_per_command_timeout_still_applies_under_a_large_budget(
    runs_dir: Path,
) -> None:
    """The command timeout is the binding limit when task time is plentiful."""
    engine, _ = build_engine(runs_dir, timeout=1)
    command = [sys.executable, "-c", "import time; time.sleep(30)"]

    result = engine.run(
        [command], round_index=0, task_time_remaining=lambda: 3600.0
    )

    assert not result.passed
    assert result.commands[0].timed_out is True


def test_rounds_write_separate_evidence_files(runs_dir: Path) -> None:
    """Evidence from one round never overwrites evidence from another."""
    engine, paths = build_engine(runs_dir)
    command = [sys.executable, "-c", "print('round output')"]

    engine.run([command], round_index=0)
    engine.run([command], round_index=1)

    records = sorted(path.name for path in paths.evidence_dir.glob("*.json"))
    assert len(records) == 2
    assert records[0].startswith("round-00")
    assert records[1].startswith("round-01")

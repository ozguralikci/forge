"""Tests for the run directory layout and the append-only audit log."""

from __future__ import annotations

import json
from pathlib import Path

from forge.audit import AuditLog, EventType, RunPaths, read_events, write_state_snapshot
from forge.states import State

REQUIRED_EVENT_FIELDS = {
    "event_id",
    "run_id",
    "timestamp",
    "event_type",
    "previous_state",
    "new_state",
    "message",
    "metadata",
}


def test_run_directory_layout_is_created(runs_dir: Path) -> None:
    """Creating run paths makes the evidence and workspace directories."""
    paths = RunPaths.create(runs_dir, "run-layout")

    assert paths.root == runs_dir / "run-layout"
    assert paths.evidence_dir.is_dir()
    assert paths.workspace_dir.is_dir()
    assert paths.state_file == paths.root / "state.json"
    assert paths.events_file == paths.root / "events.jsonl"


def test_events_carry_every_required_field(runs_dir: Path) -> None:
    """Each logged event has the full documented field set."""
    paths = RunPaths.create(runs_dir, "run-fields")
    log = AuditLog(paths.events_file, "run-fields")

    log.append(
        event_type=EventType.STATE_TRANSITION,
        previous_state=State.TASK_READY,
        new_state=State.IMPLEMENTING,
        message="Starting attempt 1.",
        metadata={"attempt": 1},
    )

    events = read_events(paths.events_file)
    assert len(events) == 1

    event = events[0]
    assert REQUIRED_EVENT_FIELDS.issubset(event.keys())
    assert event["run_id"] == "run-fields"
    assert event["event_type"] == "STATE_TRANSITION"
    assert event["previous_state"] == "TASK_READY"
    assert event["new_state"] == "IMPLEMENTING"
    assert event["message"] == "Starting attempt 1."
    assert event["metadata"] == {"attempt": 1}


def test_event_ids_are_sequential(runs_dir: Path) -> None:
    """Event ids increase monotonically within a run."""
    paths = RunPaths.create(runs_dir, "run-seq")
    log = AuditLog(paths.events_file, "run-seq")

    for _ in range(3):
        log.append(
            event_type=EventType.PROVIDER_INVOKED,
            previous_state=State.IMPLEMENTING,
            new_state=State.IMPLEMENTING,
        )

    ids = [event["event_id"] for event in read_events(paths.events_file)]
    assert ids == ["run-seq-0001", "run-seq-0002", "run-seq-0003"]
    assert log.event_count == 3


def test_log_is_append_only(runs_dir: Path) -> None:
    """Existing lines are never rewritten or truncated by later appends."""
    paths = RunPaths.create(runs_dir, "run-append")
    log = AuditLog(paths.events_file, "run-append")

    log.append(EventType.RUN_STARTED, State.TASK_READY, State.TASK_READY, "first")
    first_snapshot = paths.events_file.read_text(encoding="utf-8")

    log.append(EventType.RUN_FINISHED, State.TASK_READY, State.TASK_READY, "second")
    second_snapshot = paths.events_file.read_text(encoding="utf-8")

    assert second_snapshot.startswith(first_snapshot)
    assert len(second_snapshot) > len(first_snapshot)


def test_each_line_is_standalone_json(runs_dir: Path) -> None:
    """The log is valid JSON Lines, so it can be streamed and tailed."""
    paths = RunPaths.create(runs_dir, "run-jsonl")
    log = AuditLog(paths.events_file, "run-jsonl")

    log.append(EventType.RUN_STARTED, State.TASK_READY, State.TASK_READY, "a")
    log.append(EventType.RUN_FINISHED, State.TASK_READY, State.TASK_READY, "b")

    lines = paths.events_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        assert json.loads(line)["run_id"] == "run-jsonl"


def test_state_snapshot_is_rewritten(runs_dir: Path) -> None:
    """state.json reflects the latest snapshot rather than accumulating."""
    paths = RunPaths.create(runs_dir, "run-snapshot")

    write_state_snapshot(paths.state_file, {"current_state": "IMPLEMENTING"})
    write_state_snapshot(paths.state_file, {"current_state": "TASK_COMPLETED"})

    snapshot = json.loads(paths.state_file.read_text(encoding="utf-8"))
    assert snapshot == {"current_state": "TASK_COMPLETED"}


def test_read_events_on_missing_file_returns_empty(tmp_path: Path) -> None:
    """Reading a log that does not exist yields an empty list, not an error."""
    assert read_events(tmp_path / "absent.jsonl") == []

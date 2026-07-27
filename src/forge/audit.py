"""Run directories, the append-only audit log, and the state snapshot.

``events.jsonl`` is only ever opened in append mode, one JSON object per line.
The file is never rewritten or truncated during a run, so the sequence of events
is the authoritative record of what happened.

``state.json`` is the opposite: a small snapshot of the current position,
rewritten after every transition so an interrupted run can still be inspected.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from forge.common import utc_now_iso
from forge.states import State


class EventType:
    """Audit event types emitted by FORGE v0.1."""

    RUN_STARTED = "RUN_STARTED"
    STATE_TRANSITION = "STATE_TRANSITION"
    PROVIDER_INVOKED = "PROVIDER_INVOKED"
    PROVIDER_RESULT = "PROVIDER_RESULT"
    VALIDATION_COMMAND = "VALIDATION_COMMAND"
    VALIDATION_RESULT = "VALIDATION_RESULT"
    GUARD_TRIGGERED = "GUARD_TRIGGERED"
    RUN_FINISHED = "RUN_FINISHED"


@dataclass(frozen=True)
class Event:
    """One line of the audit log.

    ``previous_state`` and ``new_state`` are always populated. For events that
    are not transitions both carry the state the run was in at the time, so
    every event can be placed on the timeline without consulting its neighbours.
    """

    event_id: str
    run_id: str
    timestamp: str
    event_type: str
    previous_state: str
    new_state: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the event as a plain JSON-serializable dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class RunPaths:
    """The filesystem layout of a single run."""

    root: Path
    state_file: Path
    events_file: Path
    evidence_dir: Path
    workspace_dir: Path

    @classmethod
    def create(cls, runs_dir: str | Path, run_id: str) -> "RunPaths":
        """Create ``runs/<run_id>/`` and its subdirectories."""
        root = Path(runs_dir) / run_id
        paths = cls(
            root=root,
            state_file=root / "state.json",
            events_file=root / "events.jsonl",
            evidence_dir=root / "evidence",
            workspace_dir=root / "workspace",
        )
        paths.evidence_dir.mkdir(parents=True, exist_ok=True)
        paths.workspace_dir.mkdir(parents=True, exist_ok=True)
        return paths


class AuditLog:
    """Append-only writer for ``events.jsonl``.

    The file is reopened in append mode for every event. That costs a syscall
    per line and buys two things worth more at this size: nothing is buffered
    when the process dies, and no long-lived handle keeps the run directory
    locked on Windows.
    """

    def __init__(self, events_file: Path, run_id: str) -> None:
        self._events_file = Path(events_file)
        self._run_id = run_id
        self._sequence = 0
        self._events_file.parent.mkdir(parents=True, exist_ok=True)
        self._events_file.touch(exist_ok=True)

    @property
    def path(self) -> Path:
        """Location of the audit log file."""
        return self._events_file

    @property
    def event_count(self) -> int:
        """How many events this log has written."""
        return self._sequence

    def append(
        self,
        event_type: str,
        previous_state: State,
        new_state: State,
        message: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> Event:
        """Append one event and return it."""
        self._sequence += 1
        event = Event(
            event_id=f"{self._run_id}-{self._sequence:04d}",
            run_id=self._run_id,
            timestamp=utc_now_iso(),
            event_type=event_type,
            previous_state=str(previous_state),
            new_state=str(new_state),
            message=message,
            metadata=dict(metadata or {}),
        )
        line = json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True)
        with self._events_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return event


def read_events(events_file: str | Path) -> list[dict[str, Any]]:
    """Read an audit log back into a list of dictionaries."""
    path = Path(events_file)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def write_state_snapshot(state_file: str | Path, snapshot: Mapping[str, Any]) -> None:
    """Write ``state.json``, replacing any previous snapshot."""
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(snapshot), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

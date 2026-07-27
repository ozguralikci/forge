"""The independent validation engine.

This module is the reason FORGE exists. It runs the commands declared in the
task specification, records exactly what happened, and derives PASS or FAIL from
the resulting exit codes alone. It never receives the provider's self-report, so
it cannot be influenced by an agent's claims.

Commands run without a shell. A command that exits non-zero, times out, or
cannot be started at all counts as a failure.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from forge.audit import RunPaths
from forge.common import utc_now_iso

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

#: Sentinel exit code recorded when a command could not be started at all.
LAUNCH_FAILURE_EXIT_CODE = -1

#: Recorded when the task budget ran out before a command could be launched.
TASK_BUDGET_EXHAUSTED_MESSAGE = (
    "Task time budget exhausted before this command started; "
    "the command was not launched."
)


def _slugify(command: Sequence[str]) -> str:
    """Build a short filesystem-safe label from a command's executable name."""
    head = Path(command[0]).name if command else "command"
    slug = _SLUG_PATTERN.sub("-", head.lower()).strip("-")
    return slug[:32] or "command"


@dataclass(frozen=True)
class CommandEvidence:
    """The recorded outcome of one validation command."""

    run_id: str
    round_index: int
    index: int
    command: tuple[str, ...]
    exit_code: Optional[int]
    timed_out: bool
    started_at: str
    ended_at: str
    duration_seconds: float
    stdout_path: str
    stderr_path: str
    stdout_bytes: int
    stderr_bytes: int
    launch_error: Optional[str] = None

    @property
    def passed(self) -> bool:
        """True only when the process exited zero without timing out."""
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        """Return the evidence record as a JSON-serializable dictionary."""
        return {
            "run_id": self.run_id,
            "round_index": self.round_index,
            "index": self.index,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "launch_error": self.launch_error,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class ValidationResult:
    """The outcome of one validation round."""

    round_index: int
    commands: tuple[CommandEvidence, ...]
    passed: bool

    @property
    def first_failure(self) -> Optional[CommandEvidence]:
        """The first command that failed, if any."""
        for evidence in self.commands:
            if not evidence.passed:
                return evidence
        return None


class ValidationEngine:
    """Runs declared validation commands and writes evidence artifacts."""

    def __init__(
        self,
        paths: RunPaths,
        run_id: str,
        command_timeout_seconds: int,
        on_command: Optional[Callable[[CommandEvidence], None]] = None,
    ) -> None:
        self._paths = paths
        self._run_id = run_id
        self._command_timeout = command_timeout_seconds
        self._on_command = on_command

    def run(
        self,
        commands: Sequence[Sequence[str]],
        round_index: int,
        cwd: Optional[Path] = None,
        task_time_remaining: Optional[Callable[[], float]] = None,
    ) -> ValidationResult:
        """Run every command in order, stopping at the first failure.

        Stopping early keeps the evidence readable: once a command fails, the
        output of later commands describes a workspace that is already broken.

        ``task_time_remaining`` is a callback returning the seconds left in the
        overall task budget. It is deliberately a callback rather than a number:
        it is re-evaluated immediately before every command, so the budget is
        shared across the whole round. Passing a single precomputed number would
        let each of N commands consume the full remaining budget, allowing a
        round to overrun the task deadline by a factor of N.
        """
        workdir = Path(cwd) if cwd is not None else self._paths.workspace_dir
        workdir.mkdir(parents=True, exist_ok=True)

        collected: list[CommandEvidence] = []
        for index, command in enumerate(commands):
            timeout = float(self._command_timeout)

            if task_time_remaining is not None:
                remaining = task_time_remaining()
                if remaining <= 0:
                    # The budget is gone. Record deterministic timeout evidence
                    # and stop without launching this command at all.
                    evidence = self._budget_exhausted_evidence(
                        command=tuple(command),
                        round_index=round_index,
                        index=index,
                    )
                    collected.append(evidence)
                    if self._on_command is not None:
                        self._on_command(evidence)
                    break
                # Never grant more than the smaller of the two limits.
                timeout = min(timeout, remaining)

            evidence = self._run_one(
                command=tuple(command),
                round_index=round_index,
                index=index,
                workdir=workdir,
                timeout=timeout,
            )
            collected.append(evidence)
            if self._on_command is not None:
                self._on_command(evidence)
            if not evidence.passed:
                break

        return ValidationResult(
            round_index=round_index,
            commands=tuple(collected),
            passed=bool(collected) and all(item.passed for item in collected),
        )

    def _evidence_files(
        self, command: tuple[str, ...], round_index: int, index: int
    ) -> tuple[Path, Path, Path]:
        """Return the stdout, stderr and record paths for one command."""
        prefix = f"round-{round_index:02d}-cmd-{index:02d}-{_slugify(command)}"
        return (
            self._paths.evidence_dir / f"{prefix}.stdout.txt",
            self._paths.evidence_dir / f"{prefix}.stderr.txt",
            self._paths.evidence_dir / f"{prefix}.json",
        )

    def _budget_exhausted_evidence(
        self, command: tuple[str, ...], round_index: int, index: int
    ) -> CommandEvidence:
        """Record a command that was never launched because time ran out.

        The evidence is shaped exactly like a real timeout so downstream code
        needs no special case: ``timed_out`` is true and ``exit_code`` is None,
        so the command - and therefore the round - counts as failed.
        """
        stdout_file, stderr_file, record_file = self._evidence_files(
            command, round_index, index
        )
        timestamp = utc_now_iso()
        launch_error = TASK_BUDGET_EXHAUSTED_MESSAGE

        stdout_file.write_text("", encoding="utf-8")
        stderr_file.write_text(launch_error, encoding="utf-8")

        evidence = CommandEvidence(
            run_id=self._run_id,
            round_index=round_index,
            index=index,
            command=command,
            exit_code=None,
            timed_out=True,
            started_at=timestamp,
            ended_at=timestamp,
            duration_seconds=0.0,
            stdout_path=str(stdout_file.relative_to(self._paths.root)),
            stderr_path=str(stderr_file.relative_to(self._paths.root)),
            stdout_bytes=0,
            stderr_bytes=len(launch_error.encode("utf-8")),
            launch_error=launch_error,
        )
        self._persist(evidence, record_file)
        return evidence

    def _persist(self, evidence: CommandEvidence, record_file: Path) -> None:
        """Write the JSON evidence record for one command."""
        record_file.write_text(
            json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )

    def _run_one(
        self,
        command: tuple[str, ...],
        round_index: int,
        index: int,
        workdir: Path,
        timeout: float,
    ) -> CommandEvidence:
        stdout_file, stderr_file, record_file = self._evidence_files(
            command, round_index, index
        )

        started_at = utc_now_iso()
        monotonic_start = time.monotonic()
        timed_out = False
        launch_error: Optional[str] = None
        exit_code: Optional[int]
        stdout_text = ""
        stderr_text = ""

        try:
            completed = subprocess.run(
                list(command),
                cwd=str(workdir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
                check=False,
            )
            exit_code = completed.returncode
            stdout_text = completed.stdout or ""
            stderr_text = completed.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = None
            stdout_text = _as_text(exc.stdout)
            stderr_text = _as_text(exc.stderr)
            launch_error = f"Command timed out after {timeout:.1f}s."
        except OSError as exc:
            exit_code = LAUNCH_FAILURE_EXIT_CODE
            launch_error = f"Command could not be started: {exc}"
            stderr_text = launch_error

        duration = time.monotonic() - monotonic_start
        ended_at = utc_now_iso()

        stdout_file.write_text(stdout_text, encoding="utf-8")
        stderr_file.write_text(stderr_text, encoding="utf-8")

        evidence = CommandEvidence(
            run_id=self._run_id,
            round_index=round_index,
            index=index,
            command=command,
            exit_code=exit_code,
            timed_out=timed_out,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=round(duration, 6),
            stdout_path=str(stdout_file.relative_to(self._paths.root)),
            stderr_path=str(stderr_file.relative_to(self._paths.root)),
            stdout_bytes=len(stdout_text.encode("utf-8")),
            stderr_bytes=len(stderr_text.encode("utf-8")),
            launch_error=launch_error,
        )
        self._persist(evidence, record_file)
        return evidence


def _as_text(value: Any) -> str:
    """Decode partial subprocess output captured on timeout."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)

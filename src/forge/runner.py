"""The task runner: the loop that ties every other module together.

    TASK_READY -> IMPLEMENTING -> VALIDATING -> TASK_COMPLETED
                       ^              |
                       |              v
                       +------- FIX_REQUIRED -> BLOCKED (fix rounds exhausted)

Two properties of this loop matter more than the loop itself:

1. Validation runs after every attempt, including attempts the provider itself
   reports as failed. The provider's claim is recorded and then ignored; only
   exit codes decide the verdict.
2. Every transition is written to the append-only audit log before the next step
   begins, so an interrupted run still explains itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from forge.audit import AuditLog, EventType, RunPaths, write_state_snapshot
from forge.common import generate_run_id, utc_now_iso
from forge.errors import ForgeError
from forge.providers import build_provider
from forge.providers.base import AttemptContext, ImplementationResult, Provider
from forge.states import TERMINAL_STATES, State, StateMachine
from forge.task import TaskSpec
from forge.validation import CommandEvidence, ValidationEngine, ValidationResult

#: Verdict strings written to state.json.
VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"


@dataclass(frozen=True)
class RunOutcome:
    """The result of a completed run."""

    run_id: str
    task_id: str
    final_state: State
    verdict: str
    attempts: int
    fix_rounds_used: int
    paths: RunPaths
    last_validation: Optional[ValidationResult]
    message: str

    @property
    def passed(self) -> bool:
        """True only when the run finished in TASK_COMPLETED."""
        return self.final_state is State.TASK_COMPLETED


class TaskRunner:
    """Executes one task specification, start to finish."""

    def __init__(
        self,
        task: TaskSpec,
        runs_dir: str | Path,
        run_id: Optional[str] = None,
        provider: Optional[Provider] = None,
    ) -> None:
        self.task = task
        self.run_id = run_id or generate_run_id()
        self.paths = RunPaths.create(runs_dir, self.run_id)
        self.audit = AuditLog(self.paths.events_file, self.run_id)
        self.provider: Provider = provider or build_provider(task.provider)
        self.machine = StateMachine(
            initial=State.TASK_READY, on_transition=self._on_transition
        )
        self.attempts = 0
        self.fix_rounds_used = 0
        self.started_at = utc_now_iso()
        self.finished_at: Optional[str] = None
        self._deadline: Optional[float] = None
        self._verdict: Optional[str] = None
        self._engine = ValidationEngine(
            paths=self.paths,
            run_id=self.run_id,
            command_timeout_seconds=task.limits.command_timeout_seconds,
            on_command=self._on_validation_command,
        )

    # ------------------------------------------------------------------
    # audit plumbing
    # ------------------------------------------------------------------

    def _on_transition(
        self,
        previous: State,
        new: State,
        message: str,
        metadata: Mapping[str, Any],
    ) -> None:
        self.audit.append(
            event_type=EventType.STATE_TRANSITION,
            previous_state=previous,
            new_state=new,
            message=message,
            metadata=metadata,
        )
        self._write_snapshot()

    def _on_validation_command(self, evidence: CommandEvidence) -> None:
        outcome = "passed" if evidence.passed else "failed"
        self.audit.append(
            event_type=EventType.VALIDATION_COMMAND,
            previous_state=self.machine.state,
            new_state=self.machine.state,
            message=f"Validation command {evidence.index} {outcome}.",
            metadata=evidence.to_dict(),
        )

    def _write_snapshot(self) -> None:
        state = self.machine.state
        write_state_snapshot(
            self.paths.state_file,
            {
                "run_id": self.run_id,
                "task_id": self.task.task_id,
                "project_id": self.task.project_id,
                "current_state": str(state),
                "terminal": state in TERMINAL_STATES,
                "attempts": self.attempts,
                "fix_rounds_used": self.fix_rounds_used,
                "max_fix_rounds": self.task.limits.max_fix_rounds,
                "verdict": self._verdict,
                "started_at": self.started_at,
                "updated_at": utc_now_iso(),
                "finished_at": self.finished_at,
                "event_count": self.audit.event_count,
                "provider": self.provider.name,
            },
        )

    # ------------------------------------------------------------------
    # timeout helpers
    # ------------------------------------------------------------------

    def _remaining_seconds(self) -> float:
        if self._deadline is None:
            return float(self.task.limits.task_timeout_seconds)
        return self._deadline - time.monotonic()

    def _abort_if_out_of_time(self) -> bool:
        """Move to FAILED when the task timeout has been exhausted."""
        if self._remaining_seconds() > 0:
            return False
        self.audit.append(
            event_type=EventType.GUARD_TRIGGERED,
            previous_state=self.machine.state,
            new_state=self.machine.state,
            message="Task timeout exceeded.",
            metadata={"task_timeout_seconds": self.task.limits.task_timeout_seconds},
        )
        self.machine.transition(
            State.FAILED,
            message=(
                f"Task timeout of {self.task.limits.task_timeout_seconds}s exceeded."
            ),
            metadata={"guard": "task_timeout"},
        )
        return True

    # ------------------------------------------------------------------
    # the loop
    # ------------------------------------------------------------------

    def run(self) -> RunOutcome:
        """Execute the task and return its outcome."""
        self._deadline = time.monotonic() + self.task.limits.task_timeout_seconds
        self.audit.append(
            event_type=EventType.RUN_STARTED,
            previous_state=State.TASK_READY,
            new_state=State.TASK_READY,
            message=f"Run started for task {self.task.task_id}.",
            metadata={
                "task_id": self.task.task_id,
                "project_id": self.task.project_id,
                "title": self.task.title,
                "risk_level": self.task.risk_level,
                "provider": self.provider.name,
                "max_fix_rounds": self.task.limits.max_fix_rounds,
                "task_timeout_seconds": self.task.limits.task_timeout_seconds,
                "command_timeout_seconds": self.task.limits.command_timeout_seconds,
                "validation_command_count": len(self.task.validation_commands),
                "source_path": (
                    str(self.task.source_path) if self.task.source_path else None
                ),
            },
        )
        self._write_snapshot()

        last_validation: Optional[ValidationResult] = None
        message = ""

        try:
            while True:
                if self._abort_if_out_of_time():
                    message = "Task timeout exceeded."
                    break

                self.machine.transition(
                    State.IMPLEMENTING,
                    message=f"Starting attempt {self.attempts + 1}.",
                    metadata={"attempt": self.attempts + 1},
                )
                result = self._implement()

                self.machine.transition(
                    State.VALIDATING,
                    message="Running declared validation commands.",
                    metadata={
                        "attempt": self.attempts,
                        "provider_claim": result.status,
                        "note": "Provider claim is recorded, not trusted.",
                    },
                )
                last_validation = self._validate()

                if last_validation.passed:
                    self._verdict = VERDICT_PASS
                    message = "All validation commands exited zero."
                    self.machine.transition(
                        State.TASK_COMPLETED,
                        message=message,
                        metadata={"attempts": self.attempts},
                    )
                    break

                failure = last_validation.first_failure
                self.machine.transition(
                    State.FIX_REQUIRED,
                    message="Validation failed.",
                    metadata={
                        "attempt": self.attempts,
                        "failed_command": list(failure.command) if failure else [],
                        "exit_code": failure.exit_code if failure else None,
                        "timed_out": failure.timed_out if failure else False,
                    },
                )

                # Check before incrementing, so fix_rounds_used only ever counts
                # fix rounds that were actually performed.
                if self.fix_rounds_used >= self.task.limits.max_fix_rounds:
                    self._verdict = VERDICT_FAIL
                    message = (
                        f"Exhausted max_fix_rounds "
                        f"({self.task.limits.max_fix_rounds})."
                    )
                    self.audit.append(
                        event_type=EventType.GUARD_TRIGGERED,
                        previous_state=self.machine.state,
                        new_state=self.machine.state,
                        message=message,
                        metadata={
                            "guard": "max_fix_rounds",
                            "max_fix_rounds": self.task.limits.max_fix_rounds,
                            "fix_rounds_used": self.fix_rounds_used,
                        },
                    )
                    self.machine.transition(
                        State.BLOCKED,
                        message=message,
                        metadata={"attempts": self.attempts},
                    )
                    break

                self.fix_rounds_used += 1

        except KeyboardInterrupt:
            message = "Run cancelled by the operator."
            self._verdict = VERDICT_FAIL
            if not self.machine.is_terminal:
                self.machine.transition(State.CANCELLED, message=message)
        except ForgeError as exc:
            message = f"{type(exc).__name__}: {exc}"
            self._verdict = VERDICT_FAIL
            if not self.machine.is_terminal:
                self.machine.transition(
                    State.FAILED,
                    message=message,
                    metadata={"error_type": type(exc).__name__},
                )
        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised context
            message = f"Unexpected {type(exc).__name__}: {exc}"
            self._verdict = VERDICT_FAIL
            if not self.machine.is_terminal:
                self.machine.transition(
                    State.FAILED,
                    message=message,
                    metadata={"error_type": type(exc).__name__},
                )

        if self._verdict is None:
            self._verdict = (
                VERDICT_PASS
                if self.machine.state is State.TASK_COMPLETED
                else VERDICT_FAIL
            )

        self.finished_at = utc_now_iso()
        self.audit.append(
            event_type=EventType.RUN_FINISHED,
            previous_state=self.machine.state,
            new_state=self.machine.state,
            message=message or f"Run finished in {self.machine.state}.",
            metadata={
                "verdict": self._verdict,
                "attempts": self.attempts,
                "fix_rounds_used": self.fix_rounds_used,
            },
        )
        self._write_snapshot()

        return RunOutcome(
            run_id=self.run_id,
            task_id=self.task.task_id,
            final_state=self.machine.state,
            verdict=self._verdict,
            attempts=self.attempts,
            fix_rounds_used=self.fix_rounds_used,
            paths=self.paths,
            last_validation=last_validation,
            message=message or f"Run finished in {self.machine.state}.",
        )

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------

    def _implement(self) -> ImplementationResult:
        self.attempts += 1
        context = AttemptContext(
            run_id=self.run_id,
            attempt=self.attempts,
            fix_round=self.fix_rounds_used,
            workspace=self.paths.workspace_dir,
        )
        self.audit.append(
            event_type=EventType.PROVIDER_INVOKED,
            previous_state=self.machine.state,
            new_state=self.machine.state,
            message=f"Invoking provider {self.provider.name} (attempt {self.attempts}).",
            metadata={
                "provider": self.provider.name,
                "attempt": self.attempts,
                "fix_round": self.fix_rounds_used,
                "workspace": str(self.paths.workspace_dir),
            },
        )
        result = self.provider.implement(self.task, context)
        self.audit.append(
            event_type=EventType.PROVIDER_RESULT,
            previous_state=self.machine.state,
            new_state=self.machine.state,
            message=(
                f"Provider reported '{result.status}'. "
                "This is a claim and does not affect the verdict."
            ),
            metadata={"attempt": self.attempts, "claim": result.to_dict()},
        )
        return result

    def _validate(self) -> ValidationResult:
        result = self._engine.run(
            commands=self.task.validation_commands,
            round_index=self.fix_rounds_used,
            cwd=self.paths.workspace_dir,
            remaining_seconds=self._remaining_seconds(),
        )
        self.audit.append(
            event_type=EventType.VALIDATION_RESULT,
            previous_state=self.machine.state,
            new_state=self.machine.state,
            message=(
                "Validation passed." if result.passed else "Validation failed."
            ),
            metadata={
                "round_index": result.round_index,
                "passed": result.passed,
                "commands_run": len(result.commands),
                "commands_declared": len(self.task.validation_commands),
            },
        )
        return result


def run_task(
    task: TaskSpec,
    runs_dir: str | Path,
    run_id: Optional[str] = None,
    provider: Optional[Provider] = None,
) -> RunOutcome:
    """Convenience wrapper around :class:`TaskRunner`."""
    return TaskRunner(
        task=task, runs_dir=runs_dir, run_id=run_id, provider=provider
    ).run()

"""The provider interface.

A provider is anything that can attempt to implement a task inside a workspace.
Its returned :class:`ImplementationResult` is a *claim*: it is written to the
audit log for traceability and is never used to decide whether the task passed.
That decision belongs to :mod:`forge.validation` alone.

The result fields mirror the output contract in
``prompts/IMPLEMENTER_PROMPT.md`` so that a real agent adapter can populate the
same structure later without changing the runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from forge.task import TaskSpec


@dataclass(frozen=True)
class AttemptContext:
    """Everything a provider is told about the attempt it is making."""

    run_id: str
    attempt: int
    fix_round: int
    workspace: Path


@dataclass(frozen=True)
class ImplementationResult:
    """A provider's self-reported outcome. Recorded as a claim, never as proof."""

    status: str
    changed_files: tuple[str, ...] = ()
    tests_added: tuple[str, ...] = ()
    commands_run: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()
    blocking_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return the claim as a JSON-serializable dictionary."""
        return {
            "status": self.status,
            "changed_files": list(self.changed_files),
            "tests_added": list(self.tests_added),
            "commands_run": list(self.commands_run),
            "known_limitations": list(self.known_limitations),
            "blocking_reason": self.blocking_reason,
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class Provider(Protocol):
    """Implemented by every FORGE provider adapter."""

    name: str

    def implement(
        self, task: TaskSpec, context: AttemptContext
    ) -> ImplementationResult:
        """Attempt to implement ``task`` inside ``context.workspace``."""
        ...

"""A deterministic provider that makes no network calls.

The FakeProvider exists to prove the orchestration loop end to end at zero cost.
It is deliberately not a mock: it writes a real file into the run workspace, and
the task's validation command inspects that real file. So when a
``fail_then_succeed`` run recovers on its second attempt, it recovers because a
real process observed a changed workspace and returned a different exit code -
not because a stub was told to report success.

Modes:
    ``succeed``             every attempt writes a passing artifact
    ``fail``                every attempt writes a failing artifact
    ``fail_then_succeed``   attempt 1 fails, attempt 2 onwards succeed
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from forge.errors import ProviderError
from forge.providers.base import AttemptContext, ImplementationResult
from forge.task import SUPPORTED_FAKE_MODES, TaskSpec

#: Content written when the provider is meant to satisfy validation.
PASS_MARKER = "OK"

#: Content written when the provider is meant to fail validation.
FAIL_MARKER = "BROKEN"

# Which attempt number each mode starts succeeding at. None means "never".
_MODE_SUCCEEDS_FROM: dict[str, Optional[int]] = {
    "succeed": 1,
    "fail": None,
    "fail_then_succeed": 2,
}


class FakeProvider:
    """A scripted provider used to exercise the runner deterministically."""

    name = "fake"

    def __init__(self, mode: str = "succeed", artifact: str = "result.txt") -> None:
        if mode not in SUPPORTED_FAKE_MODES:
            supported = ", ".join(SUPPORTED_FAKE_MODES)
            raise ProviderError(
                f"Unknown FakeProvider mode {mode!r}. Supported: {supported}."
            )
        self.mode = mode
        self.artifact = artifact
        self.attempts: list[int] = []

    def _should_succeed(self, attempt: int) -> bool:
        threshold = _MODE_SUCCEEDS_FROM[self.mode]
        return threshold is not None and attempt >= threshold

    def implement(
        self, task: TaskSpec, context: AttemptContext
    ) -> ImplementationResult:
        """Write the artifact for this attempt and report what was claimed."""
        self.attempts.append(context.attempt)
        succeeding = self._should_succeed(context.attempt)

        artifact_path = Path(context.workspace) / self.artifact
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            PASS_MARKER if succeeding else FAIL_MARKER, encoding="utf-8"
        )

        return ImplementationResult(
            status="implemented" if succeeding else "failed",
            changed_files=(self.artifact,),
            commands_run=(),
            known_limitations=(
                ()
                if succeeding
                else ("Artifact was written in a deliberately failing state.",)
            ),
            blocking_reason=None,
            metadata={
                "provider": self.name,
                "mode": self.mode,
                "attempt": context.attempt,
                "fix_round": context.fix_round,
                "artifact": self.artifact,
            },
        )

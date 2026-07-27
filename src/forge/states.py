"""The explicit FORGE state machine.

The transition table is data, not control flow, so that the set of legal moves
can be inspected and tested directly. Any move outside the table raises
:class:`IllegalTransitionError` - transitions are never silently ignored.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Mapping, Optional

from forge.errors import IllegalTransitionError

TransitionHook = Callable[["State", "State", str, Mapping[str, Any]], None]


class State(str, Enum):
    """Every state a FORGE task run can occupy."""

    TASK_READY = "TASK_READY"
    IMPLEMENTING = "IMPLEMENTING"
    VALIDATING = "VALIDATING"
    TASK_COMPLETED = "TASK_COMPLETED"
    FIX_REQUIRED = "FIX_REQUIRED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


#: States from which no further transition is possible.
TERMINAL_STATES: frozenset[State] = frozenset(
    {State.TASK_COMPLETED, State.BLOCKED, State.FAILED, State.CANCELLED}
)

#: States a run can still move out of.
NON_TERMINAL_STATES: frozenset[State] = frozenset(
    state for state in State if state not in TERMINAL_STATES
)

# The task-flow edges. Abort edges are added mechanically below so that no
# non-terminal state can accidentally be left without an escape route.
_FLOW_TRANSITIONS: dict[State, set[State]] = {
    State.TASK_READY: {State.IMPLEMENTING},
    State.IMPLEMENTING: {State.VALIDATING},
    State.VALIDATING: {State.TASK_COMPLETED, State.FIX_REQUIRED},
    State.FIX_REQUIRED: {State.IMPLEMENTING, State.BLOCKED},
}


def _build_transition_table() -> dict[State, frozenset[State]]:
    """Build the full transition table from the flow edges plus abort edges."""
    table: dict[State, set[State]] = {state: set() for state in State}
    for source, targets in _FLOW_TRANSITIONS.items():
        table[source] |= targets
    for source in NON_TERMINAL_STATES:
        table[source] |= {State.FAILED, State.CANCELLED}
    return {source: frozenset(targets) for source, targets in table.items()}


#: The complete, immutable transition table. Terminal states map to an empty set.
TRANSITIONS: Mapping[State, frozenset[State]] = _build_transition_table()


class StateMachine:
    """Guards the current state of a single task run.

    An optional ``on_transition`` hook is called after each accepted move; the
    runner uses it to write an audit event, which keeps this class free of any
    knowledge about logging or the filesystem.
    """

    def __init__(
        self,
        initial: State = State.TASK_READY,
        on_transition: Optional[TransitionHook] = None,
    ) -> None:
        self._state = initial
        self._on_transition = on_transition
        self._history: list[State] = [initial]

    @property
    def state(self) -> State:
        """The state the run currently occupies."""
        return self._state

    @property
    def history(self) -> list[State]:
        """Every state occupied so far, in order, starting with the initial one."""
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        """True when no further transition is possible."""
        return self._state in TERMINAL_STATES

    def can_transition_to(self, target: State) -> bool:
        """Return True when moving to ``target`` is currently legal."""
        return target in TRANSITIONS[self._state]

    def transition(
        self,
        target: State,
        message: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> State:
        """Move to ``target``.

        Raises:
            IllegalTransitionError: if the move is not in the transition table.
        """
        if not self.can_transition_to(target):
            allowed = sorted(state.value for state in TRANSITIONS[self._state])
            allowed_text = ", ".join(allowed) if allowed else "none (terminal state)"
            raise IllegalTransitionError(
                f"Illegal transition {self._state.value} -> {target.value}. "
                f"Allowed from {self._state.value}: {allowed_text}."
            )

        previous = self._state
        self._state = target
        self._history.append(target)
        if self._on_transition is not None:
            self._on_transition(previous, target, message, dict(metadata or {}))
        return target

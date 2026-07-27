"""Tests for the explicit state machine."""

from __future__ import annotations

import pytest

from forge.errors import IllegalTransitionError
from forge.states import (
    NON_TERMINAL_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    State,
    StateMachine,
)


def test_happy_path_transitions_are_legal() -> None:
    """The full success path walks TASK_READY through to TASK_COMPLETED."""
    machine = StateMachine()
    assert machine.state is State.TASK_READY

    machine.transition(State.IMPLEMENTING)
    machine.transition(State.VALIDATING)
    machine.transition(State.TASK_COMPLETED)

    assert machine.state is State.TASK_COMPLETED
    assert machine.is_terminal
    assert machine.history == [
        State.TASK_READY,
        State.IMPLEMENTING,
        State.VALIDATING,
        State.TASK_COMPLETED,
    ]


def test_fix_loop_transitions_are_legal() -> None:
    """A failed validation can loop back into IMPLEMENTING and later BLOCK."""
    machine = StateMachine()
    machine.transition(State.IMPLEMENTING)
    machine.transition(State.VALIDATING)
    machine.transition(State.FIX_REQUIRED)
    machine.transition(State.IMPLEMENTING)
    machine.transition(State.VALIDATING)
    machine.transition(State.FIX_REQUIRED)
    machine.transition(State.BLOCKED)

    assert machine.state is State.BLOCKED
    assert machine.is_terminal


@pytest.mark.parametrize("source", sorted(NON_TERMINAL_STATES, key=str))
@pytest.mark.parametrize("target", [State.FAILED, State.CANCELLED])
def test_every_non_terminal_state_can_abort(source: State, target: State) -> None:
    """FAILED and CANCELLED are reachable from every non-terminal state."""
    machine = StateMachine(initial=source)
    machine.transition(target)
    assert machine.state is target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (State.TASK_READY, State.VALIDATING),
        (State.TASK_READY, State.TASK_COMPLETED),
        (State.IMPLEMENTING, State.TASK_COMPLETED),
        (State.IMPLEMENTING, State.FIX_REQUIRED),
        (State.VALIDATING, State.IMPLEMENTING),
        (State.VALIDATING, State.BLOCKED),
        (State.FIX_REQUIRED, State.VALIDATING),
        (State.FIX_REQUIRED, State.TASK_COMPLETED),
    ],
)
def test_illegal_transitions_are_rejected(source: State, target: State) -> None:
    """Moves outside the transition table raise, naming what was allowed."""
    machine = StateMachine(initial=source)
    with pytest.raises(IllegalTransitionError) as excinfo:
        machine.transition(target)

    message = str(excinfo.value)
    assert source.value in message
    assert target.value in message
    assert machine.state is source, "a rejected transition must not change state"


@pytest.mark.parametrize("source", sorted(TERMINAL_STATES, key=str))
@pytest.mark.parametrize("target", sorted(State, key=str))
def test_terminal_states_reject_every_transition(
    source: State, target: State
) -> None:
    """No state is reachable from a terminal state."""
    machine = StateMachine(initial=source)
    assert TRANSITIONS[source] == frozenset()
    with pytest.raises(IllegalTransitionError):
        machine.transition(target)


def test_transition_hook_receives_previous_and_new_state() -> None:
    """The hook the runner uses for auditing sees both ends of the move."""
    seen: list[tuple[State, State, str]] = []
    machine = StateMachine(
        on_transition=lambda previous, new, message, metadata: seen.append(
            (previous, new, message)
        )
    )
    machine.transition(State.IMPLEMENTING, message="attempt 1")

    assert seen == [(State.TASK_READY, State.IMPLEMENTING, "attempt 1")]


def test_can_transition_to_matches_the_table() -> None:
    """can_transition_to agrees with the published transition table."""
    machine = StateMachine(initial=State.VALIDATING)
    assert machine.can_transition_to(State.TASK_COMPLETED)
    assert machine.can_transition_to(State.FIX_REQUIRED)
    assert not machine.can_transition_to(State.IMPLEMENTING)

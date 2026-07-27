"""Tests for the FakeProvider's determinism."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from forge.errors import ProviderError
from forge.providers import build_provider
from forge.providers.base import AttemptContext
from forge.providers.fake import FAIL_MARKER, PASS_MARKER, FakeProvider
from forge.task import parse_task


def make_context(workspace: Path, attempt: int) -> AttemptContext:
    """Build an attempt context pointing at a temporary workspace."""
    return AttemptContext(
        run_id="run-provider",
        attempt=attempt,
        fix_round=attempt - 1,
        workspace=workspace,
    )


@pytest.mark.parametrize(
    ("mode", "attempt", "expected"),
    [
        ("succeed", 1, PASS_MARKER),
        ("succeed", 2, PASS_MARKER),
        ("fail", 1, FAIL_MARKER),
        ("fail", 5, FAIL_MARKER),
        ("fail_then_succeed", 1, FAIL_MARKER),
        ("fail_then_succeed", 2, PASS_MARKER),
        ("fail_then_succeed", 3, PASS_MARKER),
    ],
)
def test_modes_write_the_expected_artifact(
    tmp_path: Path,
    task_dict: Callable[..., dict[str, Any]],
    mode: str,
    attempt: int,
    expected: str,
) -> None:
    """Each mode writes a deterministic artifact for a given attempt number."""
    provider = FakeProvider(mode=mode, artifact="result.txt")
    task = parse_task(task_dict())

    provider.implement(task, make_context(tmp_path, attempt))

    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == expected


def test_provider_records_its_attempts(
    tmp_path: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """The provider tracks which attempts it was asked to make."""
    provider = FakeProvider(mode="fail_then_succeed")
    task = parse_task(task_dict())

    provider.implement(task, make_context(tmp_path, 1))
    provider.implement(task, make_context(tmp_path, 2))

    assert provider.attempts == [1, 2]


def test_claim_matches_the_artifact_written(
    tmp_path: Path, task_dict: Callable[..., dict[str, Any]]
) -> None:
    """The reported status lines up with what was actually written."""
    provider = FakeProvider(mode="fail_then_succeed")
    task = parse_task(task_dict())

    first = provider.implement(task, make_context(tmp_path, 1))
    second = provider.implement(task, make_context(tmp_path, 2))

    assert first.status == "failed"
    assert first.known_limitations
    assert second.status == "implemented"
    assert second.changed_files == ("result.txt",)


def test_unknown_mode_is_rejected() -> None:
    """Constructing a provider with an unknown mode fails immediately."""
    with pytest.raises(ProviderError, match="Unknown FakeProvider mode"):
        FakeProvider(mode="teleport")


def test_build_provider_returns_the_fake(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """The registry builds a FakeProvider from a validated task config."""
    task = parse_task(task_dict())
    provider = build_provider(task.provider)

    assert isinstance(provider, FakeProvider)
    assert provider.name == "fake"

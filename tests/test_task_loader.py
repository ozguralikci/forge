"""Tests for task loading and validation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from forge.errors import TaskLoadError, TaskValidationError
from forge.task import PYTHON_PLACEHOLDER, load_task, normalize_command, parse_task

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_valid_task_loads(write_task: Callable[..., Path]) -> None:
    """A well formed task file produces a fully populated TaskSpec."""
    task = load_task(write_task())

    assert task.task_id == "TEST-001"
    assert task.project_id == "FORGE-TEST"
    assert task.risk_level == "low"
    assert task.provider.name == "fake"
    assert task.provider.mode == "succeed"
    assert task.limits.max_fix_rounds == 3
    assert len(task.validation_commands) == 1
    assert task.source_path is not None


def test_shipped_example_task_is_valid() -> None:
    """The example task in examples/ must actually load."""
    task = load_task(REPO_ROOT / "examples" / "hello_task" / "task.yaml")

    assert task.task_id == "HELLO-001"
    assert task.provider.mode == "fail_then_succeed"
    # ${PYTHON} must have been resolved to a real interpreter.
    assert task.validation_commands[0][0] == sys.executable


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    """A path that does not exist raises TaskLoadError."""
    with pytest.raises(TaskLoadError, match="not found"):
        load_task(tmp_path / "does_not_exist.yaml")


def test_malformed_yaml_is_rejected(write_task: Callable[..., Path]) -> None:
    """Unparseable YAML raises TaskLoadError, not a bare YAML error."""
    path = write_task(content="task_id: [unclosed\n  broken: : :\n")
    with pytest.raises(TaskLoadError, match="not valid YAML"):
        load_task(path)


def test_empty_file_is_rejected(write_task: Callable[..., Path]) -> None:
    """An empty task file is rejected rather than treated as an empty task."""
    path = write_task(content="")
    with pytest.raises(TaskValidationError, match="empty"):
        load_task(path)


def test_non_mapping_task_is_rejected(write_task: Callable[..., Path]) -> None:
    """A YAML list at the top level is rejected."""
    path = write_task(content="- one\n- two\n")
    with pytest.raises(TaskValidationError, match="mapping at the top level"):
        load_task(path)


@pytest.mark.parametrize(
    "missing_field",
    ["task_id", "project_id", "title", "description", "acceptance_criteria",
     "risk_level"],
)
def test_missing_required_schema_field_is_rejected(
    write_task: Callable[..., Path],
    task_dict: Callable[..., dict[str, Any]],
    missing_field: str,
) -> None:
    """Each field required by schemas/task.schema.json is enforced."""
    data = task_dict()
    del data[missing_field]
    path = write_task(content=yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(TaskValidationError) as excinfo:
        load_task(path)
    assert missing_field in str(excinfo.value)


def test_invalid_risk_level_is_rejected(write_task: Callable[..., Path]) -> None:
    """risk_level is constrained by the repository schema's enum."""
    path = write_task(risk_level="catastrophic")
    with pytest.raises(TaskValidationError, match="risk_level"):
        load_task(path)


def test_unknown_provider_is_rejected(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """Only the fake provider exists in v0.1; anything else fails loudly."""
    data = task_dict(provider={"name": "claude_code", "mode": "succeed"})
    with pytest.raises(TaskValidationError, match="provider.name"):
        parse_task(data)


def test_unknown_provider_mode_is_rejected(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """An unsupported FakeProvider mode is caught at load time."""
    data = task_dict(provider={"name": "fake", "mode": "explode"})
    with pytest.raises(TaskValidationError, match="provider.mode"):
        parse_task(data)


def test_missing_validation_commands_are_rejected(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """A task with no validation command cannot produce evidence."""
    data = task_dict(validation={"commands": []})
    with pytest.raises(TaskValidationError, match="non-empty list"):
        parse_task(data)


def test_required_secrets_are_refused(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """v0.1 has no secret broker, so it refuses tasks that need secrets."""
    data = task_dict(required_secrets=["TELEGRAM_TOKEN"])
    with pytest.raises(TaskValidationError, match="secret broker"):
        parse_task(data)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("max_fix_rounds", -1),
        ("command_timeout_seconds", 0),
        ("task_timeout_seconds", 0),
        ("max_fix_rounds", "three"),
    ],
)
def test_invalid_execution_limits_are_rejected(
    task_dict: Callable[..., dict[str, Any]], field_name: str, value: Any
) -> None:
    """Safety bounds must be sane integers."""
    execution: dict[str, Any] = {
        "max_fix_rounds": 3,
        "command_timeout_seconds": 30,
        "task_timeout_seconds": 120,
    }
    execution[field_name] = value
    data = task_dict(execution=execution)

    with pytest.raises(TaskValidationError, match=field_name):
        parse_task(data)


def test_execution_limits_default_when_absent(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """The execution section is optional and falls back to documented defaults."""
    data = task_dict()
    del data["execution"]
    task = parse_task(data)

    assert task.limits.max_fix_rounds == 3
    assert task.limits.command_timeout_seconds == 60
    assert task.limits.task_timeout_seconds == 600


def test_artifact_escaping_the_workspace_is_rejected(
    task_dict: Callable[..., dict[str, Any]]
) -> None:
    """A provider artifact may not point outside the run workspace."""
    data = task_dict(
        provider={"name": "fake", "mode": "succeed", "artifact": "../escape.txt"}
    )
    with pytest.raises(TaskValidationError, match="inside the workspace"):
        parse_task(data)


def test_string_command_is_split_without_a_shell() -> None:
    """A string command is tokenized with shlex, keeping quoted arguments whole."""
    command = normalize_command('python -c "import sys; sys.exit(0)"', 0)
    assert command == ("python", "-c", "import sys; sys.exit(0)")


def test_python_placeholder_is_expanded() -> None:
    """${PYTHON} resolves to the interpreter running FORGE."""
    command = normalize_command([PYTHON_PLACEHOLDER, "-c", "pass"], 0)
    assert command == (sys.executable, "-c", "pass")


@pytest.mark.parametrize("bad", [42, {"cmd": "x"}, [], "", ["ok", 7]])
def test_malformed_commands_are_rejected(bad: Any) -> None:
    """Commands that are not a string or list of strings are rejected."""
    with pytest.raises(TaskValidationError, match=r"validation\.commands\[0\]"):
        normalize_command(bad, 0)

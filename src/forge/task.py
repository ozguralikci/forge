"""Task specification loading and validation.

The identity fields of a task (``task_id``, ``title``, ``risk_level``, ...) are
validated against the repository's own contract at ``schemas/task.schema.json``
so there is a single source of truth for that shape.

That schema does not yet describe the runtime sections FORGE needs -
``provider``, ``validation`` and ``execution`` - so those are validated here in
Python. Nothing is accepted silently: every rejection names the offending field.
"""

from __future__ import annotations

import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import yaml
from jsonschema import Draft202012Validator

from forge.errors import TaskLoadError, TaskValidationError

#: Substituted in validation commands so examples do not depend on PATH layout.
PYTHON_PLACEHOLDER = "${PYTHON}"

#: Provider names this version knows how to build.
SUPPORTED_PROVIDERS = ("fake",)

#: Modes accepted by the FakeProvider.
SUPPORTED_FAKE_MODES = ("succeed", "fail", "fail_then_succeed")

DEFAULT_MAX_FIX_ROUNDS = 3
DEFAULT_COMMAND_TIMEOUT_SECONDS = 60
DEFAULT_TASK_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class ProviderConfig:
    """How to build the provider that will implement the task."""

    name: str
    mode: str
    artifact: str


@dataclass(frozen=True)
class ExecutionLimits:
    """The safety bounds applied to a run."""

    max_fix_rounds: int
    command_timeout_seconds: int
    task_timeout_seconds: int


@dataclass(frozen=True)
class TaskSpec:
    """A fully validated task, ready to execute."""

    task_id: str
    project_id: str
    title: str
    description: str
    acceptance_criteria: tuple[str, ...]
    risk_level: str
    provider: ProviderConfig
    limits: ExecutionLimits
    validation_commands: tuple[tuple[str, ...], ...]
    source_path: Optional[Path] = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)


def find_task_schema() -> Path:
    """Locate ``schemas/task.schema.json``.

    Resolution order: the ``FORGE_TASK_SCHEMA`` environment variable, then the
    repository root inferred from this file, then the current directory. See the
    README for why an editable install is expected in v0.1.
    """
    override = os.environ.get("FORGE_TASK_SCHEMA")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override))
    # src/forge/task.py -> src/forge -> src -> <repo root>
    candidates.append(Path(__file__).resolve().parents[2] / "schemas" / "task.schema.json")
    candidates.append(Path.cwd() / "schemas" / "task.schema.json")

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    searched = "\n  ".join(str(candidate) for candidate in candidates)
    raise TaskValidationError(
        "Could not locate task.schema.json. Searched:\n  "
        f"{searched}\n"
        "Set FORGE_TASK_SCHEMA to the schema file, or run FORGE from the "
        "repository root."
    )


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TaskValidationError(
            f"'{field_name}' must be a mapping, got {type(value).__name__}."
        )
    return value


def _require_positive_int(value: Any, field_name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TaskValidationError(
            f"'{field_name}' must be an integer, got {type(value).__name__}."
        )
    if value < minimum:
        raise TaskValidationError(f"'{field_name}' must be >= {minimum}, got {value}.")
    return value


def normalize_command(raw: Any, position: int) -> tuple[str, ...]:
    """Normalize one declared command into an argv tuple.

    Commands are executed without a shell, so a string form is split with
    :func:`shlex.split` and a list form is used verbatim. Shell features such as
    pipes, redirection and ``&&`` are therefore not available.
    """
    label = f"validation.commands[{position}]"

    if isinstance(raw, str):
        if not raw.strip():
            raise TaskValidationError(f"{label} is empty.")
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            raise TaskValidationError(f"{label} could not be parsed: {exc}") from exc
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        parts = list(raw)
        if not all(isinstance(part, str) for part in parts):
            raise TaskValidationError(f"{label} must contain only strings.")
    else:
        raise TaskValidationError(
            f"{label} must be a string or a list of strings, got {type(raw).__name__}."
        )

    if not parts:
        raise TaskValidationError(f"{label} produced an empty command.")

    return tuple(part.replace(PYTHON_PLACEHOLDER, sys.executable) for part in parts)


def _parse_provider(raw: Any) -> ProviderConfig:
    config = _require_mapping(raw, "provider")

    name = config.get("name")
    if name not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise TaskValidationError(
            f"'provider.name' must be one of: {supported}. Got {name!r}. "
            "Real coding providers are not part of v0.1."
        )

    mode = config.get("mode", "succeed")
    if mode not in SUPPORTED_FAKE_MODES:
        supported = ", ".join(SUPPORTED_FAKE_MODES)
        raise TaskValidationError(
            f"'provider.mode' must be one of: {supported}. Got {mode!r}."
        )

    artifact = config.get("artifact", "result.txt")
    if not isinstance(artifact, str) or not artifact.strip():
        raise TaskValidationError("'provider.artifact' must be a non-empty string.")
    if Path(artifact).is_absolute() or ".." in Path(artifact).parts:
        raise TaskValidationError(
            "'provider.artifact' must be a relative path inside the workspace, "
            f"got {artifact!r}."
        )

    return ProviderConfig(name=name, mode=mode, artifact=artifact)


def _parse_limits(raw: Any) -> ExecutionLimits:
    config = _require_mapping(raw, "execution") if raw is not None else {}
    return ExecutionLimits(
        max_fix_rounds=_require_positive_int(
            config.get("max_fix_rounds", DEFAULT_MAX_FIX_ROUNDS),
            "execution.max_fix_rounds",
            minimum=0,
        ),
        command_timeout_seconds=_require_positive_int(
            config.get("command_timeout_seconds", DEFAULT_COMMAND_TIMEOUT_SECONDS),
            "execution.command_timeout_seconds",
            minimum=1,
        ),
        task_timeout_seconds=_require_positive_int(
            config.get("task_timeout_seconds", DEFAULT_TASK_TIMEOUT_SECONDS),
            "execution.task_timeout_seconds",
            minimum=1,
        ),
    )


def _parse_validation_commands(raw: Any) -> tuple[tuple[str, ...], ...]:
    config = _require_mapping(raw, "validation")
    commands = config.get("commands")
    if not isinstance(commands, list) or not commands:
        raise TaskValidationError(
            "'validation.commands' must be a non-empty list. A task with no "
            "validation command cannot produce evidence."
        )
    return tuple(
        normalize_command(command, index) for index, command in enumerate(commands)
    )


def _validate_against_schema(data: Mapping[str, Any]) -> None:
    """Validate the identity fields against the repository task schema."""
    schema_path = find_task_schema()
    try:
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise TaskValidationError(
            f"Could not read task schema at {schema_path}: {exc}"
        ) from exc

    errors = sorted(
        Draft202012Validator(schema).iter_errors(data),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        details = "\n".join(
            f"  - {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        )
        raise TaskValidationError(
            f"Task does not satisfy {schema_path.name}:\n{details}"
        )


def parse_task(data: Any, source_path: Optional[Path] = None) -> TaskSpec:
    """Validate an already-parsed task mapping and build a :class:`TaskSpec`."""
    if not isinstance(data, Mapping):
        raise TaskValidationError(
            f"Task file must contain a mapping at the top level, got "
            f"{type(data).__name__}."
        )

    _validate_against_schema(data)

    required_secrets = data.get("required_secrets") or []
    if required_secrets:
        raise TaskValidationError(
            "'required_secrets' is declared but FORGE v0.1 has no secret broker. "
            "Refusing to run a task whose secret handling cannot be honoured."
        )

    return TaskSpec(
        task_id=data["task_id"],
        project_id=data["project_id"],
        title=data["title"],
        description=data["description"],
        acceptance_criteria=tuple(data["acceptance_criteria"]),
        risk_level=data["risk_level"],
        provider=_parse_provider(data.get("provider")),
        limits=_parse_limits(data.get("execution")),
        validation_commands=_parse_validation_commands(data.get("validation")),
        source_path=source_path,
        raw=dict(data),
    )


def load_task(path: str | Path) -> TaskSpec:
    """Load and validate a YAML task file.

    Raises:
        TaskLoadError: the file is missing or is not parseable YAML.
        TaskValidationError: the file parsed but its contents are invalid.
    """
    task_path = Path(path)
    if not task_path.is_file():
        raise TaskLoadError(f"Task file not found: {task_path}")

    try:
        text = task_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TaskLoadError(f"Could not read task file {task_path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise TaskLoadError(f"Task file {task_path} is not valid YAML: {exc}") from exc

    if data is None:
        raise TaskValidationError(f"Task file {task_path} is empty.")

    return parse_task(data, source_path=task_path.resolve())

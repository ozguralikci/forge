"""Shared fixtures for the FORGE test suite."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# A validation command that checks the artifact the FakeProvider writes. Kept as
# an argv list so no shell or PATH lookup is involved.
ARTIFACT_CHECK_SCRIPT = (
    "import pathlib, sys\n"
    "artifact = pathlib.Path('result.txt')\n"
    "if not artifact.is_file():\n"
    "    sys.exit('FAIL: result.txt was not created')\n"
    "value = artifact.read_text(encoding='utf-8').strip()\n"
    "if value != 'OK':\n"
    "    sys.exit(f'FAIL: result.txt contains {value!r}')\n"
    "print('PASS: result.txt contains OK')\n"
)


def artifact_check_command() -> list[str]:
    """Return an argv command that passes only when the artifact says OK."""
    return [sys.executable, "-c", ARTIFACT_CHECK_SCRIPT]


def make_task_dict(**overrides: Any) -> dict[str, Any]:
    """Build a valid task mapping, with optional field overrides."""
    task: dict[str, Any] = {
        "task_id": "TEST-001",
        "project_id": "FORGE-TEST",
        "title": "Test task",
        "description": "A task used by the FORGE test suite.",
        "acceptance_criteria": ["result.txt contains OK"],
        "risk_level": "low",
        "provider": {
            "name": "fake",
            "mode": "succeed",
            "artifact": "result.txt",
        },
        "validation": {"commands": [artifact_check_command()]},
        "execution": {
            "max_fix_rounds": 3,
            "command_timeout_seconds": 30,
            "task_timeout_seconds": 120,
        },
    }
    task.update(overrides)
    return task


@pytest.fixture
def task_dict() -> Callable[..., dict[str, Any]]:
    """Return the task-mapping builder, so tests need no cross-module imports."""
    return make_task_dict


@pytest.fixture
def check_command() -> Callable[[], list[str]]:
    """Return the builder for the artifact-checking validation command."""
    return artifact_check_command


@pytest.fixture(autouse=True)
def task_schema_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the loader at the repository schema regardless of the working dir."""
    monkeypatch.setenv(
        "FORGE_TASK_SCHEMA", str(REPO_ROOT / "schemas" / "task.schema.json")
    )


@pytest.fixture
def write_task(tmp_path: Path) -> Callable[..., Path]:
    """Return a helper that writes a task file into the temp directory."""

    def _write(content: Any = None, name: str = "task.yaml", **overrides: Any) -> Path:
        path = tmp_path / name
        if content is None:
            path.write_text(
                yaml.safe_dump(make_task_dict(**overrides), sort_keys=False),
                encoding="utf-8",
            )
        else:
            path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    """A temporary directory to hold run records."""
    path = tmp_path / "runs"
    path.mkdir()
    return path

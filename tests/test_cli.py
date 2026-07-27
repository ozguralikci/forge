"""Tests for the command line interface and its exit codes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest

from forge.cli import EXIT_INVALID_TASK, main


def test_successful_run_exits_zero(
    write_task: Callable[..., Path],
    runs_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A passing task exits 0 and reports the PASS verdict."""
    task_file = write_task()
    exit_code = main(["run", str(task_file), "--runs-dir", str(runs_dir)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Verdict  : PASS" in output
    assert "TASK_COMPLETED" in output


def test_blocked_run_exits_one_and_shows_stderr(
    write_task: Callable[..., Path],
    runs_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A blocked run exits 1 and echoes the failing command's stderr."""
    task_file = write_task(
        provider={"name": "fake", "mode": "fail", "artifact": "result.txt"},
        execution={
            "max_fix_rounds": 0,
            "command_timeout_seconds": 30,
            "task_timeout_seconds": 60,
        },
    )
    exit_code = main(["run", str(task_file), "--runs-dir", str(runs_dir)])

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "Verdict  : FAIL" in output
    assert "BLOCKED" in output
    # Failing output is surfaced, never swallowed.
    assert "FAIL: result.txt contains" in output


def test_invalid_task_file_exits_four(
    write_task: Callable[..., Path],
    runs_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An unloadable task exits with the dedicated invalid-task code."""
    task_file = write_task(content="task_id: [unclosed\n")
    exit_code = main(["run", str(task_file), "--runs-dir", str(runs_dir)])

    assert exit_code == EXIT_INVALID_TASK
    assert "error:" in capsys.readouterr().err


def test_missing_task_file_exits_four(
    tmp_path: Path, runs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A nonexistent task path is reported, not raised as a traceback."""
    exit_code = main(
        ["run", str(tmp_path / "nope.yaml"), "--runs-dir", str(runs_dir)]
    )

    assert exit_code == EXIT_INVALID_TASK
    assert "not found" in capsys.readouterr().err


def test_run_id_can_be_pinned(
    write_task: Callable[..., Path],
    runs_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--run-id controls the run directory name."""
    task_file = write_task()
    exit_code = main(
        ["run", str(task_file), "--runs-dir", str(runs_dir), "--run-id", "pinned-run"]
    )

    assert exit_code == 0
    assert (runs_dir / "pinned-run" / "events.jsonl").is_file()
    assert "pinned-run" in capsys.readouterr().out

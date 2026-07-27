"""Command line interface: ``forge run <task-file>``.

Exit codes are part of the contract so the CLI can be driven by a script:

    0  TASK_COMPLETED
    1  BLOCKED       (validation never passed within max_fix_rounds)
    2  FAILED        (an error or the task timeout ended the run)
    3  CANCELLED     (interrupted)
    4  the task file could not be loaded or is invalid
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from forge import __version__
from forge.errors import ForgeError
from forge.runner import TaskRunner
from forge.states import State
from forge.task import load_task

EXIT_CODES: dict[State, int] = {
    State.TASK_COMPLETED: 0,
    State.BLOCKED: 1,
    State.FAILED: 2,
    State.CANCELLED: 3,
}

EXIT_INVALID_TASK = 4

#: How much of a failing command's stderr to echo, so failures are never hidden.
STDERR_TAIL_CHARS = 2000


def build_parser() -> argparse.ArgumentParser:
    """Build the ``forge`` argument parser."""
    parser = argparse.ArgumentParser(
        prog="forge",
        description=(
            "FORGE v0.1 - run a task specification through the deterministic "
            "implement/validate loop."
        ),
    )
    parser.add_argument("--version", action="version", version=f"forge {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run a task file.")
    run_parser.add_argument("task_file", help="Path to the YAML task specification.")
    run_parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Directory that holds run records (default: ./runs).",
    )
    run_parser.add_argument(
        "--run-id",
        default=None,
        help="Use a specific run id instead of generating one.",
    )
    return parser


def _print_failure_output(outcome) -> None:
    """Echo the failing command's captured stderr, never silently."""
    validation = outcome.last_validation
    failure = validation.first_failure if validation else None
    if failure is None:
        return

    print(f"\nFailing command : {' '.join(failure.command)}")
    print(f"Exit code       : {failure.exit_code}")
    if failure.timed_out:
        print("Timed out       : yes")
    if failure.launch_error:
        print(f"Launch error    : {failure.launch_error}")

    stderr_file = outcome.paths.root / failure.stderr_path
    if stderr_file.is_file():
        text = stderr_file.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            if len(text) > STDERR_TAIL_CHARS:
                text = "...\n" + text[-STDERR_TAIL_CHARS:]
            print("--- stderr ---")
            print(text)
            print("--------------")


def command_run(args: argparse.Namespace) -> int:
    """Handle ``forge run``."""
    try:
        task = load_task(args.task_file)
    except ForgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID_TASK

    runner = TaskRunner(task=task, runs_dir=args.runs_dir, run_id=args.run_id)
    print(f"Task     : {task.task_id} - {task.title}")
    print(f"Provider : {runner.provider.name} (mode={task.provider.mode})")
    print(f"Run id   : {runner.run_id}")
    print(f"Run dir  : {runner.paths.root}")

    outcome = runner.run()

    print(f"\nState    : {outcome.final_state}")
    print(f"Verdict  : {outcome.verdict}")
    print(f"Attempts : {outcome.attempts}")
    print(f"Fix rounds used: {outcome.fix_rounds_used}/{task.limits.max_fix_rounds}")
    print(f"Message  : {outcome.message}")

    if not outcome.passed:
        _print_failure_output(outcome)

    print(f"\nEvidence : {outcome.paths.evidence_dir}")
    print(f"Audit    : {outcome.paths.events_file}")

    return EXIT_CODES.get(outcome.final_state, 2)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``forge`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return command_run(args)
    parser.error(f"Unknown command: {args.command}")
    return 2  # pragma: no cover - argparse exits first


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

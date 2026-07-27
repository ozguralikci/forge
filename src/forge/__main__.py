"""Support ``python -m forge run <task-file>`` during development."""

from __future__ import annotations

from forge.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

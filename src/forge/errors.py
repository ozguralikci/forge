"""Exception hierarchy for FORGE.

Every error raised deliberately by FORGE derives from :class:`ForgeError`, so a
caller can distinguish an expected, explained failure from an unexpected crash.
"""

from __future__ import annotations


class ForgeError(Exception):
    """Base class for all errors raised deliberately by FORGE."""


class TaskLoadError(ForgeError):
    """The task file could not be read or parsed as YAML."""


class TaskValidationError(ForgeError):
    """The task file parsed, but its contents are missing or malformed."""


class IllegalTransitionError(ForgeError):
    """A state transition was requested that the state machine forbids."""


class ProviderError(ForgeError):
    """A provider could not be built or failed while implementing a task."""

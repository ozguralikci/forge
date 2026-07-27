"""FORGE v0.1 - the deterministic execution core of the AI Software Factory.

This package implements the smallest flow that proves the project's founding
principle: a task specification is executed by a provider, and an independent
validation step decides PASS or FAIL from real command exit codes, never from
the provider's own claims.
"""

from forge.errors import (
    ForgeError,
    IllegalTransitionError,
    ProviderError,
    TaskLoadError,
    TaskValidationError,
)
from forge.states import TRANSITIONS, State, StateMachine

__version__ = "0.1.0"

__all__ = [
    "ForgeError",
    "IllegalTransitionError",
    "ProviderError",
    "State",
    "StateMachine",
    "TRANSITIONS",
    "TaskLoadError",
    "TaskValidationError",
    "__version__",
]

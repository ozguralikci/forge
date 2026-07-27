"""Provider adapters.

FORGE v0.1 ships exactly one provider: the deterministic
:class:`~forge.providers.fake.FakeProvider`. Real coding providers arrive in a
later phase, behind the same interface.
"""

from __future__ import annotations

from forge.errors import ProviderError
from forge.providers.base import AttemptContext, ImplementationResult, Provider
from forge.providers.fake import FakeProvider
from forge.task import ProviderConfig

__all__ = [
    "AttemptContext",
    "FakeProvider",
    "ImplementationResult",
    "Provider",
    "build_provider",
]


def build_provider(config: ProviderConfig) -> Provider:
    """Build the provider described by a validated task's provider config."""
    if config.name == "fake":
        return FakeProvider(mode=config.mode, artifact=config.artifact)
    raise ProviderError(
        f"Unknown provider {config.name!r}. FORGE v0.1 supports: fake."
    )

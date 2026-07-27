"""Credentials for the GitHub integration layer.

Credentials are values that are passed in, never read from module-level state.
Nothing here reads ``os.environ`` implicitly: :func:`credentials_from_env` takes
the environment mapping as an argument so tests and callers stay in control.

Token safety is enforced structurally, in line with the project constitution's
rule that secrets must not reach logs or agent messages:

* the token is excluded from the generated ``repr``,
* ``__repr__`` and ``__str__`` are overridden to emit a redacted form,
* :meth:`TokenCredentials.redacted` gives a loggable fingerprint that cannot be
  used to reconstruct the token.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol, runtime_checkable

from forge.errors import ForgeError

#: Environment variables consulted, in order, when resolving a token.
DEFAULT_TOKEN_VARIABLES: tuple[str, ...] = ("FORGE_GITHUB_TOKEN", "GITHUB_TOKEN")

#: Placeholder substituted wherever a token would otherwise be rendered.
REDACTED = "***redacted***"


class CredentialsError(ForgeError):
    """Credentials were missing or malformed."""


@runtime_checkable
class Credentials(Protocol):
    """Anything that can authenticate a GitHub request."""

    @property
    def is_anonymous(self) -> bool:
        """True when these credentials add no authentication."""
        ...

    def auth_headers(self) -> Mapping[str, str]:
        """Return the headers to merge into an outgoing request."""
        ...


@dataclass(frozen=True)
class AnonymousCredentials:
    """Unauthenticated access.

    Valid for reading public resources, subject to a much lower rate limit.
    """

    @property
    def is_anonymous(self) -> bool:
        """Always True."""
        return True

    def auth_headers(self) -> Mapping[str, str]:
        """Return no headers."""
        return {}

    def __repr__(self) -> str:
        return "AnonymousCredentials()"


@dataclass(frozen=True)
class TokenCredentials:
    """A personal access token or installation token.

    The token is never included in the representation of this object. Anything
    that logs credentials therefore logs a redaction, not a secret.
    """

    token: str = field(repr=False)
    scheme: str = "Bearer"

    def __post_init__(self) -> None:
        if not isinstance(self.token, str) or not self.token.strip():
            raise CredentialsError("GitHub token must be a non-empty string.")
        if self.token != self.token.strip():
            # A stray newline from a file or shell pipeline would produce an
            # invalid header, so normalise instead of failing at request time.
            object.__setattr__(self, "token", self.token.strip())
        if not self.scheme.strip():
            raise CredentialsError("Authorization scheme must be non-empty.")

    @property
    def is_anonymous(self) -> bool:
        """Always False."""
        return False

    def auth_headers(self) -> Mapping[str, str]:
        """Return the Authorization header for this token."""
        return {"Authorization": f"{self.scheme} {self.token}"}

    def redacted(self) -> str:
        """Return a loggable fingerprint that cannot reconstruct the token.

        Only the length is disclosed, which is enough to tell "wrong variable"
        from "truncated value" while debugging.
        """
        return f"<github token, {len(self.token)} chars, {REDACTED}>"

    def __repr__(self) -> str:
        return f"TokenCredentials(token={REDACTED}, scheme={self.scheme!r})"

    def __str__(self) -> str:
        return self.__repr__()


def credentials_from_env(
    env: Optional[Mapping[str, str]] = None,
    variables: tuple[str, ...] = DEFAULT_TOKEN_VARIABLES,
    *,
    required: bool = False,
) -> Credentials:
    """Resolve credentials from an environment mapping.

    Args:
        env: The mapping to read. Defaults to ``os.environ``, but is injectable
            so tests never mutate real process state.
        variables: Variable names to try, in order.
        required: When True, raise instead of falling back to anonymous access.

    Returns:
        :class:`TokenCredentials` when a token is found, otherwise
        :class:`AnonymousCredentials`.

    Raises:
        CredentialsError: if ``required`` is set and no token was found.
    """
    source = os.environ if env is None else env
    for name in variables:
        value = source.get(name)
        if value and value.strip():
            return TokenCredentials(token=value)

    if required:
        tried = ", ".join(variables)
        raise CredentialsError(
            f"No GitHub token found. Set one of: {tried}."
        )
    return AnonymousCredentials()

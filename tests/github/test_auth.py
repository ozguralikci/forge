"""Tests for GitHub credentials, with emphasis on token redaction."""

from __future__ import annotations

import pytest

from forge.github.auth import (
    REDACTED,
    AnonymousCredentials,
    Credentials,
    CredentialsError,
    TokenCredentials,
    credentials_from_env,
)

SECRET = "ghp_ThisIsNotARealTokenJustATestValue"


def test_token_produces_bearer_header() -> None:
    """A token becomes an Authorization header."""
    credentials = TokenCredentials(token=SECRET)

    assert credentials.auth_headers() == {"Authorization": f"Bearer {SECRET}"}
    assert credentials.is_anonymous is False


def test_scheme_is_configurable() -> None:
    """A different authorization scheme can be supplied."""
    credentials = TokenCredentials(token=SECRET, scheme="token")

    assert credentials.auth_headers() == {"Authorization": f"token {SECRET}"}


@pytest.mark.parametrize("render", [repr, str, "{}".format, lambda c: f"{c}"])
def test_token_never_appears_in_any_rendering(render) -> None:
    """No standard way of rendering the object may leak the secret."""
    credentials = TokenCredentials(token=SECRET)
    rendered = render(credentials)

    assert SECRET not in rendered
    assert REDACTED in rendered


def test_token_absent_from_dataclass_repr_fields() -> None:
    """The token is excluded from the generated repr, not merely masked."""
    assert SECRET not in repr(TokenCredentials(token=SECRET))


def test_redacted_fingerprint_discloses_only_length() -> None:
    """The loggable fingerprint cannot reconstruct the token."""
    fingerprint = TokenCredentials(token=SECRET).redacted()

    assert SECRET not in fingerprint
    assert str(len(SECRET)) in fingerprint


@pytest.mark.parametrize("bad", ["", "   ", "\n", None, 123])
def test_empty_or_non_string_tokens_are_rejected(bad) -> None:
    """A blank token fails immediately rather than at request time."""
    with pytest.raises(CredentialsError, match="non-empty string"):
        TokenCredentials(token=bad)


def test_surrounding_whitespace_is_stripped() -> None:
    """A trailing newline from a file or pipeline would break the header."""
    credentials = TokenCredentials(token=f"  {SECRET}\n")

    assert credentials.auth_headers() == {"Authorization": f"Bearer {SECRET}"}


def test_anonymous_credentials_add_no_headers() -> None:
    """Anonymous access sends no Authorization header."""
    credentials = AnonymousCredentials()

    assert credentials.auth_headers() == {}
    assert credentials.is_anonymous is True


def test_both_credential_types_satisfy_the_protocol() -> None:
    """Both implementations are usable wherever Credentials is expected."""
    assert isinstance(TokenCredentials(token=SECRET), Credentials)
    assert isinstance(AnonymousCredentials(), Credentials)


def test_env_resolution_prefers_the_forge_variable() -> None:
    """FORGE_GITHUB_TOKEN wins over the generic GITHUB_TOKEN."""
    env = {"FORGE_GITHUB_TOKEN": "forge-token", "GITHUB_TOKEN": "generic-token"}

    credentials = credentials_from_env(env)

    assert credentials.auth_headers() == {"Authorization": "Bearer forge-token"}


def test_env_resolution_falls_back_to_github_token() -> None:
    """The generic variable is used when the FORGE-specific one is absent."""
    credentials = credentials_from_env({"GITHUB_TOKEN": "generic-token"})

    assert credentials.auth_headers() == {"Authorization": "Bearer generic-token"}


def test_env_resolution_returns_anonymous_when_absent() -> None:
    """With no token configured, access degrades to anonymous."""
    assert isinstance(credentials_from_env({}), AnonymousCredentials)


def test_env_resolution_ignores_blank_values() -> None:
    """An empty variable is treated as unset, not as a token."""
    assert isinstance(credentials_from_env({"GITHUB_TOKEN": "   "}), AnonymousCredentials)


def test_required_env_resolution_raises_when_absent() -> None:
    """required=True turns a missing token into an explicit failure."""
    with pytest.raises(CredentialsError, match="No GitHub token found"):
        credentials_from_env({}, required=True)


def test_env_resolution_does_not_read_real_environment() -> None:
    """Passing a mapping keeps os.environ out of the resolution path."""
    assert isinstance(credentials_from_env({}), AnonymousCredentials)

"""FORGE GitHub integration - read-only foundation (v0.1.1).

This package establishes the architecture for GitHub access. It performs **no
mutations**: :class:`~forge.github.client.GitHubClient` refuses any HTTP method
outside ``GET`` and ``HEAD`` before a request is built, so a write is a loud
error rather than a silent possibility.

It is entirely additive. Nothing in the execution engine, runtime, or state
machine imports it, and importing it changes no existing behaviour.

Composition happens through :class:`GitHub`, which wires one client to the
resource APIs::

    from forge.github import GitHub, TokenCredentials

    github = GitHub.from_credentials(TokenCredentials(token))
    repository = github.repositories.get("ozguralikci", "forge")
    open_prs = github.pull_requests.list("ozguralikci", "forge", state="open")

Every collaborator is injectable and there is no module-level state, so tests
substitute a fake transport instead of touching the network::

    client = GitHubClient(transport=FakeTransport(...))
    github = GitHub(client)
"""

from __future__ import annotations

from typing import Optional

from forge.github.auth import (
    AnonymousCredentials,
    Credentials,
    CredentialsError,
    TokenCredentials,
    credentials_from_env,
)
from forge.github.branches import BranchesAPI
from forge.github.client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    READ_ONLY_METHODS,
    AuthenticationError,
    GitHubApiError,
    GitHubClient,
    GitHubError,
    HttpRequest,
    HttpResponse,
    NotFoundError,
    RateLimitError,
    ReadOnlyViolationError,
    Transport,
    TransportError,
    UrllibTransport,
)
from forge.github.commits import CommitsAPI
from forge.github.models import (
    Branch,
    Commit,
    GitHubUser,
    PayloadError,
    PullRequest,
    RateLimit,
    Repository,
)
from forge.github.pull_requests import PullRequestsAPI
from forge.github.repositories import RepositoriesAPI

__all__ = [
    "AnonymousCredentials",
    "AuthenticationError",
    "Branch",
    "BranchesAPI",
    "Commit",
    "CommitsAPI",
    "Credentials",
    "CredentialsError",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "GitHub",
    "GitHubApiError",
    "GitHubClient",
    "GitHubError",
    "GitHubUser",
    "HttpRequest",
    "HttpResponse",
    "NotFoundError",
    "PayloadError",
    "PullRequest",
    "PullRequestsAPI",
    "READ_ONLY_METHODS",
    "RateLimit",
    "RateLimitError",
    "ReadOnlyViolationError",
    "RepositoriesAPI",
    "Repository",
    "TokenCredentials",
    "Transport",
    "TransportError",
    "UrllibTransport",
    "credentials_from_env",
]


class GitHub:
    """Composition root binding one client to the read-only resource APIs.

    This is a convenience, not a requirement: every resource API can be
    constructed directly with a client if a caller wants only one of them.
    """

    def __init__(self, client: GitHubClient) -> None:
        self._client = client
        self.repositories = RepositoriesAPI(client)
        self.branches = BranchesAPI(client)
        self.pull_requests = PullRequestsAPI(client)
        self.commits = CommitsAPI(client)

    @property
    def client(self) -> GitHubClient:
        """The client shared by every resource API."""
        return self._client

    @property
    def is_read_only(self) -> bool:
        """True while the underlying client permits only safe methods."""
        return self._client.is_read_only

    @classmethod
    def from_credentials(
        cls,
        credentials: Optional[Credentials] = None,
        *,
        transport: Optional[Transport] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> "GitHub":
        """Build a facade over a client assembled from the given parts."""
        return cls(
            GitHubClient(
                credentials=credentials,
                transport=transport,
                base_url=base_url,
                timeout_seconds=timeout_seconds,
            )
        )

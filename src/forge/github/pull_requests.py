"""Read-only pull request queries.

Note the deliberate absence of ``create``, ``update``, ``merge`` and ``close``.
This layer reads; it does not mutate. The client would refuse the request even
if such a method existed here.
"""

from __future__ import annotations

from typing import Optional

from forge.github.client import GitHubClient
from forge.github.models import Commit, PullRequest
from forge.github.repositories import encode_segment

#: Values GitHub accepts for the pull request ``state`` filter.
PULL_REQUEST_STATES: tuple[str, ...] = ("open", "closed", "all")


class PullRequestsAPI:
    """Pull request reads, bound to an injected client."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    @property
    def client(self) -> GitHubClient:
        """The client this API reads through."""
        return self._client

    def _repo_path(self, owner: str, repo: str) -> str:
        return (
            f"/repos/{encode_segment(owner, 'owner')}"
            f"/{encode_segment(repo, 'repo')}/pulls"
        )

    def get(self, owner: str, repo: str, number: int) -> PullRequest:
        """Fetch a single pull request by number."""
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise ValueError("Pull request number must be a positive integer.")
        path = f"{self._repo_path(owner, repo)}/{number}"
        return PullRequest.from_payload(self._client.get_json(path))

    def list(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        base: Optional[str] = None,
        head: Optional[str] = None,
        per_page: int = 30,
        max_pages: int = 10,
    ) -> list[PullRequest]:
        """List pull requests, optionally filtered by state and branch."""
        if state not in PULL_REQUEST_STATES:
            allowed = ", ".join(PULL_REQUEST_STATES)
            raise ValueError(f"state must be one of: {allowed}. Got {state!r}.")

        payloads = self._client.paginate_items(
            self._repo_path(owner, repo),
            {"state": state, "base": base, "head": head, "per_page": per_page},
            max_pages=max_pages,
        )
        return [PullRequest.from_payload(item) for item in payloads]

    def list_commits(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        per_page: int = 30,
        max_pages: int = 10,
    ) -> list[Commit]:
        """List the commits contained in a pull request."""
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise ValueError("Pull request number must be a positive integer.")
        path = f"{self._repo_path(owner, repo)}/{number}/commits"
        payloads = self._client.paginate_items(
            path, {"per_page": per_page}, max_pages=max_pages
        )
        return [Commit.from_payload(item) for item in payloads]

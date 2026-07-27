"""Read-only repository queries."""

from __future__ import annotations

import urllib.parse
from typing import Optional

from forge.github.client import GitHubClient
from forge.github.models import Repository


def encode_segment(value: str, name: str) -> str:
    """Validate and percent-encode a single URL path segment.

    Rejecting empty values here turns a subtle wrong-URL bug into an immediate,
    named error, and encoding keeps a value containing ``/`` or ``?`` from
    silently changing which endpoint is called.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return urllib.parse.quote(value.strip(), safe="")


class RepositoriesAPI:
    """Repository reads, bound to an injected client."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    @property
    def client(self) -> GitHubClient:
        """The client this API reads through."""
        return self._client

    def get(self, owner: str, repo: str) -> Repository:
        """Fetch a single repository."""
        path = f"/repos/{encode_segment(owner, 'owner')}/{encode_segment(repo, 'repo')}"
        return Repository.from_payload(self._client.get_json(path))

    def list_for_org(
        self,
        org: str,
        *,
        per_page: int = 30,
        repo_type: Optional[str] = None,
        max_pages: int = 10,
    ) -> list[Repository]:
        """List an organisation's repositories."""
        path = f"/orgs/{encode_segment(org, 'org')}/repos"
        payloads = self._client.paginate_items(
            path,
            {"per_page": per_page, "type": repo_type},
            max_pages=max_pages,
        )
        return [Repository.from_payload(item) for item in payloads]

    def list_for_user(
        self, username: str, *, per_page: int = 30, max_pages: int = 10
    ) -> list[Repository]:
        """List a user's public repositories."""
        path = f"/users/{encode_segment(username, 'username')}/repos"
        payloads = self._client.paginate_items(
            path, {"per_page": per_page}, max_pages=max_pages
        )
        return [Repository.from_payload(item) for item in payloads]

"""Read-only commit queries."""

from __future__ import annotations

from typing import Optional

from forge.github.client import GitHubClient
from forge.github.models import Commit
from forge.github.repositories import encode_segment


class CommitsAPI:
    """Commit reads, bound to an injected client."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    @property
    def client(self) -> GitHubClient:
        """The client this API reads through."""
        return self._client

    def _repo_path(self, owner: str, repo: str) -> str:
        return (
            f"/repos/{encode_segment(owner, 'owner')}"
            f"/{encode_segment(repo, 'repo')}/commits"
        )

    def get(self, owner: str, repo: str, ref: str) -> Commit:
        """Fetch a single commit by SHA, branch name, or tag."""
        path = f"{self._repo_path(owner, repo)}/{encode_segment(ref, 'ref')}"
        return Commit.from_payload(self._client.get_json(path))

    def list(
        self,
        owner: str,
        repo: str,
        *,
        sha: Optional[str] = None,
        path_filter: Optional[str] = None,
        author: Optional[str] = None,
        per_page: int = 30,
        max_pages: int = 10,
    ) -> list[Commit]:
        """List commits, optionally filtered by branch, path, or author."""
        payloads = self._client.paginate_items(
            self._repo_path(owner, repo),
            {
                "sha": sha,
                "path": path_filter,
                "author": author,
                "per_page": per_page,
            },
            max_pages=max_pages,
        )
        return [Commit.from_payload(item) for item in payloads]

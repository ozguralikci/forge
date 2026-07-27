"""Read-only branch queries."""

from __future__ import annotations

from forge.github.client import GitHubClient, NotFoundError
from forge.github.models import Branch
from forge.github.repositories import encode_segment


class BranchesAPI:
    """Branch reads, bound to an injected client."""

    def __init__(self, client: GitHubClient) -> None:
        self._client = client

    @property
    def client(self) -> GitHubClient:
        """The client this API reads through."""
        return self._client

    def get(self, owner: str, repo: str, branch: str) -> Branch:
        """Fetch a single branch."""
        path = (
            f"/repos/{encode_segment(owner, 'owner')}"
            f"/{encode_segment(repo, 'repo')}"
            f"/branches/{encode_segment(branch, 'branch')}"
        )
        return Branch.from_payload(self._client.get_json(path))

    def list(
        self,
        owner: str,
        repo: str,
        *,
        protected: bool | None = None,
        per_page: int = 30,
        max_pages: int = 10,
    ) -> list[Branch]:
        """List a repository's branches."""
        path = (
            f"/repos/{encode_segment(owner, 'owner')}"
            f"/{encode_segment(repo, 'repo')}/branches"
        )
        payloads = self._client.paginate_items(
            path,
            {"per_page": per_page, "protected": protected},
            max_pages=max_pages,
        )
        return [Branch.from_payload(item) for item in payloads]

    def exists(self, owner: str, repo: str, branch: str) -> bool:
        """Return whether a branch is visible to these credentials."""
        try:
            self.get(owner, repo, branch)
        except NotFoundError:
            return False
        return True

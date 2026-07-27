"""Fixtures for the GitHub integration tests.

Every test in this package runs against :class:`FakeTransport`. No test opens a
socket, and none reads the real environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

import pytest

from forge.github.client import GitHubClient, HttpRequest, HttpResponse


@dataclass
class FakeTransport:
    """A scripted :class:`~forge.github.client.Transport` for tests.

    Queued responses are returned in order and every request is recorded, so a
    test can assert both what came back and exactly what was sent.
    """

    responses: list[HttpResponse] = field(default_factory=list)
    requests: list[HttpRequest] = field(default_factory=list)
    error: Optional[Exception] = None

    def send(self, request: HttpRequest) -> HttpResponse:
        """Record the request and return the next scripted response."""
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError(
                f"FakeTransport had no queued response for {request.method} "
                f"{request.url}"
            )
        return self.responses.pop(0)

    @property
    def last_request(self) -> HttpRequest:
        """The most recent request, for assertions."""
        if not self.requests:
            raise AssertionError("No request was sent.")
        return self.requests[-1]

    @property
    def urls(self) -> list[str]:
        """Every URL requested, in order."""
        return [request.url for request in self.requests]


def json_response(
    payload: Any,
    status_code: int = 200,
    headers: Optional[Mapping[str, str]] = None,
    url: str = "https://api.github.com/test",
) -> HttpResponse:
    """Build a JSON :class:`HttpResponse` for the fake transport."""
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    return HttpResponse(
        status_code=status_code,
        headers=merged,
        body=json.dumps(payload),
        url=url,
    )


@pytest.fixture
def make_response() -> Callable[..., HttpResponse]:
    """Return the JSON response builder."""
    return json_response


@pytest.fixture
def transport() -> FakeTransport:
    """An empty fake transport."""
    return FakeTransport()


@pytest.fixture
def make_client(transport: FakeTransport) -> Callable[..., GitHubClient]:
    """Return a builder for clients wired to the shared fake transport."""

    def _make(responses: Optional[Sequence[HttpResponse]] = None, **kwargs: Any):
        if responses:
            transport.responses.extend(responses)
        return GitHubClient(transport=transport, **kwargs)

    return _make


# ---------------------------------------------------------------------------
# Representative API payloads, trimmed to the fields the models read.
# ---------------------------------------------------------------------------

REPOSITORY_PAYLOAD: dict[str, Any] = {
    "id": 42,
    "name": "forge",
    "full_name": "ozguralikci/forge",
    "private": False,
    "description": "AI software factory",
    "default_branch": "main",
    "html_url": "https://github.com/ozguralikci/forge",
    "owner": {
        "login": "ozguralikci",
        "id": 7,
        "html_url": "https://github.com/ozguralikci",
    },
}

BRANCH_PAYLOAD: dict[str, Any] = {
    "name": "main",
    "commit": {"sha": "a" * 40},
    "protected": True,
}

PULL_REQUEST_PAYLOAD: dict[str, Any] = {
    "number": 1,
    "title": "Implement FORGE v0.1 execution engine",
    "state": "open",
    "draft": False,
    "created_at": "2026-07-27T19:44:04Z",
    "merged_at": None,
    "html_url": "https://github.com/ozguralikci/forge/pull/1",
    "head": {"ref": "feature/forge-v0.1-core"},
    "base": {"ref": "main"},
    "user": {"login": "ozguralikci"},
}

COMMIT_PAYLOAD: dict[str, Any] = {
    "sha": "b" * 40,
    "html_url": "https://github.com/ozguralikci/forge/commit/" + "b" * 40,
    "commit": {
        "message": "fix(core): enforce shared task timeout budget",
        "author": {
            "name": "Ozgur Alikci",
            "email": "dev@example.com",
            "date": "2026-07-28T08:00:00Z",
        },
    },
    "author": {"login": "ozguralikci"},
}


@pytest.fixture
def repository_payload() -> dict[str, Any]:
    """A representative repository payload."""
    return dict(REPOSITORY_PAYLOAD)


@pytest.fixture
def branch_payload() -> dict[str, Any]:
    """A representative branch payload."""
    return dict(BRANCH_PAYLOAD)


@pytest.fixture
def pull_request_payload() -> dict[str, Any]:
    """A representative pull request payload."""
    return dict(PULL_REQUEST_PAYLOAD)


@pytest.fixture
def commit_payload() -> dict[str, Any]:
    """A representative commit payload."""
    return dict(COMMIT_PAYLOAD)

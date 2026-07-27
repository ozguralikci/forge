"""Tests for the resource APIs and the GitHub facade."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from forge.github import GitHub
from forge.github.auth import TokenCredentials
from forge.github.branches import BranchesAPI
from forge.github.client import GitHubClient, NotFoundError
from forge.github.commits import CommitsAPI
from forge.github.pull_requests import PullRequestsAPI
from forge.github.repositories import RepositoriesAPI, encode_segment


# ---------------------------------------------------------------------------
# repositories
# ---------------------------------------------------------------------------


def test_repository_get_calls_the_right_endpoint(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    repository_payload: dict[str, Any],
) -> None:
    """A repository read hits /repos/{owner}/{repo} and returns a model."""
    api = RepositoriesAPI(make_client([make_response(repository_payload)]))

    repository = api.get("ozguralikci", "forge")

    assert transport.last_request.url == "https://api.github.com/repos/ozguralikci/forge"
    assert transport.last_request.method == "GET"
    assert repository.full_name == "ozguralikci/forge"


def test_repository_list_for_org_paginates(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    repository_payload: dict[str, Any],
) -> None:
    """Organisation repositories are collected across pages."""
    first = make_response(
        [repository_payload],
        headers={"Link": '<https://api.github.com/orgs/acme/repos?page=2>; rel="next"'},
    )
    second = make_response([repository_payload])
    api = RepositoriesAPI(make_client([first, second]))

    repositories = api.list_for_org("acme")

    assert len(repositories) == 2
    assert transport.urls[0].startswith("https://api.github.com/orgs/acme/repos")


def test_repository_list_for_user_uses_users_endpoint(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    repository_payload: dict[str, Any],
) -> None:
    """User repositories come from the /users endpoint."""
    api = RepositoriesAPI(make_client([make_response([repository_payload])]))

    api.list_for_user("ozguralikci")

    assert transport.urls[0].startswith("https://api.github.com/users/ozguralikci/repos")


# ---------------------------------------------------------------------------
# path segment safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", None, 5])
def test_empty_path_segments_are_rejected(bad) -> None:
    """A blank owner or repo is a named error, not a malformed URL."""
    with pytest.raises(ValueError, match="non-empty string"):
        encode_segment(bad, "owner")


def test_path_segments_are_percent_encoded(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """A segment containing a slash cannot change which endpoint is called."""
    api = RepositoriesAPI(make_client([make_response({"full_name": "a", "name": "b"})]))

    api.get("owner", "repo/../../secret")

    assert "repo%2F..%2F..%2Fsecret" in transport.last_request.url
    assert "/repos/owner/repo/../.." not in transport.last_request.url


# ---------------------------------------------------------------------------
# branches
# ---------------------------------------------------------------------------


def test_branch_get_returns_model(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    branch_payload: dict[str, Any],
) -> None:
    """A branch read hits the branches endpoint."""
    api = BranchesAPI(make_client([make_response(branch_payload)]))

    branch = api.get("ozguralikci", "forge", "main")

    assert branch.name == "main"
    assert transport.last_request.url.endswith("/repos/ozguralikci/forge/branches/main")


def test_branch_list_returns_models(
    make_client: Callable[..., GitHubClient],
    make_response,
    branch_payload: dict[str, Any],
) -> None:
    """Branch listing returns parsed models."""
    api = BranchesAPI(make_client([make_response([branch_payload, branch_payload])]))

    assert len(api.list("o", "r")) == 2


def test_branch_exists_is_true_when_found(
    make_client: Callable[..., GitHubClient],
    make_response,
    branch_payload: dict[str, Any],
) -> None:
    """A visible branch reports as existing."""
    api = BranchesAPI(make_client([make_response(branch_payload)]))

    assert api.exists("o", "r", "main") is True


def test_branch_exists_is_false_on_not_found(
    make_client: Callable[..., GitHubClient], make_response
) -> None:
    """A 404 becomes False rather than propagating."""
    api = BranchesAPI(
        make_client([make_response({"message": "Not Found"}, status_code=404)])
    )

    assert api.exists("o", "r", "absent") is False


def test_branch_exists_does_not_swallow_other_errors(
    make_client: Callable[..., GitHubClient], make_response
) -> None:
    """Only NotFound is converted; a server error still raises."""
    api = BranchesAPI(
        make_client([make_response({"message": "boom"}, status_code=500)])
    )

    with pytest.raises(Exception) as excinfo:
        api.exists("o", "r", "main")
    assert not isinstance(excinfo.value, NotFoundError)


# ---------------------------------------------------------------------------
# pull requests
# ---------------------------------------------------------------------------


def test_pull_request_get_returns_model(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    pull_request_payload: dict[str, Any],
) -> None:
    """A pull request read hits /pulls/{number}."""
    api = PullRequestsAPI(make_client([make_response(pull_request_payload)]))

    pull_request = api.get("ozguralikci", "forge", 1)

    assert pull_request.number == 1
    assert transport.last_request.url.endswith("/repos/ozguralikci/forge/pulls/1")


def test_pull_request_list_filters_are_passed(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    pull_request_payload: dict[str, Any],
) -> None:
    """State and base filters reach the query string."""
    api = PullRequestsAPI(make_client([make_response([pull_request_payload])]))

    api.list("o", "r", state="closed", base="main")

    url = transport.last_request.url
    assert "state=closed" in url
    assert "base=main" in url


def test_pull_request_list_rejects_unknown_state(
    make_client: Callable[..., GitHubClient]
) -> None:
    """An invalid state is caught locally rather than sent to the API."""
    api = PullRequestsAPI(make_client())

    with pytest.raises(ValueError, match="state must be one of"):
        api.list("o", "r", state="merged")


@pytest.mark.parametrize("bad", [0, -1, "1", True])
def test_pull_request_number_must_be_positive_int(
    make_client: Callable[..., GitHubClient], bad
) -> None:
    """A non-positive or non-integer number is rejected."""
    api = PullRequestsAPI(make_client())

    with pytest.raises(ValueError, match="positive integer"):
        api.get("o", "r", bad)


def test_pull_request_commits_are_listed(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    commit_payload: dict[str, Any],
) -> None:
    """A pull request's commits are read from its commits endpoint."""
    api = PullRequestsAPI(make_client([make_response([commit_payload])]))

    commits = api.list_commits("o", "r", 1)

    assert len(commits) == 1
    assert transport.urls[0].startswith("https://api.github.com/repos/o/r/pulls/1/commits")


def test_pull_requests_api_exposes_no_mutations() -> None:
    """The read-only posture is visible in the API surface itself."""
    forbidden = {"create", "update", "merge", "close", "delete", "edit"}

    assert forbidden.isdisjoint(dir(PullRequestsAPI))


# ---------------------------------------------------------------------------
# commits
# ---------------------------------------------------------------------------


def test_commit_get_returns_model(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    commit_payload: dict[str, Any],
) -> None:
    """A commit read hits /commits/{ref}."""
    api = CommitsAPI(make_client([make_response(commit_payload)]))

    commit = api.get("o", "r", "b" * 40)

    assert commit.sha == "b" * 40
    assert transport.last_request.url.endswith(f"/repos/o/r/commits/{'b' * 40}")


def test_commit_list_filters_are_passed(
    make_client: Callable[..., GitHubClient],
    transport,
    make_response,
    commit_payload: dict[str, Any],
) -> None:
    """Branch and path filters reach the query string."""
    api = CommitsAPI(make_client([make_response([commit_payload])]))

    api.list("o", "r", sha="main", path_filter="src/forge")

    url = transport.last_request.url
    assert "sha=main" in url
    assert "path=src%2Fforge" in url


# ---------------------------------------------------------------------------
# facade
# ---------------------------------------------------------------------------


def test_facade_shares_one_client(make_client: Callable[..., GitHubClient]) -> None:
    """Every resource API on the facade reads through the same client."""
    client = make_client()
    github = GitHub(client)

    assert github.client is client
    assert github.repositories.client is client
    assert github.branches.client is client
    assert github.pull_requests.client is client
    assert github.commits.client is client


def test_facade_reports_read_only(make_client: Callable[..., GitHubClient]) -> None:
    """The facade surfaces the client's read-only posture."""
    assert GitHub(make_client()).is_read_only is True


def test_facade_from_credentials_injects_transport(
    transport, make_response, repository_payload: dict[str, Any]
) -> None:
    """The factory accepts an injected transport, so no network is touched."""
    transport.responses.append(make_response(repository_payload))
    github = GitHub.from_credentials(transport=transport)

    repository = github.repositories.get("ozguralikci", "forge")

    assert repository.name == "forge"


def test_two_facades_are_independent(transport) -> None:
    """Facades hold no shared or global state."""
    first = GitHub.from_credentials(transport=transport, base_url="https://a.test")
    second = GitHub.from_credentials(transport=transport, base_url="https://b.test")

    assert first.client is not second.client
    assert first.repositories is not second.repositories


# ---------------------------------------------------------------------------
# public API surface
# ---------------------------------------------------------------------------


def test_token_credentials_is_exported() -> None:
    """TokenCredentials is part of the documented public API.

    It is the type callers need in order to authenticate at all, and the README
    example imports it by name, so omitting it from __all__ would break
    ``from forge.github import *`` and misrepresent the public surface.
    """
    import forge.github as package

    assert "TokenCredentials" in package.__all__
    assert package.TokenCredentials is TokenCredentials


@pytest.mark.parametrize(
    "name",
    ["TokenCredentials", "AnonymousCredentials", "Credentials", "credentials_from_env"],
)
def test_credential_api_is_fully_exported(name: str) -> None:
    """Every piece needed to construct credentials is exported together."""
    import forge.github as package

    assert name in package.__all__


def test_every_exported_name_resolves() -> None:
    """__all__ must not name anything the package does not actually provide.

    Guards against the whole class of defect this test was added for: a name
    listed but missing, or a public type present but never listed.
    """
    import forge.github as package

    missing = [name for name in package.__all__ if not hasattr(package, name)]

    assert missing == [], f"__all__ names these non-existent attributes: {missing}"


def test_star_import_provides_the_credential_types() -> None:
    """A wildcard import yields a usable client-construction surface."""
    namespace: dict[str, object] = {}
    exec("from forge.github import *", namespace)  # noqa: S102

    for name in ("GitHub", "GitHubClient", "TokenCredentials", "AnonymousCredentials"):
        assert name in namespace, f"{name} was not provided by a star import"

"""Tests for parsing GitHub payloads into domain models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from forge.github.models import (
    Branch,
    Commit,
    GitHubUser,
    PayloadError,
    PullRequest,
    RateLimit,
    Repository,
    parse_timestamp,
)


def test_repository_is_parsed(repository_payload: dict[str, Any]) -> None:
    """Repository fields are lifted from the payload."""
    repository = Repository.from_payload(repository_payload)

    assert repository.full_name == "ozguralikci/forge"
    assert repository.name == "forge"
    assert repository.default_branch == "main"
    assert repository.private is False
    assert repository.owner is not None
    assert repository.owner.login == "ozguralikci"
    assert repository.repository_id == 42


def test_branch_is_parsed(branch_payload: dict[str, Any]) -> None:
    """Branch fields, including the nested commit SHA, are lifted."""
    branch = Branch.from_payload(branch_payload)

    assert branch.name == "main"
    assert branch.commit_sha == "a" * 40
    assert branch.protected is True


def test_pull_request_is_parsed(pull_request_payload: dict[str, Any]) -> None:
    """Pull request fields, including nested refs, are lifted."""
    pull_request = PullRequest.from_payload(pull_request_payload)

    assert pull_request.number == 1
    assert pull_request.state == "open"
    assert pull_request.head_ref == "feature/forge-v0.1-core"
    assert pull_request.base_ref == "main"
    assert pull_request.author is not None
    assert pull_request.author.login == "ozguralikci"
    assert pull_request.is_merged is False
    assert pull_request.created_at == datetime(
        2026, 7, 27, 19, 44, 4, tzinfo=timezone.utc
    )


def test_merged_pull_request_reports_merged(
    pull_request_payload: dict[str, Any]
) -> None:
    """A merge timestamp flips is_merged."""
    pull_request_payload["merged_at"] = "2026-07-28T09:00:00Z"

    assert PullRequest.from_payload(pull_request_payload).is_merged is True


def test_commit_is_flattened(commit_payload: dict[str, Any]) -> None:
    """The nested commit payload is flattened onto one model."""
    commit = Commit.from_payload(commit_payload)

    assert commit.sha == "b" * 40
    assert commit.short_sha == "bbbbbbb"
    assert commit.message == "fix(core): enforce shared task timeout budget"
    assert commit.author_name == "Ozgur Alikci"
    assert commit.authored_at == datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
    assert commit.author is not None
    assert commit.author.login == "ozguralikci"


def test_raw_payload_is_retained(repository_payload: dict[str, Any]) -> None:
    """Nothing is lost: the full payload stays available on the model."""
    repository = Repository.from_payload(repository_payload)

    assert repository.raw["id"] == 42


def test_models_are_immutable(repository_payload: dict[str, Any]) -> None:
    """Models are frozen, so parsed data cannot drift."""
    repository = Repository.from_payload(repository_payload)

    with pytest.raises(Exception):
        repository.name = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("model", "payload", "missing"),
    [
        (Repository, {"name": "forge"}, "full_name"),
        (Repository, {"full_name": "o/r"}, "name"),
        (Branch, {"commit": {"sha": "x"}}, "name"),
        (PullRequest, {"title": "t", "state": "open"}, "number"),
        (Commit, {"commit": {}}, "sha"),
        (GitHubUser, {"id": 1}, "login"),
    ],
)
def test_missing_required_fields_are_named(model, payload, missing: str) -> None:
    """A malformed payload names the field that was absent."""
    with pytest.raises(PayloadError, match=missing):
        model.from_payload(payload)


def test_optional_nested_user_absence_is_tolerated() -> None:
    """A payload without an owner parses, with owner left as None."""
    repository = Repository.from_payload({"full_name": "o/r", "name": "r"})

    assert repository.owner is None
    assert repository.default_branch is None


def test_branch_without_commit_is_tolerated() -> None:
    """A branch payload lacking commit detail still parses."""
    assert Branch.from_payload({"name": "main"}).commit_sha is None


def test_from_optional_returns_none_for_malformed_user() -> None:
    """A nested user missing its login degrades to None, not an error."""
    assert GitHubUser.from_optional({"id": 1}) is None
    assert GitHubUser.from_optional(None) is None
    assert GitHubUser.from_optional("not a mapping") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-07-28T08:00:00Z", datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)),
        ("2026-07-28T08:00:00+00:00", datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)),
        (None, None),
        ("", None),
        ("not a date", None),
        (12345, None),
    ],
)
def test_timestamp_parsing(value, expected) -> None:
    """Timestamps parse to aware UTC, and bad values degrade to None."""
    assert parse_timestamp(value) == expected


def test_naive_timestamp_is_assumed_utc() -> None:
    """A timestamp without an offset is interpreted as UTC."""
    parsed = parse_timestamp("2026-07-28T08:00:00")

    assert parsed == datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)


def test_rate_limit_reports_exhaustion() -> None:
    """Zero remaining requests is reported as exhausted."""
    assert RateLimit.from_headers({"X-RateLimit-Remaining": "0"}).is_exhausted is True
    assert RateLimit.from_headers({"X-RateLimit-Remaining": "5"}).is_exhausted is False
    assert RateLimit.from_headers({}).is_exhausted is False


def test_rate_limit_ignores_unparseable_headers() -> None:
    """Junk header values degrade to None rather than raising."""
    rate_limit = RateLimit.from_headers({"X-RateLimit-Limit": "not-a-number"})

    assert rate_limit.limit is None

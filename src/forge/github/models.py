"""Immutable domain models for the GitHub integration layer.

These are frozen dataclasses rather than Pydantic models: the rest of FORGE
already models its domain with dataclasses, and this keeps the integration layer
free of runtime dependencies.

Each model exposes a ``from_payload`` classmethod that maps a GitHub REST API
JSON object onto the model. Parsing is deliberately narrow - only the fields
FORGE has a use for are lifted out, and the untouched remainder of the payload
is kept on ``raw`` so nothing is lost for callers that need more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


class PayloadError(ValueError):
    """A GitHub payload was missing a field the model requires."""


def _require(payload: Mapping[str, Any], key: str, model: str) -> Any:
    """Return ``payload[key]`` or explain precisely what was missing."""
    if key not in payload or payload[key] is None:
        raise PayloadError(f"{model} payload is missing required field {key!r}.")
    return payload[key]


def _optional_str(payload: Mapping[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse a GitHub ISO-8601 timestamp into an aware UTC datetime.

    Returns None for missing or unparseable values: a timestamp FORGE cannot
    read is not a reason to reject an otherwise usable payload.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class GitHubUser:
    """A GitHub account referenced by another resource."""

    login: str
    user_id: Optional[int] = None
    html_url: Optional[str] = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "GitHubUser":
        """Build a user from a GitHub API payload."""
        return cls(
            login=_require(payload, "login", "GitHubUser"),
            user_id=payload.get("id"),
            html_url=_optional_str(payload, "html_url"),
            raw=dict(payload),
        )

    @classmethod
    def from_optional(
        cls, payload: Optional[Mapping[str, Any]]
    ) -> Optional["GitHubUser"]:
        """Build a user when the payload is present, otherwise return None."""
        if not isinstance(payload, Mapping):
            return None
        try:
            return cls.from_payload(payload)
        except PayloadError:
            return None


@dataclass(frozen=True)
class Repository:
    """A GitHub repository."""

    full_name: str
    name: str
    owner: Optional[GitHubUser] = None
    default_branch: Optional[str] = None
    private: bool = False
    html_url: Optional[str] = None
    description: Optional[str] = None
    repository_id: Optional[int] = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Repository":
        """Build a repository from a GitHub API payload."""
        return cls(
            full_name=_require(payload, "full_name", "Repository"),
            name=_require(payload, "name", "Repository"),
            owner=GitHubUser.from_optional(payload.get("owner")),
            default_branch=_optional_str(payload, "default_branch"),
            private=bool(payload.get("private", False)),
            html_url=_optional_str(payload, "html_url"),
            description=_optional_str(payload, "description"),
            repository_id=payload.get("id"),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class Branch:
    """A branch reference within a repository."""

    name: str
    commit_sha: Optional[str] = None
    protected: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Branch":
        """Build a branch from a GitHub API payload."""
        commit = payload.get("commit")
        commit_sha = commit.get("sha") if isinstance(commit, Mapping) else None
        return cls(
            name=_require(payload, "name", "Branch"),
            commit_sha=commit_sha if isinstance(commit_sha, str) else None,
            protected=bool(payload.get("protected", False)),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class PullRequest:
    """A pull request, as read from the API."""

    number: int
    title: str
    state: str
    draft: bool = False
    head_ref: Optional[str] = None
    base_ref: Optional[str] = None
    author: Optional[GitHubUser] = None
    html_url: Optional[str] = None
    merged_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_merged(self) -> bool:
        """True when the API reported a merge timestamp."""
        return self.merged_at is not None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "PullRequest":
        """Build a pull request from a GitHub API payload."""
        head = payload.get("head")
        base = payload.get("base")
        return cls(
            number=int(_require(payload, "number", "PullRequest")),
            title=_require(payload, "title", "PullRequest"),
            state=_require(payload, "state", "PullRequest"),
            draft=bool(payload.get("draft", False)),
            head_ref=head.get("ref") if isinstance(head, Mapping) else None,
            base_ref=base.get("ref") if isinstance(base, Mapping) else None,
            author=GitHubUser.from_optional(payload.get("user")),
            html_url=_optional_str(payload, "html_url"),
            merged_at=parse_timestamp(payload.get("merged_at")),
            created_at=parse_timestamp(payload.get("created_at")),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class Commit:
    """A commit, flattened from GitHub's nested commit payload."""

    sha: str
    message: Optional[str] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    authored_at: Optional[datetime] = None
    author: Optional[GitHubUser] = None
    html_url: Optional[str] = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @property
    def short_sha(self) -> str:
        """The conventional seven character abbreviation."""
        return self.sha[:7]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Commit":
        """Build a commit from a GitHub API payload."""
        inner = payload.get("commit")
        inner = inner if isinstance(inner, Mapping) else {}
        author = inner.get("author")
        author = author if isinstance(author, Mapping) else {}
        return cls(
            sha=_require(payload, "sha", "Commit"),
            message=_optional_str(inner, "message"),
            author_name=_optional_str(author, "name"),
            author_email=_optional_str(author, "email"),
            authored_at=parse_timestamp(author.get("date")),
            author=GitHubUser.from_optional(payload.get("author")),
            html_url=_optional_str(payload, "html_url"),
            raw=dict(payload),
        )


@dataclass(frozen=True)
class RateLimit:
    """The rate limit state reported on a response."""

    limit: Optional[int] = None
    remaining: Optional[int] = None
    used: Optional[int] = None
    reset_at: Optional[datetime] = None

    @property
    def is_exhausted(self) -> bool:
        """True when the API has reported zero remaining requests."""
        return self.remaining is not None and self.remaining <= 0

    @classmethod
    def from_headers(cls, headers: Mapping[str, str]) -> "RateLimit":
        """Read the ``X-RateLimit-*`` headers, tolerating absence."""
        lowered = {key.lower(): value for key, value in headers.items()}

        def as_int(name: str) -> Optional[int]:
            try:
                return int(lowered[name])
            except (KeyError, TypeError, ValueError):
                return None

        reset = as_int("x-ratelimit-reset")
        return cls(
            limit=as_int("x-ratelimit-limit"),
            remaining=as_int("x-ratelimit-remaining"),
            used=as_int("x-ratelimit-used"),
            reset_at=(
                datetime.fromtimestamp(reset, tz=timezone.utc)
                if reset is not None
                else None
            ),
        )

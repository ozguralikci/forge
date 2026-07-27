"""Transport abstraction and the read-only GitHub client.

Two ideas carry this module.

**The transport is injectable.** :class:`GitHubClient` never imports an HTTP
library directly; it talks to the :class:`Transport` protocol. The shipped
implementation uses :mod:`urllib` from the standard library, so the integration
adds no runtime dependency, and tests substitute a fake transport instead of
patching globals or opening sockets.

**Read-only is enforced structurally, not by convention.** v0.1.1 is a read-only
foundation, so :meth:`GitHubClient.request` refuses any method outside
:data:`READ_ONLY_METHODS` before a request is ever built. A mutation is a
programming error that fails loudly rather than something prevented by everyone
remembering not to do it. Write support will mean deliberately widening that
set, which is a visible, reviewable change.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Mapping, Optional, Protocol, Sequence

from forge.errors import ForgeError
from forge.github.auth import REDACTED, AnonymousCredentials, Credentials
from forge.github.models import RateLimit

#: The public GitHub API root.
DEFAULT_BASE_URL = "https://api.github.com"

#: Per-request timeout, in seconds.
DEFAULT_TIMEOUT_SECONDS = 30.0

#: The REST API version this client is written against.
DEFAULT_API_VERSION = "2022-11-28"

#: Sent so GitHub can attribute traffic.
DEFAULT_USER_AGENT = "forge-github-integration"

#: The only HTTP methods this layer is permitted to use.
READ_ONLY_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})

#: Safety net for pagination so a malformed Link header cannot loop forever.
DEFAULT_MAX_PAGES = 100

#: Headers whose values must never be rendered. Compared case-insensitively,
#: because HTTP header names are not case sensitive.
SENSITIVE_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
    }
)


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with every sensitive value replaced.

    Header *names* are preserved so a reader can still see that, say, an
    Authorization header was present; only the value is removed. The input is
    never mutated.
    """
    return {
        key: (REDACTED if key.lower() in SENSITIVE_HEADERS else value)
        for key, value in headers.items()
    }


class GitHubError(ForgeError):
    """Base class for every GitHub integration error."""


class ReadOnlyViolationError(GitHubError):
    """A write was attempted through a read-only client."""


class TransportError(GitHubError):
    """The request never produced an HTTP response."""


class GitHubApiError(GitHubError):
    """GitHub returned an unsuccessful HTTP status."""

    def __init__(
        self,
        status_code: int,
        message: str,
        url: str,
        documentation_url: Optional[str] = None,
    ) -> None:
        super().__init__(f"GitHub API error {status_code} for {url}: {message}")
        self.status_code = status_code
        self.message = message
        self.url = url
        self.documentation_url = documentation_url


class AuthenticationError(GitHubApiError):
    """Credentials were missing, invalid, or lacked the required scope."""


class NotFoundError(GitHubApiError):
    """The resource does not exist, or the token cannot see it."""


class RateLimitError(GitHubApiError):
    """The rate limit is exhausted."""

    def __init__(
        self,
        status_code: int,
        message: str,
        url: str,
        rate_limit: Optional[RateLimit] = None,
    ) -> None:
        super().__init__(status_code, message, url)
        self.rate_limit = rate_limit


@dataclass(frozen=True)
class HttpRequest:
    """An outgoing HTTP request, fully resolved.

    This object necessarily carries the resolved ``Authorization`` header, so
    its representation is redacted in two independent ways: ``headers`` is
    excluded from the dataclass-generated ``repr``, and the explicit
    ``__repr__`` below renders sensitive values as a redaction. Either alone
    would be sufficient; both together mean that removing one does not silently
    reintroduce a credential leak into logs, tracebacks or debugger output.

    Redaction is a display concern only. :attr:`headers` still holds the real
    values, because the transport has to send them.
    """

    method: str
    url: str
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def redacted_headers(self) -> dict[str, str]:
        """The headers with sensitive values removed, safe to log."""
        return redact_headers(self.headers)

    def __repr__(self) -> str:
        return (
            f"HttpRequest(method={self.method!r}, url={self.url!r}, "
            f"headers={self.redacted_headers()!r}, "
            f"timeout_seconds={self.timeout_seconds!r})"
        )


@dataclass(frozen=True)
class HttpResponse:
    """An HTTP response, independent of the library that produced it."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: str = ""
    url: str = ""

    @property
    def is_success(self) -> bool:
        """True for 2xx statuses."""
        return 200 <= self.status_code < 300

    def header(self, name: str) -> Optional[str]:
        """Look up a header case-insensitively, as HTTP requires."""
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None

    def json(self) -> Any:
        """Parse the body as JSON.

        Raises:
            GitHubApiError: if the body is not valid JSON.
        """
        if not self.body.strip():
            return None
        try:
            return json.loads(self.body)
        except json.JSONDecodeError as exc:
            raise GitHubApiError(
                self.status_code, f"Response body was not valid JSON: {exc}", self.url
            ) from exc

    def rate_limit(self) -> RateLimit:
        """The rate limit state reported on this response."""
        return RateLimit.from_headers(self.headers)


class Transport(Protocol):
    """Sends an :class:`HttpRequest` and returns an :class:`HttpResponse`.

    An implementation must return a response for ordinary HTTP error statuses
    rather than raising, so that status interpretation stays in one place. Only
    genuine transport failures - DNS, connection, timeout - should raise
    :class:`TransportError`.
    """

    def send(self, request: HttpRequest) -> HttpResponse:
        """Perform the request."""
        ...


class UrllibTransport:
    """A :class:`Transport` backed by the standard library.

    ``urlopen`` is injectable so the transport itself remains unit-testable
    without network access.
    """

    def __init__(self, urlopen: Optional[Callable[..., Any]] = None) -> None:
        self._urlopen = urlopen or urllib.request.urlopen

    def send(self, request: HttpRequest) -> HttpResponse:
        """Perform the request, mapping HTTP errors onto responses."""
        native = urllib.request.Request(
            url=request.url,
            headers=dict(request.headers),
            method=request.method,
        )
        try:
            with self._urlopen(native, timeout=request.timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                return HttpResponse(
                    status_code=getattr(response, "status", 200),
                    headers=dict(response.headers.items()),
                    body=body,
                    url=request.url,
                )
        except urllib.error.HTTPError as exc:
            # A 4xx/5xx is a response, not a transport failure.
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return HttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()) if exc.headers else {},
                body=body,
                url=request.url,
            )
        except urllib.error.URLError as exc:
            raise TransportError(
                f"Could not reach {request.url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise TransportError(
                f"Request to {request.url} timed out after "
                f"{request.timeout_seconds}s."
            ) from exc


def parse_link_header(value: Optional[str]) -> dict[str, str]:
    """Parse a ``Link`` header into a mapping of relation name to URL."""
    links: dict[str, str] = {}
    if not value:
        return links
    for part in value.split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        url = section[0].strip()
        if not (url.startswith("<") and url.endswith(">")):
            continue
        for attribute in section[1:]:
            key, _, raw = attribute.strip().partition("=")
            if key.strip() == "rel":
                links[raw.strip().strip('"')] = url[1:-1]
    return links


class GitHubClient:
    """A read-only HTTP client for the GitHub REST API.

    Every collaborator is injected and there is no module-level state, so any
    number of independently configured clients can coexist.
    """

    def __init__(
        self,
        credentials: Optional[Credentials] = None,
        transport: Optional[Transport] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = DEFAULT_USER_AGENT,
        api_version: str = DEFAULT_API_VERSION,
    ) -> None:
        self._credentials: Credentials = credentials or AnonymousCredentials()
        self._transport: Transport = transport or UrllibTransport()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent
        self._api_version = api_version

    @property
    def base_url(self) -> str:
        """The API root this client targets."""
        return self._base_url

    @property
    def credentials(self) -> Credentials:
        """The credentials in use. Never renders the token."""
        return self._credentials

    @property
    def is_read_only(self) -> bool:
        """True for as long as only safe methods are permitted."""
        return not (READ_ONLY_METHODS - {"GET", "HEAD"})

    # ------------------------------------------------------------------
    # request construction
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self._user_agent,
            "X-GitHub-Api-Version": self._api_version,
        }
        headers.update(self._credentials.auth_headers())
        return headers

    def build_url(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> str:
        """Resolve ``path`` against the base URL and append a query string.

        An absolute URL is accepted only when it stays within the configured
        base URL, so a hostile ``Link`` header cannot redirect this client - and
        its Authorization header - to another host.
        """
        if path.startswith(("http://", "https://")):
            if not path.startswith(self._base_url):
                raise GitHubError(
                    f"Refusing to request {path!r}: outside the configured base "
                    f"URL {self._base_url!r}."
                )
            url = path
        else:
            url = f"{self._base_url}/{path.lstrip('/')}"

        if params:
            filtered = {
                key: value for key, value in params.items() if value is not None
            }
            if filtered:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}{urllib.parse.urlencode(filtered)}"
        return url

    # ------------------------------------------------------------------
    # requests
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
    ) -> HttpResponse:
        """Perform a read-only request.

        Raises:
            ReadOnlyViolationError: for any method outside
                :data:`READ_ONLY_METHODS`. This is checked before the request is
                constructed, so a mutation never reaches the transport.
        """
        normalized = method.upper()
        if normalized not in READ_ONLY_METHODS:
            allowed = ", ".join(sorted(READ_ONLY_METHODS))
            raise ReadOnlyViolationError(
                f"{normalized} is not permitted: the FORGE GitHub integration is "
                f"read-only in this version. Allowed methods: {allowed}."
            )

        request = HttpRequest(
            method=normalized,
            url=self.build_url(path, params),
            headers=self._headers(),
            timeout_seconds=self._timeout_seconds,
        )
        response = self._transport.send(request)
        self._raise_for_status(response)
        return response

    def get(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> HttpResponse:
        """Perform a GET request."""
        return self.request("GET", path, params)

    def get_json(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> Any:
        """Perform a GET request and return the decoded JSON body."""
        return self.get(path, params).json()

    def paginate(
        self,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> Iterator[Sequence[Any]]:
        """Yield each page of a paginated collection, following ``Link``.

        Pages are yielded lazily so a caller can stop early. ``max_pages`` bounds
        the walk; when it is hit, iteration stops rather than looping forever on
        a malformed header.
        """
        next_path: Optional[str] = path
        next_params = params
        pages = 0

        while next_path is not None and pages < max_pages:
            response = self.get(next_path, next_params)
            payload = response.json()
            if payload is None:
                return
            if not isinstance(payload, list):
                raise GitHubApiError(
                    response.status_code,
                    "Expected a JSON array for a paginated collection, got "
                    f"{type(payload).__name__}.",
                    response.url,
                )
            yield payload
            pages += 1

            # The next link already carries the query string.
            next_path = parse_link_header(response.header("Link")).get("next")
            next_params = None

    def paginate_items(
        self,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> list[Any]:
        """Collect every item across pages into one list."""
        items: list[Any] = []
        for page in self.paginate(path, params, max_pages=max_pages):
            items.extend(page)
        return items

    # ------------------------------------------------------------------
    # status handling
    # ------------------------------------------------------------------

    def _raise_for_status(self, response: HttpResponse) -> None:
        """Translate an unsuccessful status into a specific exception."""
        if response.is_success:
            return

        message, documentation_url = self._error_details(response)
        rate_limit = response.rate_limit()

        if response.status_code == 401:
            raise AuthenticationError(401, message, response.url, documentation_url)
        if response.status_code == 403 and rate_limit.is_exhausted:
            raise RateLimitError(403, message, response.url, rate_limit)
        if response.status_code == 429:
            raise RateLimitError(429, message, response.url, rate_limit)
        if response.status_code == 403:
            raise AuthenticationError(403, message, response.url, documentation_url)
        if response.status_code == 404:
            raise NotFoundError(404, message, response.url, documentation_url)
        raise GitHubApiError(
            response.status_code, message, response.url, documentation_url
        )

    @staticmethod
    def _error_details(response: HttpResponse) -> tuple[str, Optional[str]]:
        """Extract GitHub's error message without letting parsing fail twice."""
        try:
            payload = json.loads(response.body) if response.body.strip() else None
        except json.JSONDecodeError:
            payload = None

        if isinstance(payload, Mapping):
            message = payload.get("message")
            documentation_url = payload.get("documentation_url")
            return (
                message if isinstance(message, str) else "Unknown error",
                documentation_url if isinstance(documentation_url, str) else None,
            )
        return "Unknown error", None

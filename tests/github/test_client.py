"""Tests for the GitHub client: read-only enforcement, URLs, errors, paging."""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

import pytest

from forge.github.auth import REDACTED, AnonymousCredentials, TokenCredentials
from forge.github.client import (
    READ_ONLY_METHODS,
    SENSITIVE_HEADERS,
    AuthenticationError,
    GitHubApiError,
    GitHubClient,
    GitHubError,
    HttpRequest,
    HttpResponse,
    NotFoundError,
    RateLimitError,
    ReadOnlyViolationError,
    TransportError,
    UrllibTransport,
    parse_link_header,
    redact_headers,
)

SECRET = "ghp_ThisIsNotARealTokenJustATestValue"


# ---------------------------------------------------------------------------
# read-only enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post", "patch"])
def test_write_methods_are_refused(
    make_client: Callable[..., GitHubClient], transport, method: str
) -> None:
    """Any mutating method is rejected before a request is built."""
    client = make_client()

    with pytest.raises(ReadOnlyViolationError, match="read-only"):
        client.request(method, "/repos/o/r")

    assert transport.requests == [], "no request may reach the transport"


@pytest.mark.parametrize("method", sorted(READ_ONLY_METHODS))
def test_safe_methods_are_allowed(
    make_client: Callable[..., GitHubClient], make_response, method: str
) -> None:
    """GET and HEAD are permitted."""
    client = make_client([make_response({"ok": True})])

    response = client.request(method, "/repos/o/r")

    assert response.status_code == 200


def test_client_reports_itself_as_read_only(
    make_client: Callable[..., GitHubClient]
) -> None:
    """The read-only posture is introspectable."""
    assert make_client().is_read_only is True


def test_read_only_method_set_contains_no_mutations() -> None:
    """The permitted set must never quietly acquire a write method."""
    assert READ_ONLY_METHODS == {"GET", "HEAD"}


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def test_relative_path_is_resolved_against_base_url(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """A leading slash is optional and never doubled."""
    client = make_client([make_response({}), make_response({})])

    client.get("/repos/o/r")
    client.get("repos/o/r")

    assert transport.urls == [
        "https://api.github.com/repos/o/r",
        "https://api.github.com/repos/o/r",
    ]


def test_query_parameters_are_encoded(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """Params are URL-encoded onto the query string."""
    client = make_client([make_response({})])

    client.get("/search", {"q": "a b&c", "per_page": 30})

    assert "q=a+b%26c" in transport.last_request.url
    assert "per_page=30" in transport.last_request.url


def test_none_parameters_are_dropped(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """Unset optional filters do not appear in the query string."""
    client = make_client([make_response({})])

    client.get("/pulls", {"state": "open", "base": None})

    assert "state=open" in transport.last_request.url
    assert "base" not in transport.last_request.url


def test_absolute_url_outside_base_is_refused(
    make_client: Callable[..., GitHubClient]
) -> None:
    """A hostile next link cannot redirect the client to another host."""
    client = make_client()

    with pytest.raises(GitHubError, match="outside the configured base URL"):
        client.get("https://evil.example.com/repos/o/r")


def test_custom_base_url_is_honoured(transport, make_response) -> None:
    """A GitHub Enterprise base URL is supported."""
    client = GitHubClient(
        transport=transport, base_url="https://ghe.example.com/api/v3/"
    )
    transport.responses.append(make_response({}))

    client.get("/repos/o/r")

    assert transport.last_request.url == "https://ghe.example.com/api/v3/repos/o/r"


# ---------------------------------------------------------------------------
# headers
# ---------------------------------------------------------------------------


def test_default_headers_are_sent(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """Accept, User-Agent and API version accompany every request."""
    client = make_client([make_response({})])

    client.get("/repos/o/r")
    headers = transport.last_request.headers

    assert headers["Accept"] == "application/vnd.github+json"
    assert headers["X-GitHub-Api-Version"]
    assert headers["User-Agent"]


def test_token_credentials_add_authorization(
    transport, make_response
) -> None:
    """A token client authenticates its requests."""
    client = GitHubClient(
        credentials=TokenCredentials(token=SECRET), transport=transport
    )
    transport.responses.append(make_response({}))

    client.get("/repos/o/r")

    assert transport.last_request.headers["Authorization"] == f"Bearer {SECRET}"


def test_anonymous_client_sends_no_authorization(
    transport, make_response
) -> None:
    """Anonymous access omits the header entirely."""
    client = GitHubClient(credentials=AnonymousCredentials(), transport=transport)
    transport.responses.append(make_response({}))

    client.get("/repos/o/r")

    assert "Authorization" not in transport.last_request.headers


def test_client_defaults_to_anonymous(make_client: Callable[..., GitHubClient]) -> None:
    """Omitting credentials yields anonymous access, not an error."""
    assert make_client().credentials.is_anonymous is True


def test_timeout_is_attached_to_every_request(
    transport, make_response
) -> None:
    """The configured timeout reaches the transport."""
    client = GitHubClient(transport=transport, timeout_seconds=7.5)
    transport.responses.append(make_response({}))

    client.get("/repos/o/r")

    assert transport.last_request.timeout_seconds == 7.5


# ---------------------------------------------------------------------------
# error mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (404, NotFoundError),
        (422, GitHubApiError),
        (500, GitHubApiError),
    ],
)
def test_error_statuses_raise_specific_exceptions(
    make_client: Callable[..., GitHubClient], make_response, status: int, expected
) -> None:
    """Each status maps onto the most specific exception available."""
    client = make_client([make_response({"message": "boom"}, status_code=status)])

    with pytest.raises(expected) as excinfo:
        client.get("/repos/o/r")

    assert excinfo.value.status_code == status
    assert "boom" in str(excinfo.value)


def test_exhausted_rate_limit_raises_rate_limit_error(
    make_client: Callable[..., GitHubClient], make_response
) -> None:
    """A 403 with no remaining quota is a rate limit, not an auth failure."""
    client = make_client(
        [
            make_response(
                {"message": "API rate limit exceeded"},
                status_code=403,
                headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Limit": "60"},
            )
        ]
    )

    with pytest.raises(RateLimitError) as excinfo:
        client.get("/repos/o/r")

    assert excinfo.value.rate_limit is not None
    assert excinfo.value.rate_limit.remaining == 0


def test_status_429_raises_rate_limit_error(
    make_client: Callable[..., GitHubClient], make_response
) -> None:
    """Explicit throttling is reported as a rate limit."""
    client = make_client([make_response({"message": "slow down"}, status_code=429)])

    with pytest.raises(RateLimitError):
        client.get("/repos/o/r")


def test_error_message_never_contains_the_token(
    transport, make_response
) -> None:
    """A failure must not leak credentials into logs or tracebacks."""
    client = GitHubClient(
        credentials=TokenCredentials(token=SECRET), transport=transport
    )
    transport.responses.append(make_response({"message": "bad"}, status_code=401))

    with pytest.raises(AuthenticationError) as excinfo:
        client.get("/repos/o/r")

    assert SECRET not in str(excinfo.value)
    assert SECRET not in repr(excinfo.value)


def test_non_json_error_body_is_tolerated(
    make_client: Callable[..., GitHubClient]
) -> None:
    """An HTML error page must not cause a second, confusing failure."""
    client = make_client(
        [HttpResponse(status_code=502, body="<html>bad gateway</html>", url="u")]
    )

    with pytest.raises(GitHubApiError, match="Unknown error"):
        client.get("/repos/o/r")


def test_invalid_json_success_body_raises(
    make_client: Callable[..., GitHubClient]
) -> None:
    """A 200 with a malformed body is an error, not silently None."""
    client = make_client([HttpResponse(status_code=200, body="{not json", url="u")])

    with pytest.raises(GitHubApiError, match="not valid JSON"):
        client.get_json("/repos/o/r")


def test_transport_failures_propagate(transport) -> None:
    """A transport error is not swallowed."""
    transport.error = TransportError("network down")
    client = GitHubClient(transport=transport)

    with pytest.raises(TransportError, match="network down"):
        client.get("/repos/o/r")


# ---------------------------------------------------------------------------
# responses, rate limit, pagination
# ---------------------------------------------------------------------------


def test_header_lookup_is_case_insensitive() -> None:
    """HTTP header names are not case sensitive."""
    response = HttpResponse(200, {"X-RateLimit-Remaining": "12"}, "{}", "u")

    assert response.header("x-ratelimit-remaining") == "12"
    assert response.header("X-RATELIMIT-REMAINING") == "12"
    assert response.header("absent") is None


def test_rate_limit_is_parsed_from_headers(make_response) -> None:
    """Rate limit headers are surfaced as a model."""
    response = make_response(
        {},
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Used": "1",
            "X-RateLimit-Reset": "1900000000",
        },
    )
    rate_limit = response.rate_limit()

    assert rate_limit.limit == 5000
    assert rate_limit.remaining == 4999
    assert rate_limit.is_exhausted is False
    assert rate_limit.reset_at is not None


def test_missing_rate_limit_headers_are_tolerated(make_response) -> None:
    """Absent headers produce empty values rather than errors."""
    rate_limit = make_response({}).rate_limit()

    assert rate_limit.limit is None
    assert rate_limit.is_exhausted is False


def test_empty_body_decodes_to_none() -> None:
    """A 204-style empty body is not a JSON error."""
    assert HttpResponse(200, {}, "", "u").json() is None


def test_parse_link_header_extracts_relations() -> None:
    """The Link header is parsed into relation to URL pairs."""
    header = (
        '<https://api.github.com/repos/o/r/pulls?page=2>; rel="next", '
        '<https://api.github.com/repos/o/r/pulls?page=9>; rel="last"'
    )
    links = parse_link_header(header)

    assert links["next"] == "https://api.github.com/repos/o/r/pulls?page=2"
    assert links["last"] == "https://api.github.com/repos/o/r/pulls?page=9"


@pytest.mark.parametrize("value", [None, "", "garbage", "<no-rel>"])
def test_parse_link_header_tolerates_malformed_input(value) -> None:
    """A malformed Link header yields no relations rather than raising."""
    assert parse_link_header(value) == {}


def test_pagination_follows_next_links(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """Pages are walked until no next relation remains."""
    page_one = make_response(
        [{"n": 1}],
        headers={
            "Link": '<https://api.github.com/items?page=2>; rel="next"',
        },
    )
    page_two = make_response([{"n": 2}])
    client = make_client([page_one, page_two])

    items = client.paginate_items("/items")

    assert items == [{"n": 1}, {"n": 2}]
    assert transport.urls == [
        "https://api.github.com/items",
        "https://api.github.com/items?page=2",
    ]


def test_pagination_is_bounded_by_max_pages(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """A Link header that always points onward cannot loop forever."""
    always_next = {"Link": '<https://api.github.com/items?page=2>; rel="next"'}
    client = make_client(
        [make_response([{"n": index}], headers=always_next) for index in range(10)]
    )

    items = client.paginate_items("/items", max_pages=3)

    assert len(items) == 3
    assert len(transport.requests) == 3


def test_pagination_is_lazy(
    make_client: Callable[..., GitHubClient], transport, make_response
) -> None:
    """A caller that stops early does not trigger further requests."""
    page_one = make_response(
        [{"n": 1}], headers={"Link": '<https://api.github.com/items?page=2>; rel="next"'}
    )
    client = make_client([page_one, make_response([{"n": 2}])])

    first = next(iter(client.paginate("/items")))

    assert first == [{"n": 1}]
    assert len(transport.requests) == 1


def test_pagination_rejects_non_array_payloads(
    make_client: Callable[..., GitHubClient], make_response
) -> None:
    """An object where a collection was expected is an explicit error."""
    client = make_client([make_response({"message": "not a list"})])

    with pytest.raises(GitHubApiError, match="Expected a JSON array"):
        client.paginate_items("/items")


# ---------------------------------------------------------------------------
# request representation must not leak credentials
# ---------------------------------------------------------------------------


def test_http_request_repr_redacts_authorization() -> None:
    """The token must not appear in the request's repr."""
    request = HttpRequest(
        method="GET",
        url="https://api.github.com/repos/o/r",
        headers={"Authorization": f"Bearer {SECRET}"},
    )

    rendered = repr(request)

    assert SECRET not in rendered
    assert REDACTED in rendered
    # The header's presence is still visible; only its value is removed.
    assert "Authorization" in rendered


def test_http_request_str_redacts_authorization() -> None:
    """str() falls through to the redacting repr."""
    request = HttpRequest(
        method="GET", url="https://api.github.com", headers={"Authorization": SECRET}
    )

    assert SECRET not in str(request)
    assert SECRET not in f"{request}"
    assert SECRET not in "{}".format(request)


@pytest.mark.parametrize(
    "header",
    ["Authorization", "Proxy-Authorization", "Cookie", "Set-Cookie", "X-API-Key"],
)
def test_all_sensitive_headers_are_redacted(header: str) -> None:
    """Every header named in SENSITIVE_HEADERS is redacted."""
    request = HttpRequest(method="GET", url="u", headers={header: SECRET})

    assert SECRET not in repr(request)


@pytest.mark.parametrize(
    "header", ["authorization", "AUTHORIZATION", "AuThOrIzAtIoN"]
)
def test_sensitive_header_matching_is_case_insensitive(header: str) -> None:
    """HTTP header names are case-insensitive, so redaction must be too."""
    request = HttpRequest(method="GET", url="u", headers={header: SECRET})

    assert SECRET not in repr(request)


def test_non_sensitive_headers_remain_visible() -> None:
    """Redaction is targeted: ordinary headers stay debuggable."""
    request = HttpRequest(
        method="GET",
        url="u",
        headers={"Accept": "application/vnd.github+json", "Authorization": SECRET},
    )

    rendered = repr(request)

    assert "application/vnd.github+json" in rendered
    assert SECRET not in rendered


def test_headers_excluded_from_generated_dataclass_repr() -> None:
    """The second, independent guard: the field itself opts out of repr.

    If the explicit __repr__ were ever removed, the generated one must still not
    render header values.
    """
    fields = {f.name: f for f in dataclasses.fields(HttpRequest)}

    assert fields["headers"].repr is False


def test_redaction_does_not_alter_the_headers_that_get_sent() -> None:
    """Redaction is display-only; the real value must still be transmitted."""
    request = HttpRequest(
        method="GET", url="u", headers={"Authorization": f"Bearer {SECRET}"}
    )

    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert request.redacted_headers()["Authorization"] == REDACTED


def test_redact_headers_does_not_mutate_its_input() -> None:
    """The helper returns a copy rather than editing the caller's mapping."""
    original = {"Authorization": SECRET, "Accept": "application/json"}

    redacted = redact_headers(original)

    assert original["Authorization"] == SECRET
    assert redacted["Authorization"] == REDACTED
    assert redacted["Accept"] == "application/json"


def test_real_request_built_by_client_does_not_leak_the_token(
    transport, make_response
) -> None:
    """End to end: a request the client actually built is safe to log."""
    client = GitHubClient(
        credentials=TokenCredentials(token=SECRET), transport=transport
    )
    transport.responses.append(make_response({}))

    client.get("/repos/o/r")
    sent = transport.last_request

    # The header really was sent...
    assert sent.headers["Authorization"] == f"Bearer {SECRET}"
    # ...but no rendering of the request discloses it.
    assert SECRET not in repr(sent)
    assert SECRET not in str(sent)


def test_sensitive_header_set_covers_authorization() -> None:
    """A regression guard on the constant itself."""
    assert "authorization" in SENSITIVE_HEADERS
    assert all(name == name.lower() for name in SENSITIVE_HEADERS), (
        "entries must be lowercase for case-insensitive matching to work"
    )


# ---------------------------------------------------------------------------
# transport wiring
# ---------------------------------------------------------------------------


def test_default_transport_is_urllib_based() -> None:
    """The client works with no transport supplied."""
    client = GitHubClient()

    assert isinstance(client._transport, UrllibTransport)  # noqa: SLF001


def test_clients_do_not_share_state(transport, make_response) -> None:
    """Two clients are independently configured; there is no global state."""
    first = GitHubClient(transport=transport, base_url="https://a.example.com")
    second = GitHubClient(transport=transport, base_url="https://b.example.com")

    assert first.base_url != second.base_url
    assert first.credentials is not second.credentials

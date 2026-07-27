"""Guards that the GitHub layer stays additive.

The v0.1.1 sprint rule is that the execution engine, runtime and state machine
are untouched. These tests encode that rule so a later change cannot quietly
couple the two halves together.
"""

from __future__ import annotations

import inspect

from forge import runner, states, task, validation
from forge.github import GitHub, GitHubClient

CORE_MODULES = (runner, states, task, validation)


def test_core_modules_do_not_import_the_github_layer() -> None:
    """No execution-engine module may depend on the integration layer."""
    for module in CORE_MODULES:
        source = inspect.getsource(module)
        assert "forge.github" not in source, (
            f"{module.__name__} imports the GitHub layer; the execution engine "
            "must stay independent of it."
        )


def test_github_layer_does_not_touch_the_state_machine() -> None:
    """The integration layer must not reference execution states."""
    import forge.github.branches as branches
    import forge.github.client as client
    import forge.github.commits as commits
    import forge.github.pull_requests as pull_requests
    import forge.github.repositories as repositories

    for module in (client, repositories, branches, pull_requests, commits):
        source = inspect.getsource(module)
        assert "StateMachine" not in source
        assert "TaskRunner" not in source


def test_importing_github_does_not_run_network_or_io() -> None:
    """Constructing the layer performs no request on its own."""
    github = GitHub(GitHubClient())

    assert github.is_read_only is True
    assert github.client.base_url.startswith("https://")


def test_github_errors_extend_the_existing_forge_hierarchy() -> None:
    """Integration errors are catchable as ForgeError, without changing it."""
    from forge.errors import ForgeError
    from forge.github.client import GitHubError

    assert issubclass(GitHubError, ForgeError)

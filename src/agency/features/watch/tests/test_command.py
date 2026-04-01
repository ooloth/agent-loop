"""Tests for watch command guards."""

import pytest

from agency.domain.errors import InvariantError
from agency.domain.ports.tests.stubs import StubAgent
from agency.features.tests.context import make_ctx
from agency.features.watch.command import WatchAgents, cmd_watch


def _make_agents() -> WatchAgents:
    return WatchAgents(analysis=StubAgent(), coding=StubAgent(), review=StubAgent())


class TestCmdWatchInvariants:
    def test_zero_interval_raises(self) -> None:
        ctx = make_ctx()
        with pytest.raises(InvariantError, match="interval should never be < 1"):
            cmd_watch(ctx, _make_agents(), interval=0, max_open_issues=5)

    def test_zero_max_open_issues_raises(self) -> None:
        ctx = make_ctx()
        with pytest.raises(InvariantError, match="max_open_issues should never be < 1"):
            cmd_watch(ctx, _make_agents(), interval=60, max_open_issues=0)

"""Tests for CLI dispatch."""

import argparse

import pytest

from agency.domain.config import Config
from agency.domain.errors import InvariantError
from agency.entrypoints.cli import _dispatch
from agency.features.tests.context import make_ctx


class TestDispatch:
    def test_unknown_command_raises(self) -> None:
        args = argparse.Namespace(command="bogus")
        ctx = make_ctx()
        with pytest.raises(InvariantError, match="unknown command should never reach _dispatch"):
            _dispatch(args, ctx, Config())

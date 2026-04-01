"""Tests for CLI dispatch and argument validation."""

import argparse

import pytest

from agency.domain.config import Config
from agency.domain.errors import InvariantError
from agency.entrypoints.cli import _build_parser, _dispatch
from agency.features.tests.context import make_ctx


class TestDispatch:
    def test_unknown_command_raises(self) -> None:
        args = argparse.Namespace(command="bogus")
        ctx = make_ctx()
        with pytest.raises(InvariantError, match="unknown command should never reach _dispatch"):
            _dispatch(args, ctx, Config())


class TestPromptValidation:
    def test_fix_blank_prompt_rejected(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["fix", "--prompt", ""])

    def test_ralph_blank_prompt_rejected(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["ralph", "--prompt", ""])

    def test_fix_valid_prompt_accepted(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["fix", "--prompt", "add type hints"])
        assert args.prompt == "add type hints"

    def test_ralph_valid_prompt_accepted(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["ralph", "--prompt", "add type hints"])
        assert args.prompt == "add type hints"

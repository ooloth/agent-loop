"""Tests for planning model resolution."""

import os
from unittest.mock import patch

from agent_loop.domain.config import DEFAULT_PLANNING_MODEL, resolve_planning_model


class TestResolvePlanningModel:
    def test_cli_flag_wins_over_everything(self) -> None:
        assert (
            resolve_planning_model(config_model="from-config", cli_model="from-cli") == "from-cli"
        )

    def test_config_wins_over_env_and_default(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_DEFAULT_OPUS_MODEL": "from-env"}):
            assert (
                resolve_planning_model(config_model="from-config", cli_model=None) == "from-config"
            )

    def test_env_var_wins_over_default(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_DEFAULT_OPUS_MODEL": "from-env"}):
            assert resolve_planning_model(config_model=None, cli_model=None) == "from-env"

    def test_falls_back_to_hardcoded_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert (
                resolve_planning_model(config_model=None, cli_model=None) == DEFAULT_PLANNING_MODEL
            )

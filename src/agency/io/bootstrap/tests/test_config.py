"""Tests for config loading."""

from pathlib import Path

import pytest

from agency.domain.config import Config
from agency.domain.errors import AgentLoopError
from agency.io.bootstrap.config import load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        config = load_config(tmp_path)
        assert config == Config()
        assert config.max_iterations == 5
        assert config.context == ""
        assert config.analyze_prompt is None
        assert config.fix_prompt_template is None
        assert config.review_prompt is None

    def test_overrides_from_yaml(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: 10\ncontext: My project\n")
        config = load_config(tmp_path)
        assert config.max_iterations == 10
        assert config.context == "My project"

    def test_null_values_fall_back_to_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: null\ncontext: null\n")
        config = load_config(tmp_path)
        assert config.max_iterations == 5
        assert config.context == ""

    def test_unknown_keys_ignored(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: 3\nunknown_key: hello\n")
        config = load_config(tmp_path)
        assert config.max_iterations == 3

    def test_empty_yaml_returns_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("")
        config = load_config(tmp_path)
        assert config == Config()

    def test_prompt_overrides(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text(
            "analyze_prompt: custom analyze\nreview_prompt: custom review\n"
        )
        config = load_config(tmp_path)
        assert config.analyze_prompt == "custom analyze"
        assert config.review_prompt == "custom review"
        assert config.fix_prompt_template is None

    def test_invalid_type_for_int_field(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: five\n")
        with pytest.raises(AgentLoopError, match=r"max_iterations.*expected int.*got str"):
            load_config(tmp_path)

    def test_invalid_type_for_str_field(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("context: 42\n")
        with pytest.raises(AgentLoopError, match=r"context.*expected str.*got int"):
            load_config(tmp_path)

    def test_invalid_type_for_optional_str_field(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("analyze_prompt: [1, 2, 3]\n")
        with pytest.raises(AgentLoopError, match=r"analyze_prompt.*expected str.*got list"):
            load_config(tmp_path)

    def test_multiple_type_errors_reported_together(self, tmp_path: Path) -> None:
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: five\ncontext: 42\n")
        with pytest.raises(AgentLoopError, match="max_iterations") as exc_info:
            load_config(tmp_path)
        assert "context" in str(exc_info.value)

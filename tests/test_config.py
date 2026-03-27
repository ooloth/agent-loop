"""Tests for config loading."""

from pathlib import Path

from agent_loop.domain.config import Config
from agent_loop.io.bootstrap.config import load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path: Path):
        config = load_config(tmp_path)
        assert config == Config()
        assert config.max_iterations == 5
        assert config.context == ""
        assert config.analyze_prompt is None
        assert config.fix_prompt_template is None
        assert config.review_prompt is None

    def test_overrides_from_yaml(self, tmp_path: Path):
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: 10\ncontext: My project\n")
        config = load_config(tmp_path)
        assert config.max_iterations == 10
        assert config.context == "My project"

    def test_null_values_fall_back_to_defaults(self, tmp_path: Path):
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: null\ncontext: null\n")
        config = load_config(tmp_path)
        assert config.max_iterations == 5
        assert config.context == ""

    def test_unknown_keys_ignored(self, tmp_path: Path):
        (tmp_path / ".agent-loop.yml").write_text("max_iterations: 3\nunknown_key: hello\n")
        config = load_config(tmp_path)
        assert config.max_iterations == 3

    def test_empty_yaml_returns_defaults(self, tmp_path: Path):
        (tmp_path / ".agent-loop.yml").write_text("")
        config = load_config(tmp_path)
        assert config == Config()

    def test_prompt_overrides(self, tmp_path: Path):
        (tmp_path / ".agent-loop.yml").write_text(
            "analyze_prompt: custom analyze\nreview_prompt: custom review\n"
        )
        config = load_config(tmp_path)
        assert config.analyze_prompt == "custom analyze"
        assert config.review_prompt == "custom review"
        assert config.fix_prompt_template is None

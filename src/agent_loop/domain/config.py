import os
from dataclasses import dataclass

DEFAULT_PLANNING_MODEL = "claude-opus-4-6"


def resolve_planning_model(config_model: str | None, cli_model: str | None) -> str:
    """Resolve the planning model: CLI flag > config > env var > hardcoded default."""
    if cli_model:
        return cli_model
    if config_model:
        return config_model
    return os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", DEFAULT_PLANNING_MODEL)


@dataclass(frozen=True)
class Config:
    """Settings loaded from .agent-loop.yml.

    All fields have defaults. Optional prompt overrides are None when absent —
    pipelines fall back to their own built-in defaults in that case.
    """

    max_iterations: int = 5
    context: str = ""

    # Per-role agent settings — model None means "use claude CLI default".
    planning_agent_model: str | None = None
    planning_agent_effort: str = "high"
    coding_agent_model: str | None = None
    coding_agent_effort: str = "high"
    review_agent_model: str | None = None
    review_agent_effort: str = "high"
    analysis_agent_model: str | None = None
    analysis_agent_effort: str = "high"

    # Prompt overrides — None means "use the built-in default".
    analyze_prompt: str | None = None
    fix_prompt_template: str | None = None
    review_prompt: str | None = None

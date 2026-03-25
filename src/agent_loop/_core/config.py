from pathlib import Path

import yaml

from agent_loop._core.types import Config

# Structural defaults only — prompt text lives with its feature module and is
# used as the fallback when not overridden via .agent-loop.yml. This avoids a
# circular import: config → analyze.prompts → analyze.__init__ → analyze.command → _core.
DEFAULT_CONFIG: Config = {
    "max_iterations": 5,
    "context": "",
}


def load_config(project_dir: Path) -> Config:
    """Load config from .agent-loop.yml in the project directory, merged with defaults."""
    config = dict(DEFAULT_CONFIG)
    config_file = project_dir / ".agent-loop.yml"
    if config_file.exists():
        with open(config_file) as f:
            # Filter out null values so they fall back to defaults rather than overriding them
            overrides = {
                k: v for k, v in (yaml.safe_load(f) or {}).items() if v is not None
            }
        config.update(overrides)
    return config  # type: ignore[return-value]

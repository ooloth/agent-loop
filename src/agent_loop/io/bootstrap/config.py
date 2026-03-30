"""Load and merge .agent-loop.yml configuration."""

from pathlib import Path

import yaml

from agent_loop.domain.config import Config
from agent_loop.io.observability.logging import log


def load_config(project_dir: Path) -> Config:
    """Load config from .agent-loop.yml in the project directory, merged with defaults.

    Only keys that exist on Config and have non-None values in the YAML file are
    applied. Unknown keys are silently ignored. Absent or null keys fall back to
    Config's built-in defaults.
    """
    config_file = project_dir / ".agent-loop.yml"
    if not config_file.exists():
        config = Config()
        log.debug("Config: no .agent-loop.yml found, using defaults: %s", config)
        return config

    with config_file.open() as f:
        raw = yaml.safe_load(f) or {}

    # Keep only keys that Config knows about, and drop nulls
    valid_fields = {f.name for f in Config.__dataclass_fields__.values()}
    overrides = {k: v for k, v in raw.items() if k in valid_fields and v is not None}
    config = Config(**overrides)
    log.debug("Config: %s", config)
    return config

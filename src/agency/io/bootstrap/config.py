"""Load and merge .agent-loop.yml configuration."""

import dataclasses
from pathlib import Path
from typing import get_args, get_origin

import yaml

from agency.domain.config import Config
from agency.domain.errors import AgentLoopError
from agency.io.observability.logging import log


def load_config(project_dir: Path) -> Config:
    """Load config from .agent-loop.yml in the project directory, merged with defaults.

    Only keys that exist on Config and have non-None values in the YAML file are
    applied. Unknown keys are silently ignored. Absent or null keys fall back to
    Config's built-in defaults. Type mismatches raise AgentLoopError.
    """
    config_file = project_dir / ".agent-loop.yml"
    if not config_file.exists():
        config = Config()
        log.debug("Config: no .agent-loop.yml found, using defaults: %s", config)
        return config

    with config_file.open() as f:
        raw = yaml.safe_load(f) or {}

    # Keep only keys that Config knows about, and drop nulls
    valid_fields = {f.name for f in dataclasses.fields(Config)}
    overrides = {k: v for k, v in raw.items() if k in valid_fields and v is not None}

    _validate_types(overrides)

    config = Config(**overrides)
    log.debug("Config: %s", config)
    return config


def _validate_types(overrides: dict[str, object]) -> None:
    """Check that each override matches the type declared on Config.

    Collects all violations and raises a single AgentLoopError listing them all.
    """
    field_types = {f.name: f.type for f in dataclasses.fields(Config)}
    errors: list[str] = []

    for key, value in overrides.items():
        expected = _concrete_type(field_types[key])
        if not isinstance(value, expected):
            errors.append(f"  {key}: expected {expected.__name__}, got {type(value).__name__}")

    if errors:
        detail = "\n".join(errors)
        msg = f"Invalid config types in .agent-loop.yml:\n{detail}"
        raise AgentLoopError(msg)


def _concrete_type(annotation: object) -> type:
    """Extract the concrete type from a type annotation.

    str | None → str, int → int, str → str.
    """
    if get_origin(annotation) is not None:
        # Union type (e.g. str | None) — return the non-None arg
        args = [a for a in get_args(annotation) if a is not type(None)]
        return args[0]  # type: ignore[return-value]
    if not isinstance(annotation, type):
        msg = f"Unexpected annotation type: {annotation}"
        raise TypeError(msg)
    return annotation

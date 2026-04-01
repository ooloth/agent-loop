"""Domain exceptions raised by adapters and pipelines, caught at the CLI boundary."""


class InvariantError(RuntimeError):
    """A programmer assumption was found to be false at runtime."""


def invariant(condition: bool, rule: str, **values: object) -> None:  # noqa: FBT001
    """Raise InvariantError if condition is False.

    Use for programmer assumptions — conditions that should be impossible if the code is wired
    correctly. A violation should always indicate a bug. Do not use to validate user/external
    input (parse that at the I/O boundary instead).

    rule: state the violated constraint using "should never", e.g. "max should never be < 1"

    values: variables from the condition; if present, will be included in the error message
        as key=value pairs to make debugging the bad runtime state easier - for example:
        invariant(max >= 1, "...", max=max) → InvariantError: max should never be < 1 (max=0)
    """
    if not condition:
        detail = ", ".join(f"{k}={v!r}" for k, v in values.items())
        message = f"{rule} ({detail})" if detail else rule
        raise InvariantError(message)


class AgentLoopError(Exception):
    """Base for all agent-loop errors. CLI catches this to exit cleanly."""


class AgentError(AgentLoopError):
    """The AI agent backend failed to produce a response."""

    def __init__(self, stderr: str = "") -> None:
        """Store captured stderr and build a human-readable message."""
        self.stderr = stderr
        detail = f"\n{stderr.rstrip()}" if stderr else ""
        super().__init__(f"Agent failed{detail}")

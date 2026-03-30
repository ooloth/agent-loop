"""Domain exceptions raised by adapters and pipelines, caught at the CLI boundary."""


class AgentLoopError(Exception):
    """Base for all agent-loop errors. CLI catches this to exit cleanly."""


class AgentError(AgentLoopError):
    """The AI agent backend failed to produce a response."""

    def __init__(self, stderr: str = "") -> None:
        """Store captured stderr and build a human-readable message."""
        self.stderr = stderr
        detail = f"\n{stderr.rstrip()}" if stderr else ""
        super().__init__(f"Agent failed{detail}")

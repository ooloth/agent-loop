"""Errors raised by the analyze pipeline."""

from agency.domain.errors import AgentLoopError


class AnalysisParseError(AgentLoopError):
    """The analyze pipeline could not parse the agent's response as JSON."""

    def __init__(self, raw_response: str, *, reason: str = "invalid JSON") -> None:
        """Store the raw response and build a truncated preview message."""
        self.raw_response = raw_response
        # Show a truncated preview in the message
        max_preview = 200
        preview = (
            raw_response[:max_preview] + "…" if len(raw_response) > max_preview else raw_response
        )
        super().__init__(f"Failed to parse agent response ({reason}):\n{preview}")

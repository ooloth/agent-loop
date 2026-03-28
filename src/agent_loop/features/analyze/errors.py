from agent_loop.domain.errors import AgentLoopError


class AnalysisParseError(AgentLoopError):
    """The analyze pipeline could not parse the agent's response as JSON."""

    def __init__(self, raw_response: str, *, reason: str = "invalid JSON") -> None:
        self.raw_response = raw_response
        # Show a truncated preview in the message
        preview = raw_response[:200] + "…" if len(raw_response) > 200 else raw_response
        super().__init__(f"Failed to parse agent response ({reason}):\n{preview}")

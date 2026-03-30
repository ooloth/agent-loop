"""AgentBackend port — the AI execution interface."""

from typing import Protocol


class AgentBackend(Protocol):
    """Run a prompt and return the response. Abstracts the AI provider."""

    def run(self, prompt: str) -> str: ...


class InteractiveAgentBackend(Protocol):
    """Launch an interactive session that hands control to the user."""

    def session(self, *, system_prompt: str, initial_message: str | None = None) -> None: ...

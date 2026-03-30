"""AgentBackend port — the AI execution interface.

Abstracts "send a prompt, get a response" so the engine and pipelines are
independent of which AI provider or invocation method is used.

Known adapters:
- ClaudeCliBackend (io/adapters/claude_cli.py) — runs the claude CLI as a subprocess
"""

from typing import Protocol


class AgentBackend(Protocol):
    """Run a prompt and return the response. Abstracts the AI provider.

    Contract:
    - run() blocks until the response is complete.
    - Returns the raw response as a string. Callers parse structure (JSON,
      verdict keywords, etc.) from the response.
    - Raises on unrecoverable failure. Does not return empty string as a
      sentinel for failure — callers may legitimately receive an empty response.
    - Tool access (read-only vs. edit) is a backend concern, configured at
      construction time — not passed per call. Construct two instances with
      different access levels for implement vs. review roles.
    """

    def run(self, prompt: str) -> str:
        """Run a prompt and return the agent's text response."""
        ...


class InteractiveAgentBackend(Protocol):
    """Launch an interactive session that hands control to the user.

    Contract:
    - session() hands control of the terminal to the user for an interactive
      conversation. Used by the plan pipeline.
    - Blocks until the user ends the conversation. Does not capture or return
      the conversation — the agent writes artifacts (e.g. plan files) directly
      to disk during the session.
    - System prompt and optional initial message are passed at call time,
      not at construction.
    """

    def session(self, *, system_prompt: str, initial_message: str | None = None) -> None:
        """Start an interactive terminal session with the given system prompt."""
        ...

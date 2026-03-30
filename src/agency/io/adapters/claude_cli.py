"""AgentBackend backed by the Claude CLI."""

import subprocess
from pathlib import Path

from agency.domain.errors import AgentError
from agency.io.errors import SubprocessError
from agency.io.observability.logging import log
from agency.io.transports.process import run

# Read-only tools for analysis and review (no filesystem writes or shell execution)
READ_ONLY_TOOLS = "Read,Glob,Grep"
# Tools needed to implement fixes (scoped to project dir via cwd)
EDIT_TOOLS = "Read,Write,Edit,MultiEdit,Glob,Grep,Bash"


class ClaudeCliBackend:
    """AgentBackend + InteractiveAgentBackend that calls the claude CLI.

    Implements both protocols:
    - run(prompt) -> str  — non-interactive, captures output (claude -p)
    - session(...)        — interactive, hands terminal to user (claude)
    """

    def __init__(
        self,
        project_dir: Path,
        allowed_tools: str = EDIT_TOOLS,
        model: str | None = None,
        effort: str = "high",
    ) -> None:
        """Configure the CLI backend with project dir, tools, and model settings."""
        self._project_dir = project_dir
        self._allowed_tools = allowed_tools
        self._model = model
        self._effort = effort

    def _common_args(self) -> list[str]:
        """Args shared by both run and session modes."""
        args = ["--effort", self._effort]
        if self._model:
            args.extend(["--model", self._model])
        return args

    def run(self, prompt: str) -> str:
        """Run a prompt non-interactively and return captured output."""
        log.debug(
            "Agent call: %d char prompt, model=%s, effort=%s",
            len(prompt),
            self._model,
            self._effort,
        )
        try:
            result = run(
                [
                    "claude",
                    "-p",
                    prompt,
                    "--allowedTools",
                    self._allowed_tools,
                    *self._common_args(),
                ],
                cwd=self._project_dir,
            )
        except SubprocessError as exc:
            raise AgentError(stderr=exc.stderr) from exc
        log.debug("Agent response: %d chars", len(result))
        return result

    def session(self, *, system_prompt: str, initial_message: str | None = None) -> None:
        """Launch an interactive Claude session in the user's terminal."""
        cmd = [
            "claude",
            "--append-system-prompt",
            system_prompt,
            *self._common_args(),
        ]
        if initial_message:
            cmd.append(initial_message)

        subprocess.run(cmd, cwd=self._project_dir, check=False)  # noqa: S603

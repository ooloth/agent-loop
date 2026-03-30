import subprocess
from pathlib import Path

from agent_loop.domain.errors import AgentError
from agent_loop.io.errors import SubprocessError
from agent_loop.io.transports.process import run

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
        try:
            return run(
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

    def session(self, *, system_prompt: str, initial_message: str | None = None) -> None:
        cmd = [
            "claude",
            "--append-system-prompt",
            system_prompt,
            *self._common_args(),
        ]
        if initial_message:
            cmd.append(initial_message)

        subprocess.run(cmd, cwd=self._project_dir)

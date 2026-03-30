"""IO-layer exceptions for infrastructure concerns (subprocesses, network, etc.)."""

from agent_loop.domain.errors import AgentLoopError


class SubprocessError(AgentLoopError):
    """A subprocess (git, gh, etc.) returned a non-zero exit code."""

    def __init__(self, cmd: str, stdout: str = "", stderr: str = "") -> None:
        """Store the failed command and its output."""
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr
        parts = [f"Command failed: {cmd}"]
        if stderr:
            parts.append(f"stderr:\n{stderr.rstrip()}")
        if stdout:
            parts.append(f"stdout:\n{stdout.rstrip()}")
        super().__init__("\n".join(parts))

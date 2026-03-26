import subprocess
import sys
from pathlib import Path

# Read-only tools for analysis and review (no filesystem writes or shell execution)
READ_ONLY_TOOLS = "Read,Glob,Grep"
# Tools needed to implement fixes (scoped to project dir via cwd)
EDIT_TOOLS = "Read,Write,Edit,MultiEdit,Glob,Grep,Bash"


class ClaudeCliBackend:
    """AgentBackend that calls the claude CLI as a subprocess."""

    def __init__(self, project_dir: Path, allowed_tools: str = EDIT_TOOLS) -> None:
        self._project_dir = project_dir
        self._allowed_tools = allowed_tools

    def run(self, prompt: str) -> str:
        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", self._allowed_tools],
            capture_output=True,
            text=True,
            cwd=self._project_dir,
        )
        if result.returncode != 0:
            print(f"Claude failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        return result.stdout.strip()

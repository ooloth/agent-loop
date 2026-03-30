"""Thin subprocess wrapper with structured error handling."""

import subprocess
from pathlib import Path

from agent_loop.io.errors import SubprocessError


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    cwd: Path | None = None,
) -> str:
    """Run a subprocess command and return stdout.

    Raises SubprocessError on non-zero exit (when check=True) instead of
    calling sys.exit, so callers higher up can decide how to handle it.
    """
    result = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd, check=False)  # noqa: S603
    if check and result.returncode != 0:
        raise SubprocessError(
            cmd=" ".join(cmd), stdout=result.stdout or "", stderr=result.stderr or ""
        )
    return result.stdout.strip() if capture else ""

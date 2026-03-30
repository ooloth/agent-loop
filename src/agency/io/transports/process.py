"""Thin subprocess wrapper with structured error handling."""

import subprocess
import time
from pathlib import Path

from agency.io.errors import SubprocessError
from agency.io.observability.logging import log


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
    cmd_str = " ".join(cmd)
    log.debug("$ %s", cmd_str)
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd, check=False)  # noqa: S603
    elapsed = time.monotonic() - t0
    log.debug("  → exit %d (%.1fs)", result.returncode, elapsed)
    if check and result.returncode != 0:
        raise SubprocessError(cmd=cmd_str, stdout=result.stdout or "", stderr=result.stderr or "")
    return result.stdout.strip() if capture else ""

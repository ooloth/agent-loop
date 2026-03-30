"""Timestamped console and file logging for CLI output."""

import logging
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger("agency")

LOG_FORMAT = "[%(asctime)s] %(message)s"
CONSOLE_DATE_FORMAT = "%H:%M:%S"
FILE_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_RETENTION_DAYS = 14


def configure_logging(
    *,
    verbose: bool = False,
    command: str,
    project_dir: Path,
    log_file: Path | None = None,
) -> None:
    """Set up the agency logger for timestamped console and file output.

    Always writes to stderr and to <project_dir>/.logs/<date>-<command>.log.
    Warnings and errors also go to a companion .err.log (created on demand).
    If log_file is provided, it replaces the default log directory target.
    """
    log.setLevel(logging.DEBUG if verbose else logging.INFO)

    # stderr
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=CONSOLE_DATE_FORMAT))
    log.addHandler(stderr_handler)

    # file
    target = log_file or _default_log_path(project_dir, command)
    target.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(target)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=FILE_DATE_FORMAT))
    log.addHandler(file_handler)

    # error file (WARNING+ only, created on first warning via delay=True)
    err_path = target.with_suffix(".err.log")
    err_handler = logging.FileHandler(err_path, delay=True)
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=FILE_DATE_FORMAT))
    log.addHandler(err_handler)

    _log_run_banner(command)
    _cleanup_old_logs(target.parent)


def _default_log_path(project_dir: Path, command: str) -> Path:
    """Build the default log file path: <project_dir>/.logs/<date>-<command>.log."""
    today = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
    return project_dir / ".logs" / f"{today}-{command}.log"


def _log_run_banner(command: str) -> None:
    """Append a visual separator marking the start of a new run."""
    now = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    banner = f"  {command} · {now}"
    separator = "═" * max(len(banner) + 4, 58)
    # Write directly to open file handlers only (skip stderr and delayed err handler)
    for handler in log.handlers:
        if isinstance(handler, logging.FileHandler) and handler.stream is not None:
            handler.stream.write(f"\n{separator}\n{banner}\n{separator}\n\n")
            handler.stream.flush()


def _cleanup_old_logs(log_dir: Path, retention_days: int = LOG_RETENTION_DAYS) -> None:
    """Delete .log and .err.log files older than retention_days."""
    if not log_dir.is_dir():
        return
    cutoff = datetime.now(UTC).timestamp() - (retention_days * 86400)
    for path in log_dir.glob("*.log"):
        if path.stat().st_mtime < cutoff:
            path.unlink()


def log_step(msg: str, *, last: bool = False) -> None:
    """Log a step under the current issue."""
    connector = "└──" if last else "├──"
    log.info("%s %s", connector, msg)


def log_detail(msg: str, *, last_step: bool = False) -> None:
    """Log a detail line under the current step."""
    rail = " " if last_step else "│"
    log.info("%s      %s", rail, msg)

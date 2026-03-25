from datetime import datetime


def log(msg: str, prefix: str = "") -> None:
    """Log a timestamped message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {prefix}{msg}")


def log_step(msg: str, last: bool = False) -> None:
    """Log a step under the current issue."""
    connector = "└──" if last else "├──"
    log(f"{connector} {msg}")


def log_detail(msg: str, last_step: bool = False) -> None:
    """Log a detail line under the current step."""
    rail = " " if last_step else "│"
    log(f"{rail}      {msg}")

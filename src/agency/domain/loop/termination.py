"""Termination conditions — when should the loop stop?

Each condition scans an agent's text response for a signal that work is
complete. Used by loop strategies to decide whether to continue iterating.
"""

import re
from typing import Protocol


class TerminationCondition(Protocol):
    """Decides whether an agent response signals that work is complete."""

    def is_met(self, response: str) -> bool:
        """Return True if the response signals completion."""
        ...


class ReviewApproval:
    """The response contains an LGTM verdict from a reviewer.

    Scans for LGTM as a whole word, case-insensitive. Used by
    AntagonisticStrategy to detect reviewer approval.
    """

    def is_met(self, response: str) -> bool:
        """Return True if the response contains an LGTM verdict."""
        return bool(re.search(r"\bLGTM\b", response, re.IGNORECASE))


class OutputSignal:
    """The response contains a completion token on its own line.

    The token must be the only non-whitespace content on its line — embedded
    in prose does not match. Default token: ##DONE##. Used by RalphStrategy
    to detect goal completion.
    """

    def __init__(self, token: str = "##DONE##") -> None:  # noqa: S107
        """Store the completion token to scan for."""
        self._token = token

    def is_met(self, response: str) -> bool:
        """Return True if any line exactly matches the token."""
        return any(line.strip() == self._token for line in response.splitlines())

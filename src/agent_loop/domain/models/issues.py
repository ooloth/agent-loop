"""Domain value objects for issues."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """A work item in the issue tracker."""

    number: int
    title: str
    body: str
    labels: frozenset[str]


@dataclass(frozen=True)
class FoundIssue:
    """An issue discovered by the analyzer, before it is filed in a tracker."""

    title: str
    body: str
    labels: tuple[str, ...] = ()

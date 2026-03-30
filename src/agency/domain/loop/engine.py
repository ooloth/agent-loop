"""Generic loop engine — run a strategy to completion.

This is the core abstraction all agent workflows (fix, ralph, future) build on.
A single entry point (loop_until_done) accepts a pluggable LoopStrategy and runs
it to completion. The engine has no knowledge of which AI provider, VCS system,
or issue tracker is in use.

Progress events (AntagonisticStrategy):
    Implemented → [NoChanges | DiffReady → ReviewApproved/ReviewRejected
                   → AddressedFeedback → DiffReady → ...]*

Progress events (RalphStrategy):
    [StepStarted → StepCompleted]*
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agency.domain.loop.work import WorkSpec
from agency.domain.ports.vcs_backend import VCSBackend

# ---------------------------------------------------------------------------
# Progress events — reported by strategies during execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Implemented:
    """The implement agent completed the initial fix."""

    elapsed_seconds: int


@dataclass(frozen=True)
class NoChanges:
    """The implement agent produced no staged diff."""


@dataclass(frozen=True)
class ReviewApproved:
    """The review agent approved the diff."""

    iteration: int
    max_iterations: int
    elapsed_seconds: int


@dataclass(frozen=True)
class ReviewRejected:
    """The review agent requested changes."""

    iteration: int
    max_iterations: int
    elapsed_seconds: int
    summary: str


@dataclass(frozen=True)
class DiffReady:
    """A staged diff is ready for review."""

    lines: int


@dataclass(frozen=True)
class AddressedFeedback:
    """The implement agent addressed review feedback."""

    elapsed_seconds: int


@dataclass(frozen=True)
class StepStarted:
    """A Ralph-style agent is starting a fresh-eyes iteration."""

    iteration: int
    max_iterations: int


@dataclass(frozen=True)
class StepCompleted:
    """A Ralph-style agent finished an iteration."""

    iteration: int
    max_iterations: int
    elapsed_seconds: int
    done: bool
    scratchpad: str = ""


EngineEvent = (
    Implemented
    | NoChanges
    | DiffReady
    | ReviewApproved
    | ReviewRejected
    | AddressedFeedback
    | StepStarted
    | StepCompleted
)
ProgressCallback = Callable[[EngineEvent], None]


def _noop(_event: EngineEvent) -> None:
    pass


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoopResult:
    """Outcome of a loop_until_done run.

    Strategy-specific state (review log, scratchpad, agent responses) lives on
    the strategy instances, not here. Callers that need strategy-specific data
    access it via the strategy object after the loop completes.
    """

    converged: bool
    has_changes: bool
    iterations: int


# ---------------------------------------------------------------------------
# Loop options
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoopOptions:
    """Execution options for a loop run."""

    max_iterations: int
    context: str = ""
    on_progress: ProgressCallback = _noop


# ---------------------------------------------------------------------------
# Strategy protocol
# ---------------------------------------------------------------------------


class LoopStrategy(Protocol):
    """A pluggable strategy that drives one style of agent loop.

    The engine calls execute() exactly once per loop_until_done() invocation.
    The strategy owns the loop body and all iteration logic.
    """

    def execute(
        self,
        work: WorkSpec,
        vcs: VCSBackend,
        options: LoopOptions,
    ) -> LoopResult:
        """Run the strategy's loop body and return the outcome."""
        ...


# ---------------------------------------------------------------------------
# Engine entry point
# ---------------------------------------------------------------------------


def loop_until_done(
    work: WorkSpec,
    strategy: LoopStrategy,
    vcs: VCSBackend,
    options: LoopOptions,
) -> LoopResult:
    """Run a loop strategy to completion.

    This is the single entry point for all loop variants. The strategy owns
    the loop body; this function provides the uniform call site and a seam
    for future cross-cutting concerns (timing, metrics, error handling).
    """
    return strategy.execute(work, vcs, options)

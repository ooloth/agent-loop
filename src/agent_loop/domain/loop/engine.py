"""Generic loop engine — run a strategy to completion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agent_loop.domain.loop.work import WorkSpec
from agent_loop.domain.ports.vcs_backend import VCSBackend

# ---------------------------------------------------------------------------
# Progress events — reported by strategies during execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Implementing:
    """The implement agent is working on the initial fix."""


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
class AddressingFeedback:
    """The implement agent is addressing review feedback."""


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
    Implementing
    | NoChanges
    | ReviewApproved
    | ReviewRejected
    | AddressingFeedback
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
    """Outcome of a loop_until_done run."""

    converged: bool
    has_changes: bool
    iterations: int


# ---------------------------------------------------------------------------
# Strategy protocol
# ---------------------------------------------------------------------------


class LoopStrategy(Protocol):
    """A pluggable strategy that drives one style of agent loop."""

    def execute(
        self,
        work: WorkSpec,
        vcs: VCSBackend,
        max_iterations: int,
        context: str,
        on_progress: ProgressCallback,
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
    max_iterations: int,
    context: str = "",
    on_progress: ProgressCallback = _noop,
) -> LoopResult:
    """Run a loop strategy to completion.

    This is the single entry point for all loop variants. The strategy owns
    the loop body; this function provides the uniform call site and a seam
    for future cross-cutting concerns (timing, metrics, error handling).
    """
    return strategy.execute(work, vcs, max_iterations, context, on_progress)

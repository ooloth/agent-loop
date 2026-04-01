"""Tests for domain error types and invariant() helper."""

import pytest

from agency.domain.errors import InvariantError, invariant


class TestInvariant:
    def test_passes_when_condition_is_true(self) -> None:
        x = 1
        invariant(x > 0, "should not raise")

    def test_raises_invariant_violation_when_condition_is_false(self) -> None:
        x = -1
        with pytest.raises(InvariantError, match="x must be positive"):
            invariant(x > 0, "x must be positive")

    def test_invariant_violation_is_runtime_error(self) -> None:
        x = -1
        with pytest.raises(RuntimeError):
            invariant(x > 0, "x must be positive")

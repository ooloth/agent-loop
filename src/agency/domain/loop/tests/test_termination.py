"""Tests for termination conditions."""

from agency.domain.loop.termination import OutputSignal


class TestOutputSignal:
    def test_token_on_own_line(self) -> None:
        response = "Made the change.\n##DONE##\n"
        assert OutputSignal().is_met(response) is True

    def test_token_with_surrounding_whitespace(self) -> None:
        response = "Made the change.\n  ##DONE##  \n"
        assert OutputSignal().is_met(response) is True

    def test_token_at_end_without_trailing_newline(self) -> None:
        response = "Made the change.\n##DONE##"
        assert OutputSignal().is_met(response) is True

    def test_token_embedded_in_prose(self) -> None:
        response = "I will output ##DONE## when finished."
        assert OutputSignal().is_met(response) is False

    def test_no_token(self) -> None:
        response = "Made progress but more work remains."
        assert OutputSignal().is_met(response) is False

    def test_custom_token(self) -> None:
        signal = OutputSignal(token="FINISHED")
        assert signal.is_met("All done.\nFINISHED\n") is True
        assert signal.is_met("Not FINISHED yet.") is False

    def test_empty_response(self) -> None:
        assert OutputSignal().is_met("") is False

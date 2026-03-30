"""Tests for scratchpad extraction and inter-iteration passing."""

from agency.domain.loop.strategies import extract_scratchpad


class TestExtractScratchpad:
    def test_extracts_scratchpad_block(self) -> None:
        response = "Made the change.\n\n```scratchpad\n## Status\nStep 1 done.\n```"
        assert extract_scratchpad(response) == "## Status\nStep 1 done."

    def test_multiline_scratchpad(self) -> None:
        response = (
            "Done.\n\n"
            "```scratchpad\n"
            "## Status\n"
            "All criteria met.\n\n"
            "## Key decisions\n"
            "Used dataclass over dict.\n\n"
            "## Remaining work\n"
            "None.\n"
            "```"
        )
        result = extract_scratchpad(response)
        assert "## Status" in result
        assert "## Key decisions" in result
        assert "## Remaining work" in result

    def test_no_scratchpad_returns_empty(self) -> None:
        response = "Made the change. All done.\n##DONE##"
        assert extract_scratchpad(response) == ""

    def test_other_code_blocks_ignored(self) -> None:
        response = "Here's the code:\n```python\nprint('hello')\n```\n\nNo scratchpad here."
        assert extract_scratchpad(response) == ""

    def test_scratchpad_with_surrounding_content(self) -> None:
        response = (
            "I fixed the bug and added tests.\n\n"
            "##DONE##\n\n"
            "```scratchpad\n"
            "## Status\n"
            "Complete.\n"
            "```\n\n"
            "Some trailing text."
        )
        assert extract_scratchpad(response) == "## Status\nComplete."

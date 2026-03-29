"""Tests for WorkSpec loaders."""

from agent_loop.domain.loop.work import from_prompt


class TestFromPrompt:
    def test_short_prompt_is_title(self) -> None:
        work = from_prompt("add type hints")
        assert work.title == "add type hints"
        assert work.body == "add type hints"

    def test_long_prompt_truncates_title(self) -> None:
        long = "a" * 100
        work = from_prompt(long)
        assert len(work.title) == 51  # 50 chars + ellipsis
        assert work.title.endswith("…")
        assert work.body == long

    def test_exactly_50_chars_no_truncation(self) -> None:
        prompt = "a" * 50
        work = from_prompt(prompt)
        assert work.title == prompt
        assert "…" not in work.title

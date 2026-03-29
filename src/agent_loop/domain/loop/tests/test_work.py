"""Tests for WorkSpec loaders."""

from agent_loop.domain.loop.work import work_from_prompt


class TestFromPrompt:
    def test_short_prompt_is_title(self) -> None:
        work = work_from_prompt("add type hints")
        assert work.title == "add type hints"
        assert work.body == "add type hints"

    def test_long_prompt_truncates_title(self) -> None:
        long = "a" * 100
        work = work_from_prompt(long)
        assert len(work.title) == 61  # 60 chars + ellipsis
        assert work.title.endswith("…")
        assert work.body == long

    def test_exactly_60_chars_no_truncation(self) -> None:
        prompt = "a" * 60
        work = work_from_prompt(prompt)
        assert work.title == prompt
        assert "…" not in work.title

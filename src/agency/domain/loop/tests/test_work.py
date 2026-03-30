"""Tests for WorkSpec loaders."""

from pathlib import Path

import pytest

from agency.domain.loop.work import from_file, from_prompt


class TestFromPrompt:
    def test_short_prompt_is_title(self) -> None:
        work = from_prompt("add type hints")
        assert work.title == "add type hints"
        assert work.body == "add type hints"

    def test_long_prompt_truncates_title(self) -> None:
        long = "a" * 100
        work = from_prompt(long)
        assert len(work.title) == 61  # 60 chars + ellipsis
        assert work.title.endswith("…")
        assert work.body == long

    def test_exactly_60_chars_no_truncation(self) -> None:
        prompt = "a" * 60
        work = from_prompt(prompt)
        assert work.title == prompt
        assert "…" not in work.title


class TestFromFile:
    def test_heading_becomes_title(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text("# Add type hints\n\nDo the thing.\n")
        work = from_file(f)
        assert work.title == "Add type hints"
        assert work.body.startswith("# Add type hints")

    def test_body_is_full_file_content(self, tmp_path: Path) -> None:
        content = "# Title\n\n## Acceptance Criteria\n- Tests pass\n"
        f = tmp_path / "task.md"
        f.write_text(content)
        work = from_file(f)
        assert work.body == content.strip()

    def test_no_heading_falls_back_to_first_line(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text("Add type hints to foo.py\n\nMore details.\n")
        work = from_file(f)
        assert work.title == "Add type hints to foo.py"

    def test_no_heading_long_first_line_truncates(self, tmp_path: Path) -> None:
        long_line = "a" * 100
        f = tmp_path / "task.md"
        f.write_text(f"{long_line}\n\nDetails.\n")
        work = from_file(f)
        assert len(work.title) == 61
        assert work.title.endswith("…")

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text("")
        with pytest.raises(ValueError, match="empty"):
            from_file(f)

    def test_whitespace_only_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "task.md"
        f.write_text("   \n\n  \n")
        with pytest.raises(ValueError, match="empty"):
            from_file(f)

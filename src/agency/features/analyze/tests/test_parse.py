"""Tests for pure parsing functions used by the analyze pipeline."""

import pytest

from agency.domain.models.issues import FoundIssue
from agency.features.analyze.errors import AnalysisParseError
from agency.features.analyze.parse import parse_analysis_results

# --- parse_analysis_results ---


class TestParseAnalysisResults:
    def test_bare_json(self) -> None:
        raw = '[{"title": "Bug", "body": "desc"}]'
        result = parse_analysis_results(raw)
        assert result == [FoundIssue(title="Bug", body="desc")]

    def test_fenced_json(self) -> None:
        raw = '```json\n[{"title": "Bug"}]\n```'
        result = parse_analysis_results(raw)
        assert result == [FoundIssue(title="Bug", body="")]

    def test_fenced_no_language(self) -> None:
        raw = '```\n[{"title": "Bug"}]\n```'
        result = parse_analysis_results(raw)
        assert result == [FoundIssue(title="Bug", body="")]

    def test_surrounding_text_ignored(self) -> None:
        raw = 'Here are the issues:\n```json\n[{"title": "A"}]\n```\nDone.'
        result = parse_analysis_results(raw)
        assert result == [FoundIssue(title="A", body="")]

    def test_labels_parsed(self) -> None:
        raw = '[{"title": "Bug", "body": "desc", "labels": ["bug", "p1"]}]'
        result = parse_analysis_results(raw)
        assert result == [FoundIssue(title="Bug", body="desc", labels=("bug", "p1"))]

    def test_empty_array(self) -> None:
        result = parse_analysis_results("[]")
        assert result == []

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(AnalysisParseError) as exc_info:
            parse_analysis_results("not json at all")
        assert "not json at all" in str(exc_info.value)

    def test_invalid_json_in_fence_raises(self) -> None:
        with pytest.raises(AnalysisParseError):
            parse_analysis_results("```\nnot json\n```")

    def test_missing_title_raises(self) -> None:
        raw = '[{"body": "no title here"}]'
        with pytest.raises(AnalysisParseError, match="item 0 missing required 'title' key"):
            parse_analysis_results(raw)

    def test_non_dict_item_raises(self) -> None:
        raw = '["just a string"]'
        with pytest.raises(AnalysisParseError, match="item 0 missing required 'title' key"):
            parse_analysis_results(raw)

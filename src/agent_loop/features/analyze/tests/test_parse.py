"""Tests for pure parsing functions used by the analyze pipeline."""

import pytest

from agent_loop.domain.errors import AnalysisParseError
from agent_loop.features.analyze.command import parse_analysis_results


# --- parse_analysis_results ---


class TestParseAnalysisResults:
    def test_bare_json(self):
        raw = '[{"title": "Bug", "body": "desc"}]'
        result = parse_analysis_results(raw)
        assert result == [{"title": "Bug", "body": "desc"}]

    def test_fenced_json(self):
        raw = '```json\n[{"title": "Bug"}]\n```'
        result = parse_analysis_results(raw)
        assert result == [{"title": "Bug"}]

    def test_fenced_no_language(self):
        raw = '```\n[{"title": "Bug"}]\n```'
        result = parse_analysis_results(raw)
        assert result == [{"title": "Bug"}]

    def test_surrounding_text_ignored(self):
        raw = 'Here are the issues:\n```json\n[{"title": "A"}]\n```\nDone.'
        result = parse_analysis_results(raw)
        assert result == [{"title": "A"}]

    def test_empty_array(self):
        result = parse_analysis_results("[]")
        assert result == []

    def test_invalid_json_raises(self):
        with pytest.raises(AnalysisParseError) as exc_info:
            parse_analysis_results("not json at all")
        assert "not json at all" in str(exc_info.value)

    def test_invalid_json_in_fence_raises(self):
        with pytest.raises(AnalysisParseError):
            parse_analysis_results("```\nnot json\n```")

"""Tests for `nlp.normalize` -- deterministic text cleaning, no model."""

from __future__ import annotations

import pytest

from nlp.exceptions import NlpError
from nlp.normalize import normalize_headline, normalize_summary


class TestNormalizeHeadline:
    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert normalize_headline("  Fed holds rates  ") == "Fed holds rates"

    def test_collapses_internal_whitespace_runs(self) -> None:
        assert normalize_headline("Fed   holds\n\trates") == "Fed holds rates"

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(NlpError, match="empty"):
            normalize_headline("")

    def test_raises_on_whitespace_only_string(self) -> None:
        with pytest.raises(NlpError, match="empty"):
            normalize_headline("   \n\t  ")

    def test_leaves_already_clean_text_unchanged(self) -> None:
        assert normalize_headline("Fed holds rates steady") == "Fed holds rates steady"


class TestNormalizeSummary:
    def test_strips_and_collapses_like_headline(self) -> None:
        assert normalize_summary("  Some   detail.  ") == "Some detail."

    def test_empty_string_is_valid(self) -> None:
        assert normalize_summary("") == ""

    def test_whitespace_only_normalizes_to_empty(self) -> None:
        assert normalize_summary("   \n  ") == ""

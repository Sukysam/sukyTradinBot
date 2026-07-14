"""Deterministic text cleaning for Phase A ingestion -- no model, no
randomness, just whitespace normalization and emptiness validation.
Mirrors `regime-trader/core/sentiment_engine.py::SentimentEngine.
_validate_text`'s non-empty-after-strip check for `headline` specifically
(the field sentiment scoring is calibrated against, per
`06_NLP_ENGINEER.md`'s documented pitfall), while treating `summary` as
optional, matching `NewsItem.summary`'s legacy `news.summary or ""`
fallback.
"""

from __future__ import annotations

import re

from nlp.exceptions import NlpError

_WHITESPACE_RUN = re.compile(r"\s+")


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text.strip())


def normalize_headline(raw: str) -> str:
    """Strip and collapse whitespace; raise if nothing meaningful
    remains -- a blank headline can't be scored or displayed, so this
    fails loudly at ingestion rather than producing a `NewsItem` no
    downstream stage can use."""
    cleaned = _collapse_whitespace(raw)
    if not cleaned:
        raise NlpError("headline must not be empty after normalization")
    return cleaned


def normalize_summary(raw: str) -> str:
    """Strip and collapse whitespace. Unlike `normalize_headline`, an
    empty result is valid -- summaries are legitimately absent for many
    real news events (see `NewsItem`'s docstring)."""
    return _collapse_whitespace(raw)


__all__ = ["normalize_headline", "normalize_summary"]

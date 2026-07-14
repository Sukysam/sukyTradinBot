"""NLP & Event Processing (Milestone 10) -- shadow mode only.

Records a `NewsSignal` for every processed story, without ever
influencing `strategy`, `risk`, or `execution`. See
docs/engineering-handbook/Architecture/ADR/ADR-018-NewsSignal-Contract.md.

Phase A (`models.py`, `normalize.py`, `store.py`): deterministic
ingestion, cleaning, and deduplication into a `NewsItem` -- no sentiment
model yet. Phase B: FinBERT sentiment scoring, producing the frozen
`NewsSignal`. Phase C: evaluation reporting (ingestion latency,
deduplication rate, sentiment distribution, throughput) -- still no
influence on the trading pipeline.
"""

from __future__ import annotations

from nlp.evaluation import evaluate_ingestion, evaluate_sentiment, generate_evaluation_report
from nlp.exceptions import CorruptNewsLogError, NlpError
from nlp.interfaces import NewsItemStore, SentimentScorer
from nlp.models import NewsItem, NewsSignal, SentimentResult
from nlp.normalize import normalize_headline, normalize_summary
from nlp.sentiment import DeterministicSentimentScorer, FinBertSentimentScorer
from nlp.service import NlpService
from nlp.store import InMemoryNewsItemStore, JsonlNewsItemStore

__version__ = "0.1.0"

__all__ = [
    "CorruptNewsLogError",
    "DeterministicSentimentScorer",
    "FinBertSentimentScorer",
    "InMemoryNewsItemStore",
    "JsonlNewsItemStore",
    "NewsItem",
    "NewsItemStore",
    "NewsSignal",
    "NlpError",
    "NlpService",
    "SentimentResult",
    "SentimentScorer",
    "__version__",
    "evaluate_ingestion",
    "evaluate_sentiment",
    "generate_evaluation_report",
    "normalize_headline",
    "normalize_summary",
]

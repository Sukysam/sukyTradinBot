"""FinBERT headline sentiment scoring (Spec Sec. 3).

Loads ProsusAI/finbert once per process and scores incoming headlines into
[positive, negative, neutral] probabilities. This module only scores text; it
does not decide whether a score triggers the NLP Catalyst Strategy override.
That threshold logic (FinBERT > 0.90 positive while the HMM regime is
NEUTRAL) belongs to the orchestrator (`signal_generator.py`), the only place
that has visibility into the concurrent HMM regime state -- keeping the
threshold out of this file means sentiment scoring stays reusable wherever
else headline sentiment is needed later.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "ProsusAI/finbert"
MAX_SEQUENCE_LENGTH = 512
REQUIRED_LABELS = {"positive", "negative", "neutral"}


@dataclass(frozen=True)
class SentimentScore:
    text: str
    positive: float
    negative: float
    neutral: float
    label: str

    def __post_init__(self):
        total = self.positive + self.negative + self.neutral
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Sentiment probabilities must sum to ~1.0, got {total}")


class SentimentEngine:
    """Loads FinBERT once; call `score` / `score_batch` per headline or batch
    of headlines. Headline bursts from the Alpaca News WebSocket should go
    through `score_batch` rather than repeated `score` calls -- batching is
    the difference between one forward pass and N of them.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, device: str | None = None):
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        logger.info("Loading FinBERT model %s onto %s", model_name, self.device)
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self._model.to(self.device)
        self._model.eval()

        # Read the label order from the model config instead of assuming
        # [positive, negative, neutral] index order -- a swapped config would
        # otherwise silently mislabel every score with no error anywhere.
        self._id2label = {int(k): v.lower() for k, v in self._model.config.id2label.items()}
        if set(self._id2label.values()) != REQUIRED_LABELS:
            raise ValueError(
                f"Unexpected label set from model config: {self._id2label}. "
                f"Expected exactly {REQUIRED_LABELS}."
            )

    @torch.no_grad()
    def score_batch(self, texts: list[str]) -> list[SentimentScore]:
        if not texts:
            return []
        cleaned = [self._validate_text(t) for t in texts]

        inputs = self._tokenizer(
            cleaned,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_SEQUENCE_LENGTH,
        ).to(self.device)

        logits = self._model(**inputs).logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()

        results = []
        for text, row in zip(cleaned, probs):
            scores = {self._id2label[i]: float(p) for i, p in enumerate(row)}
            label = max(scores, key=scores.get)
            results.append(
                SentimentScore(
                    text=text,
                    positive=scores["positive"],
                    negative=scores["negative"],
                    neutral=scores["neutral"],
                    label=label,
                )
            )
        return results

    def score(self, text: str) -> SentimentScore:
        return self.score_batch([text])[0]

    @staticmethod
    def _validate_text(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Headline text must be a non-empty string, got {text!r}")
        return text.strip()

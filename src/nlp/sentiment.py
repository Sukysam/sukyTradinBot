"""`nlp.interfaces.SentimentScorer` implementations.

`DeterministicSentimentScorer` is dependency-free and fully deterministic
-- the default choice for tests and for any caller that wants Phase B's
`NewsSignal`-assembly logic exercised without a real model. `FinBertSentimentScorer`
adapts `regime-trader/core/sentiment_engine.py::SentimentEngine`: same
model (`ProsusAI/finbert`), same batch-only scoring, same `id2label`-driven
label validation -- but `torch`/`transformers` are imported lazily inside
`__init__`, not at module level, so the rest of `nlp` (and anything that
imports it) never requires those packages to be installed. Mirrors
`execution.broker_adapter`'s isolation of the one module that imports the
Alpaca SDK.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from nlp.exceptions import NlpError
from nlp.models import REQUIRED_SENTIMENT_LABELS, SentimentResult

DEFAULT_FINBERT_MODEL_NAME = "ProsusAI/finbert"
MAX_SEQUENCE_LENGTH = 512


def _default_neutral_result() -> SentimentResult:
    return SentimentResult(positive=0.0, negative=0.0, neutral=1.0, label="neutral")


@dataclass
class DeterministicSentimentScorer:
    """Returns a caller-supplied `SentimentResult` per headline, or
    `default` for any headline not present in `overrides`. Useful both as
    a test double and as an explicit "no model configured yet" fallback
    -- either way, deterministic and instant, no inference cost."""

    default: SentimentResult = field(default_factory=_default_neutral_result)
    overrides: Mapping[str, SentimentResult] = field(default_factory=dict)
    model_version: str = "deterministic-v1"

    def score_batch(self, headlines: Sequence[str]) -> Sequence[SentimentResult]:
        return [self.overrides.get(headline, self.default) for headline in headlines]


class FinBertSentimentScorer:
    """Real FinBERT-backed `SentimentScorer`. Requires `torch` and
    `transformers` to be installed (the `trading` extra) -- raises
    `NlpError` at construction, not import time, if they aren't, so
    importing `nlp.sentiment` itself never requires them."""

    def __init__(
        self, model_name: str = DEFAULT_FINBERT_MODEL_NAME, device: str | None = None
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise NlpError(
                "FinBertSentimentScorer requires the 'torch' and 'transformers' packages -- "
                "install them (e.g. via the 'trading' extra) before constructing this scorer."
            ) from exc

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)
        self._model.eval()

        id2label = {int(index): name.lower() for index, name in self._model.config.id2label.items()}
        if set(id2label.values()) != set(REQUIRED_SENTIMENT_LABELS):
            raise NlpError(
                f"model {model_name!r} label set {sorted(set(id2label.values()))} does not "
                f"match the required set {sorted(REQUIRED_SENTIMENT_LABELS)}"
            )
        self._id2label = id2label
        self._model_name = model_name

    @property
    def model_version(self) -> str:
        return self._model_name

    def score_batch(self, headlines: Sequence[str]) -> Sequence[SentimentResult]:
        if not headlines:
            return []
        for headline in headlines:
            if not headline or not headline.strip():
                raise NlpError("headline must not be empty")

        inputs = self._tokenizer(
            list(headlines),
            padding=True,
            truncation=True,
            max_length=MAX_SEQUENCE_LENGTH,
            return_tensors="pt",
        ).to(self._device)

        with self._torch.no_grad():
            logits = self._model(**inputs).logits
            probabilities = self._torch.nn.functional.softmax(logits, dim=-1).cpu().tolist()

        results = []
        for row in probabilities:
            scores = {self._id2label[index]: value for index, value in enumerate(row)}
            label = max(scores, key=lambda name: scores[name])
            results.append(
                SentimentResult(
                    positive=scores["positive"],
                    negative=scores["negative"],
                    neutral=scores["neutral"],
                    label=label,
                )
            )
        return results


__all__ = [
    "DEFAULT_FINBERT_MODEL_NAME",
    "MAX_SEQUENCE_LENGTH",
    "DeterministicSentimentScorer",
    "FinBertSentimentScorer",
]

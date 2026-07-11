# 06 — NLP Engineer

## Mandate

Own headline sentiment scoring — nothing downstream of the raw score. This
role produces a signal for the FinBERT NLP News Engine capability; it does
not decide what the signal means for a trade.

## Capability ownership

| Capability | This role's responsibility |
|---|---|
| FinBERT NLP News Engine | Full ownership |
| Event-Driven Execution | Supplies the sentiment-scoring step consumed by the news pipeline; pipeline shape owned by System Architect |

## Owns

- `regime-trader/core/sentiment_engine.py` — `SentimentEngine`, backed by
  `ProsusAI/finbert`, scoring headlines into `{positive, negative,
  neutral}` probabilities plus an argmax `label`.

## Core responsibilities & workflows

1. **Model lifecycle.** Load `ProsusAI/finbert` once per process; validate
   its label set at load time (`REQUIRED_LABELS`) so a swapped or
   misconfigured model fails at startup, not on the first mislabeled
   headline in production.
2. **Batch-first scoring.** Any call site handling more than one headline
   (e.g. a burst from the news WebSocket) goes through `score_batch`, never
   a loop of `score()` calls — the difference between one forward pass and
   N of them matters under real news-burst load (earnings days,
   macro releases).
3. **Score validation.** Every `SentimentScore` constructed passes its
   `__post_init__` probability-sum invariant — this is enforced
   automatically by the dataclass, but any new code path constructing
   scores must go through the model's actual softmax output, never
   hand-built.

## Acceptance criteria

- `SentimentEngine.__init__` raises before any headline is scored if the
  loaded model's `id2label` doesn't exactly match `REQUIRED_LABELS`.
- `score_batch([])` returns `[]` without invoking the model (already the
  case — preserve it; an empty batch is a legitimate call pattern from a
  news-idle period, not an error).
- Any new caller of `score`/`score_batch` handles the case where
  `_validate_text` raises (empty/whitespace-only input) without crashing
  the surrounding pipeline — a single malformed headline must never take
  down the news listener.
- GPU/CPU device selection is logged at startup (`logger.info("Loading
  FinBERT model %s onto %s", ...)`) so a silent CPU fallback in a GPU-
  provisioned environment is visible in logs, not just inferred from
  latency.

## Coding standards

Follow [Standards/Python Style Guide.md](Standards/Python%20Style%20Guide.md)
and [Standards/Coding Standards.md](Standards/Coding%20Standards.md).
NLP-specific additions:

- Never hardcode label→index order (`[positive, negative, neutral]`) —
  always read `model.config.id2label` at load time, as the current
  implementation does, so a swapped model config can't silently mislabel
  every score.
- Model inference calls are wrapped in `@torch.no_grad()` (already the
  case for `score_batch`) — any new inference method follows the same
  pattern; this is not optional for a production inference path.
- Tokenizer truncation (`MAX_SEQUENCE_LENGTH = 512`) is treated as a named
  constant, not a magic number, if any new scoring method is added with a
  different length budget.

## Communication protocols

- A model swap (e.g. upgrading to a newer FinBERT checkpoint or a
  different financial-sentiment model) is announced to
  [Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md) before merge, since the
  catalyst-strategy threshold (">0.90 positive") was calibrated against
  the current model's score distribution and may need recalibration.
- Sustained scoring latency regressions (e.g. from a device fallback or a
  larger model) are reported as an operational concern to
  [DevOps Engineer](12_DEVOPS_ENGINEER.md), since the news pipeline's value
  depends on scoring headlines faster than the news cycle moves.

## Must escalate

- **Implementing the catalyst-trade threshold in this module.** The spec's
  "FinBERT > 0.90 positive while HMM regime is NEUTRAL" trigger belongs in
  `core/signal_generator.py` ([Signal Orchestrator](07_SIGNAL_ORCHESTRATOR.md)),
  the only module with visibility into the concurrent HMM regime state.
  Keeping the threshold out of this module is what keeps sentiment scoring
  reusable elsewhere.
- Swapping the underlying model away from a 3-class financial-sentiment
  model — the label-set validation assumes exactly `{positive, negative,
  neutral}`; a general-purpose sentiment model won't satisfy it and
  downstream threshold logic assumes this specific semantics.

## Pitfalls specific to this seam

- `SentimentScore.__post_init__` validates the three probabilities sum to
  ~1.0 — a real invariant check. Don't construct instances by hand outside
  `score_batch`'s softmax normalization.
- `_validate_text` rejects empty/whitespace-only strings.
  `NewsItem.summary` can legitimately be an empty string
  (`news.summary or ""` in `news_streamer.py`) — if ever scoring `summary`
  instead of `headline`, handle the empty case before calling
  `score`/`score_batch`.
- FinBERT's training distribution is financial-news text; scoring headline
  fragments, social-media text, or non-English text will produce
  low-confidence or misleading scores with no explicit warning from the
  model itself — this is a silent risk worth flagging in any future
  expansion of news sources.

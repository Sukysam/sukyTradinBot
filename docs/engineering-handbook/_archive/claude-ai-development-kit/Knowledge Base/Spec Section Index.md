# Spec Section Index

Reconstructed entirely from "Spec Sec. N" citations found in
`regime-trader/` module docstrings as of 2026-07-11 — **not** transcribed
from an authoritative spec document, because none was found in this
repository. If the real spec surfaces, reconcile this index against it and
correct any drift (see
[11_DOCUMENTATION_ENGINEER.md](../11_DOCUMENTATION_ENGINEER.md)).

| Section | Subject (inferred) | Implementing module(s) | Cited in |
|---|---|---|---|
| Sec. 1 | Order execution basics (bracket orders, news transport) | `broker/order_executor.py`, `broker/news_streamer.py` | Both modules' docstrings |
| Sec. 2 | HMM volatility-regime engine: feature causality, Baum-Welch/BIC training, causal forward inference | `core/hmm_engine.py`, `data/feature_engineering.py` | Both modules' docstrings |
| Sec. 3 | Regime-tier → strategy/allocation logic; FinBERT catalyst threshold (">0.90 positive in NEUTRAL regime") | `core/regime_strategies.py` (not yet built), `core/sentiment_engine.py` | `sentiment_engine.py`, `main.py` docstrings |
| Sec. 4 | Continuous learning loop: trade context snapshot schema, Thompson-sampling bandit over closed trades | `core/learning_engine.py`, `data/trade_context_db.json` schema | `learning_engine.py`, `main.py` docstrings |
| Sec. 5 | Risk limits: exposure/concentration/leverage caps, correlation filter, circuit breakers, emergency hard stop | `core/risk_manager.py` | `risk_manager.py`, `order_executor.py` docstrings |
| Sec. 6 | Execution loop orchestration: three concurrent pipelines (5-min structural, event-driven news, weekend cron), 3-bar stability filter | `main.py` | `main.py` docstring |

## Values cited directly in code (treat as spec-derived constants)

- 3-bar persistence filter before a regime state is acted on
  (`main.py.STABILITY_PERSISTENCE_BARS`).
- 252-day rolling z-score window (`feature_engineering.ZSCORE_WINDOW`).
- FinBERT catalyst threshold: >0.90 positive probability while HMM regime
  reads NEUTRAL (cited in `sentiment_engine.py`, not yet implemented in
  `signal_generator.py`).
- Full risk-limit table — see
  [Standards/Risk Limits Reference.md](../Standards/Risk%20Limits%20Reference.md).

## Explicitly *not* specified anywhere found

These are treated as open design questions, not omissions to guess at — see
[Architecture/Known Gaps.md](../Architecture/Known%20Gaps.md):

- Where/how a fitted `GaussianHMM` per ticker is persisted and refreshed.
- The exact regime label taxonomy beyond the example names used in
  docstrings (`"LOW_VOL"`, `"MID_VOL"`, `"HIGH_VOL"`, `"NEUTRAL"`).
- `config/settings.yaml`'s schema (ticker list, sector mapping).
- Take-profit target logic — Sec. 5 defines stop levels per volatility tier
  but never a take-profit target.

# Standard — Anti-Look-Ahead Checklist

The single most important correctness property in this codebase: every
value computed at bar `t` must depend only on data at or before `t`. A
violation doesn't crash anything — it silently makes the HMM (and every
downstream decision) look better in backtests than it will ever perform
live, because the model gets to "see the future" during training/evaluation
in a way it never can in production.

## When adding or changing a feature in `data/feature_engineering.py`

- [ ] No `.rolling(..., center=True)`.
- [ ] No `.shift(-n)` for any positive `n` (negative-lag shift pulls future
      values backward).
- [ ] Every `.rolling(window=W, ...)` call sets `min_periods=W`, matching
      `rolling_zscore`'s existing pattern — a value should never be emitted
      from a partial window, since that's statistically unstable in a
      different way (not look-ahead, but still not trustworthy).
- [ ] Any technical indicator sourced from the `ta` library is confirmed
      trailing-only for the specific function used (Wilder's smoothing in
      ADX/RSI/ATR is trailing by construction, but not every indicator in
      that library necessarily is — check before adding a new one).
- [ ] New raw feature gets a `_z`-suffixed rolling-zscore counterpart,
      following `build_feature_matrix`'s existing pattern, and the raw
      version's own look-ahead safety is checked independently of the
      z-score wrapper's.

## Regression test pattern

For any feature column `X`, this property must hold and should be asserted
directly, not just eyeballed:

```python
def test_no_lookahead(feature_col_fn, sample_df):
    baseline = feature_col_fn(sample_df)
    mutated = sample_df.copy()
    future_idx = mutated.index[-1]          # last row = "the future" relative to earlier rows
    mutated.loc[future_idx, "close"] *= 1.5  # perturb only the most recent bar
    perturbed = feature_col_fn(mutated)

    # every row except the perturbed one (and rows that causally depend on
    # it, e.g. via a *trailing* window that includes it) must be unchanged
    pd.testing.assert_series_equal(
        baseline.iloc[:-1], perturbed.iloc[:-1]
    )
```

Adapt the mutation index/window depending on whether the trailing window
under test includes the perturbed bar in earlier rows' computations (it
shouldn't, for any strictly causal transform).

## On the inference side (`core/hmm_engine.py`)

- [ ] Live regime probability always comes from `ForwardFilter.update` or
      `forward_algorithm`, never `GaussianHMM.predict_proba` (smoothed,
      uses the backward pass) or `.predict`/`.decode` (Viterbi, globally
      optimal path over the whole sequence).
- [ ] If you must inspect smoothed/Viterbi output for offline research
      (e.g. "how would an oracle have labeled this period"), keep it
      clearly separated from anything that touches the live trading path or
      a backtest that's meant to represent achievable performance.

## Why this matters more than most other bugs here

A risk-limit bug or an order-construction bug tends to fail loudly (a
rejected order, an exception, a circuit breaker firing). A look-ahead bug
fails silently and specifically *flatters* backtests and paper-trading
metrics — it's the failure mode most likely to survive all the way to a
live-capital decision undetected. Treat any ambiguity here as a blocking
question, not a judgment call to make alone.

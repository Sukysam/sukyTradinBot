"""End-to-end integration: real `Bar`s -> real `FeaturePipeline` ->
`RegimeService`, not the hand-constructed `FeatureVector`s the rest of
`tests/hmm/` uses for precise control over synthetic regime structure.
Proves the two milestones' contracts actually compose, not just that each
one's own tests pass in isolation.
"""

from __future__ import annotations

from pathlib import Path

from features.pipeline import FeaturePipeline
from hmm.config import HMMConfig, SelectionConfig, TrainingConfig
from hmm.service import RegimeService
from tests.features.conftest import make_bars


def test_real_feature_pipeline_output_trains_and_infers_successfully(tmp_path: Path) -> None:
    bars = make_bars(300, drift=0.001, vol=0.01, seed=11)
    pipeline = FeaturePipeline()
    vectors, _diagnostics = pipeline.compute_series(bars, "TEST")

    # Drop the warmup-flagged rows (see hmm.normalizer.drop_incomplete_rows
    # for why the HMM package won't silently impute them) and pick a small,
    # HMM-appropriate feature subset rather than the full 39-feature
    # registry -- see tests/hmm/test_performance.py's module docstring on
    # full-covariance parameter growth.
    clean = [v for v in vectors if not v.has_any_flag]
    feature_names = ("log_return_1", "realized_volatility_20", "rsi_14")

    service = RegimeService.train(
        clean,
        symbol="TEST",
        model_version="v1",
        feature_names=feature_names,
        config=HMMConfig(
            selection=SelectionConfig(candidate_states=(2, 3)),
            training=TrainingConfig(n_init=2, random_state=1),
        ),
    )

    state = service.infer(clean)
    assert state.symbol == "TEST"
    assert state.feature_pipeline_version == clean[-1].provenance.pipeline_version
    assert 0.0 <= state.confidence <= 1.0

    service.save(tmp_path)
    reloaded = RegimeService.load(tmp_path, "TEST", "v1")
    reloaded_state = reloaded.infer(clean)
    assert reloaded_state.regime_id == state.regime_id

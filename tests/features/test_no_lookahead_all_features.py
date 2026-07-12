"""The single most important test file in this platform.

Applies the anti-look-ahead regression pattern from
docs/engineering-handbook/Standards/Anti-Lookahead Checklist.md to *every*
feature in `registry.DEFAULT_REGISTRY` automatically, via
`pytest.mark.parametrize`. A new feature registered anywhere in
`price.py`/`volatility.py`/etc. is covered by this test the moment it's
registered — nobody has to remember to write a bespoke leakage test for
it. This is the concrete implementation of Milestone 3's "data leakage
protection" deliverable: `FeatureSpec.uses_future_data` (see registry.py)
catches a feature that *declares* itself as future-peeking; this test
catches one that *behaves* that way despite the declaration.
"""

from __future__ import annotations

import pandas as pd
import pytest

from features.pipeline import _bars_to_dataframe
from features.registry import DEFAULT_REGISTRY
from tests.features.conftest import make_bars

_TEST_BARS = make_bars(150)
_BASE_DF = _bars_to_dataframe(_TEST_BARS)


def _perturbed_df() -> pd.DataFrame:
    mutated = _BASE_DF.copy()
    last = mutated.index[-1]
    # A large, unambiguous perturbation to the most recent bar only.
    mutated.loc[last, ["open", "high", "low", "close"]] *= 2.0
    mutated.loc[last, "volume"] *= 5.0
    return mutated


_PERTURBED_DF = _perturbed_df()


@pytest.mark.parametrize("spec", DEFAULT_REGISTRY.all(), ids=lambda s: s.name)
def test_feature_is_causal(spec: object) -> None:
    """For every registered feature: perturbing only the most recent bar
    must never change any earlier row's computed value. This is the
    literal definition of causality this platform exists to guarantee.
    """
    baseline = spec.compute(_BASE_DF)  # type: ignore[attr-defined]
    perturbed = spec.compute(_PERTURBED_DF)  # type: ignore[attr-defined]

    pd.testing.assert_series_equal(
        baseline.iloc[:-1],
        perturbed.iloc[:-1],
        check_names=False,
        obj=f"{spec.name}: value changed at a row before the perturbed bar",  # type: ignore[attr-defined]
    )


@pytest.mark.parametrize("spec", DEFAULT_REGISTRY.all(), ids=lambda s: s.name)
def test_feature_declares_causal(spec: object) -> None:
    """Belt-and-suspenders: every registered spec's own declaration must
    say `uses_future_data=False` — redundant with `FeatureSpec.__post_init__`
    already enforcing this at registration time, but explicit here so this
    file alone documents the full guarantee without needing to cross-
    reference registry.py.
    """
    assert spec.uses_future_data is False  # type: ignore[attr-defined]


def test_registry_is_not_accidentally_empty() -> None:
    """Guards against this entire test file silently testing nothing if
    the category-module imports in `features/__init__.py` ever stop
    registering features (e.g. an import removed by mistake).
    """
    assert len(DEFAULT_REGISTRY) >= 30

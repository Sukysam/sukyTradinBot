"""Tests for `app.main`.

`_run()`/`main()` themselves (signal registration, the real
`asyncio.run` entrypoint) are not unit-tested -- meaningfully exercising
OS signal delivery requires a real subprocess, not a unit test, the
same honest, documented gap this codebase already accepts for
`FinBertSentimentScorer`'s FinBERT-dependent body (see
`nlp.sentiment`). What *is* testable without a subprocess is confirmed
here: the module-level default configuration is valid (importing the
module already proves this, since `MarketDataLoopConfig.__post_init__`
would raise otherwise) and reachable.
"""

from __future__ import annotations

from app.config import MarketDataLoopConfig
from app.main import _DEFAULT_CONFIG


class TestDefaultConfig:
    def test_default_config_is_valid(self) -> None:
        assert isinstance(_DEFAULT_CONFIG, MarketDataLoopConfig)
        assert _DEFAULT_CONFIG.symbols == ("AAPL",)

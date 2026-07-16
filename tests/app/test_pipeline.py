"""Tests for `app.pipeline.compose_pipeline`."""

from __future__ import annotations

from datetime import datetime, timezone

from app.frame import RuntimeFrame
from app.pipeline import compose_pipeline
from market_data.models import Bar, Timeframe

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _bar() -> Bar:
    return Bar(
        symbol="AAPL",
        timestamp=T0,
        timeframe=Timeframe.DAY_1,
        open=99.0,
        high=101.0,
        low=98.0,
        close=100.0,
        volume=1000.0,
    )


class TestComposePipeline:
    def test_calls_every_stage_in_order_when_all_succeed(self) -> None:
        calls: list[str] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            calls.append("handle_bar")
            return RuntimeFrame(bar=bar)

        def stage_one(frame: RuntimeFrame) -> RuntimeFrame:
            calls.append("stage_one")
            return frame

        def stage_two(frame: RuntimeFrame) -> RuntimeFrame:
            calls.append("stage_two")
            return frame

        on_bar = compose_pipeline(handle_bar, stage_one, stage_two)
        result = on_bar(_bar())

        assert calls == ["handle_bar", "stage_one", "stage_two"]
        assert result is None  # on_bar always discards the final frame

    def test_stops_when_handle_bar_returns_none(self) -> None:
        calls: list[str] = []

        def handle_bar(_bar: Bar) -> None:
            calls.append("handle_bar")
            return None

        def stage_one(frame: RuntimeFrame) -> RuntimeFrame:
            calls.append("stage_one")
            return frame

        on_bar = compose_pipeline(handle_bar, stage_one)
        on_bar(_bar())

        assert calls == ["handle_bar"]

    def test_stops_when_a_middle_stage_returns_none(self) -> None:
        calls: list[str] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            calls.append("handle_bar")
            return RuntimeFrame(bar=bar)

        def stage_one(frame: RuntimeFrame) -> None:
            calls.append("stage_one")
            return None

        def stage_two(frame: RuntimeFrame) -> RuntimeFrame:
            calls.append("stage_two")
            return frame

        on_bar = compose_pipeline(handle_bar, stage_one, stage_two)
        on_bar(_bar())

        assert calls == ["handle_bar", "stage_one"]

    def test_works_with_no_extra_stages(self) -> None:
        calls: list[str] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            calls.append("handle_bar")
            return RuntimeFrame(bar=bar)

        on_bar = compose_pipeline(handle_bar)
        on_bar(_bar())

        assert calls == ["handle_bar"]

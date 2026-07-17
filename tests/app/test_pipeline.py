"""Tests for `app.pipeline.compose_pipeline` and `app.pipeline.PipelineResult`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.frame import RuntimeFrame
from app.pipeline import PipelineResult, compose_pipeline
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


class TestPipelineResultReporting:
    def test_on_result_not_called_by_default(self) -> None:
        # Every build_*_loop before Phase G omits stage_names/on_result
        # entirely -- confirms nothing changes for them.
        def handle_bar(bar: Bar) -> RuntimeFrame:
            return RuntimeFrame(bar=bar)

        on_bar = compose_pipeline(handle_bar, lambda frame: frame)
        on_bar(_bar())  # must not raise even though on_result is None

    def test_on_result_reports_success_with_final_stage_name(self) -> None:
        results: list[PipelineResult] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            return RuntimeFrame(bar=bar)

        def stage_two(frame: RuntimeFrame) -> RuntimeFrame:
            return frame

        on_bar = compose_pipeline(
            handle_bar,
            lambda frame: frame,
            stage_two,
            stage_names=("feature", "regime", "strategy"),
            on_result=results.append,
        )
        on_bar(_bar())

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].completed_stage == "strategy"
        assert results[0].error is None
        assert results[0].frame is not None
        assert results[0].frame.bar.symbol == "AAPL"

    def test_on_result_reports_short_circuit_with_the_frame_going_in(self) -> None:
        results: list[PipelineResult] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            return RuntimeFrame(bar=bar)

        def stage_one(frame: RuntimeFrame) -> None:
            return None

        on_bar = compose_pipeline(
            handle_bar,
            stage_one,
            stage_names=("feature", "regime"),
            on_result=results.append,
        )
        on_bar(_bar())

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].completed_stage == "regime"
        assert results[0].error is None
        # The frame reported is the one going INTO stage_one (all we
        # ever had), not the None stage_one returned.
        assert results[0].frame is not None
        assert results[0].frame.bar.symbol == "AAPL"

    def test_on_result_reports_none_frame_when_handle_bar_itself_fails(self) -> None:
        results: list[PipelineResult] = []

        def handle_bar(_bar: Bar) -> None:
            return None

        on_bar = compose_pipeline(
            handle_bar,
            stage_names=("feature",),
            on_result=results.append,
        )
        on_bar(_bar())

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].completed_stage == "feature"
        assert results[0].frame is None

    def test_on_result_reports_and_reraises_on_an_unexpected_exception(self) -> None:
        results: list[PipelineResult] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            return RuntimeFrame(bar=bar)

        def boom(frame: RuntimeFrame) -> RuntimeFrame:
            raise RuntimeError("stage bug")

        on_bar = compose_pipeline(
            handle_bar,
            boom,
            stage_names=("feature", "regime"),
            on_result=results.append,
        )

        with pytest.raises(RuntimeError, match="stage bug"):
            on_bar(_bar())

        assert len(results) == 1
        assert results[0].success is False
        assert results[0].completed_stage == "regime"
        assert results[0].error == "stage bug"
        # Frame reported is the one going into `boom`, not lost.
        assert results[0].frame is not None
        assert results[0].frame.bar.symbol == "AAPL"

    def test_rejects_stage_names_with_wrong_length(self) -> None:
        def handle_bar(bar: Bar) -> RuntimeFrame:
            return RuntimeFrame(bar=bar)

        with pytest.raises(ValueError, match="stage_names"):
            compose_pipeline(handle_bar, lambda frame: frame, stage_names=("only_one_name",))

    def test_default_stage_names_are_positional_when_omitted(self) -> None:
        results: list[PipelineResult] = []

        def handle_bar(bar: Bar) -> RuntimeFrame:
            return RuntimeFrame(bar=bar)

        on_bar = compose_pipeline(handle_bar, lambda frame: frame, on_result=results.append)
        on_bar(_bar())

        assert results[0].completed_stage == "stage_1"

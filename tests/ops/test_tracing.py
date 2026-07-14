"""Tests for `ops.tracing`: `Span` and `Tracer`."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from common.time import FixedClock
from ops.tracing import Span, Tracer

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)
T1 = datetime(2024, 1, 1, 0, 0, 2, tzinfo=UTC)


class TestSpan:
    def test_valid_span_constructs(self) -> None:
        span = Span(name="fetch_bars", started_at=T0, ended_at=T1)
        assert span.duration_seconds == 2.0

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            Span(name="", started_at=T0, ended_at=T1)

    def test_rejects_naive_started_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Span(name="fetch_bars", started_at=datetime(2024, 1, 1), ended_at=T1)

    def test_rejects_naive_ended_at(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Span(name="fetch_bars", started_at=T0, ended_at=datetime(2024, 1, 1))

    def test_rejects_ended_before_started(self) -> None:
        with pytest.raises(ValueError, match="ended_at"):
            Span(name="fetch_bars", started_at=T1, ended_at=T0)

    def test_is_frozen(self) -> None:
        span = Span(name="fetch_bars", started_at=T0, ended_at=T1)
        with pytest.raises(AttributeError):
            span.name = "other"  # type: ignore[misc]


class TestTracer:
    def test_span_context_manager_yields_control(self) -> None:
        tracer = Tracer()
        ran = False
        with tracer.span("fetch_bars"):
            ran = True
        assert ran is True

    def test_hook_receives_completed_span_with_correct_name(self) -> None:
        clock = FixedClock(T0)
        received: list[Span] = []
        tracer = Tracer(clock=clock, hooks=(received.append,))
        with tracer.span("fetch_bars"):
            clock.advance(seconds=2)
        assert len(received) == 1
        assert received[0].name == "fetch_bars"
        assert received[0].duration_seconds == 2.0

    def test_add_hook_registers_additional_hook(self) -> None:
        tracer = Tracer()
        received: list[Span] = []
        tracer.add_hook(received.append)
        with tracer.span("fetch_bars"):
            pass
        assert len(received) == 1

    def test_multiple_hooks_all_called_in_order(self) -> None:
        order: list[str] = []
        tracer = Tracer(
            hooks=(lambda span: order.append("first"), lambda span: order.append("second"))
        )
        with tracer.span("fetch_bars"):
            pass
        assert order == ["first", "second"]

    def test_hook_called_even_when_block_raises(self) -> None:
        tracer = Tracer()
        received: list[Span] = []
        tracer.add_hook(received.append)
        with pytest.raises(RuntimeError), tracer.span("fetch_bars"):
            raise RuntimeError("boom")
        assert len(received) == 1

    def test_span_carries_metadata(self) -> None:
        received: list[Span] = []
        tracer = Tracer(hooks=(received.append,))
        with tracer.span("fetch_bars", symbol="AAPL"):
            pass
        assert received[0].metadata == {"symbol": "AAPL"}

    def test_uses_system_clock_by_default(self) -> None:
        tracer = Tracer()
        received: list[Span] = []
        tracer.add_hook(received.append)
        with tracer.span("fetch_bars"):
            pass
        assert received[0].started_at.tzinfo is not None

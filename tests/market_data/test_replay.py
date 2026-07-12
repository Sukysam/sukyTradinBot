from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_data.models import Bar, Timeframe
from market_data.replay import HistoricalReplay

UTC = timezone.utc


def _bar(ts: datetime, close: float) -> Bar:
    return Bar(
        symbol="AAPL",
        timestamp=ts,
        timeframe=Timeframe.MIN_1,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )


def test_len_reflects_bar_count() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(minutes=i), 100.0 + i) for i in range(5)]
    assert len(HistoricalReplay(bars)) == 5


def test_sync_iteration_yields_ascending_order_regardless_of_input_order() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(minutes=i), 100.0 + i) for i in range(5)]
    shuffled = [bars[3], bars[0], bars[4], bars[1], bars[2]]

    replay = HistoricalReplay(shuffled)

    assert list(replay) == bars


async def test_run_delivers_every_bar_to_handler_in_order() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(minutes=i), 100.0 + i) for i in range(5)]
    received: list[Bar] = []

    async def handler(bar: Bar) -> None:
        received.append(bar)

    await HistoricalReplay(bars).run(handler)

    assert received == bars


async def test_run_speed_zero_never_sleeps() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [_bar(start + timedelta(minutes=i), 100.0 + i) for i in range(3)]
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def handler(bar: Bar) -> None:
        pass

    await HistoricalReplay(bars).run(handler, speed=0.0, sleep=fake_sleep)

    assert sleeps == []


async def test_run_paced_replay_sleeps_proportional_to_speed() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [_bar(start, 100.0), _bar(start + timedelta(minutes=1), 101.0)]
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    async def handler(bar: Bar) -> None:
        pass

    await HistoricalReplay(bars).run(handler, speed=2.0, sleep=fake_sleep)

    # 60s real gap / speed=2.0 -> 30s simulated sleep
    assert sleeps == [pytest.approx(30.0)]


async def test_run_propagates_handler_exceptions() -> None:
    start = datetime(2026, 6, 1, tzinfo=UTC)
    bars = [_bar(start, 100.0)]

    async def failing_handler(bar: Bar) -> None:
        raise ValueError("consumer blew up")

    with pytest.raises(ValueError, match="consumer blew up"):
        await HistoricalReplay(bars).run(failing_handler)


async def test_empty_replay_completes_without_error() -> None:
    calls = 0

    async def handler(bar: Bar) -> None:
        nonlocal calls
        calls += 1

    await HistoricalReplay([]).run(handler)
    assert calls == 0

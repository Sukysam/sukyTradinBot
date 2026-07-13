"""`BacktestResult` -- the single contract `backtest.engine.BacktestEngine.
run` returns, and the only thing about this package any consumer
(regression tests, `reporting.py`, Milestone 9's Adaptive Learning) is
meant to depend on. Frozen per
docs/engineering-handbook/Architecture/ADR/ADR-014-BacktestResult-Contract.md
*before* this package existed at all; full detail in
"docs/engineering-handbook/Standards/BacktestResult Contract.md".

Also defines `OpenPosition` -- an internal, unfrozen tracking type
`portfolio.PortfolioEngine` uses while a position is still open (before
it closes into a `TradeRecord`). It never appears in `BacktestResult`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from common.time import require_utc
from execution.models import OrderSide


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: float

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if self.equity < 0.0:
            raise ValueError(f"equity must be >= 0.0, got {self.equity}")

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": self.timestamp.isoformat(), "equity": self.equity}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EquityPoint:
        return cls(timestamp=datetime.fromisoformat(data["timestamp"]), equity=data["equity"])


@dataclass(frozen=True)
class TradeRecord:
    """One closed round-trip trade (entry through exit)."""

    symbol: str
    strategy_id: str
    regime_id: int
    side: OrderSide
    entry_timestamp: datetime
    exit_timestamp: datetime
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    holding_period: timedelta

    def __post_init__(self) -> None:
        require_utc(self.entry_timestamp, "entry_timestamp")
        require_utc(self.exit_timestamp, "exit_timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.regime_id < 0:
            raise ValueError(f"regime_id must be >= 0, got {self.regime_id}")
        if self.exit_timestamp <= self.entry_timestamp:
            raise ValueError("exit_timestamp must be after entry_timestamp")
        if self.entry_price <= 0:
            raise ValueError(f"entry_price must be > 0, got {self.entry_price}")
        if self.exit_price <= 0:
            raise ValueError(f"exit_price must be > 0, got {self.exit_price}")
        if self.quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {self.quantity}")
        if self.holding_period != self.exit_timestamp - self.entry_timestamp:
            raise ValueError("holding_period must equal exit_timestamp - entry_timestamp")
        if self.holding_period <= timedelta(0):
            raise ValueError("holding_period must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "strategy_id": self.strategy_id,
            "regime_id": self.regime_id,
            "side": self.side.value,
            "entry_timestamp": self.entry_timestamp.isoformat(),
            "exit_timestamp": self.exit_timestamp.isoformat(),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "holding_period_seconds": self.holding_period.total_seconds(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TradeRecord:
        return cls(
            symbol=data["symbol"],
            strategy_id=data["strategy_id"],
            regime_id=data["regime_id"],
            side=OrderSide(data["side"]),
            entry_timestamp=datetime.fromisoformat(data["entry_timestamp"]),
            exit_timestamp=datetime.fromisoformat(data["exit_timestamp"]),
            entry_price=data["entry_price"],
            exit_price=data["exit_price"],
            quantity=data["quantity"],
            pnl=data["pnl"],
            pnl_pct=data["pnl_pct"],
            holding_period=timedelta(seconds=data["holding_period_seconds"]),
        )


@dataclass(frozen=True)
class ReplayRun:
    """Reproducibility metadata for one backtest run -- see ADR-014
    Decision 5. Embedded in `BacktestResult.replay_run`."""

    run_id: str
    dataset: str
    pipeline_versions: Mapping[str, str]
    git_commit: str
    timestamp: datetime

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if not self.dataset.strip():
            raise ValueError("dataset must not be empty")
        if not self.git_commit.strip():
            raise ValueError("git_commit must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "dataset": self.dataset,
            "pipeline_versions": dict(self.pipeline_versions),
            "git_commit": self.git_commit,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReplayRun:
        return cls(
            run_id=data["run_id"],
            dataset=data["dataset"],
            pipeline_versions=dict(data["pipeline_versions"]),
            git_commit=data["git_commit"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


@dataclass(frozen=True)
class BacktestResult:
    """One completed backtest run's full record -- a run-level summary,
    not a single-event snapshot like every other contract in this
    handbook. See Standards/BacktestResult Contract.md."""

    start_date: datetime
    end_date: datetime
    symbols: tuple[str, ...]
    initial_equity: float
    final_equity: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    average_holding_period: timedelta
    exposure: float
    turnover: float
    trade_log: tuple[TradeRecord, ...]
    equity_curve: tuple[EquityPoint, ...]
    replay_run: ReplayRun
    generated_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_utc(self.start_date, "start_date")
        require_utc(self.end_date, "end_date")
        require_utc(self.generated_at, "generated_at")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        if not self.symbols:
            raise ValueError("symbols must not be empty")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("symbols must not contain duplicates")
        if self.initial_equity <= 0:
            raise ValueError(f"initial_equity must be > 0, got {self.initial_equity}")
        if self.final_equity < 0:
            raise ValueError(f"final_equity must be >= 0, got {self.final_equity}")
        if not 0.0 <= self.max_drawdown <= 1.0:
            raise ValueError(f"max_drawdown must be in [0.0, 1.0], got {self.max_drawdown}")
        if not 0.0 <= self.win_rate <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {self.win_rate}")
        if self.profit_factor < 0.0:
            raise ValueError(f"profit_factor must be >= 0.0, got {self.profit_factor}")
        if self.average_holding_period < timedelta(0):
            raise ValueError("average_holding_period must be >= timedelta(0)")
        if not 0.0 <= self.exposure <= 1.0:
            raise ValueError(f"exposure must be in [0.0, 1.0], got {self.exposure}")
        if self.turnover < 0.0:
            raise ValueError(f"turnover must be >= 0.0, got {self.turnover}")
        if not self.equity_curve:
            raise ValueError("equity_curve must not be empty")
        for prev_point, curr_point in zip(self.equity_curve, self.equity_curve[1:]):
            if curr_point.timestamp <= prev_point.timestamp:
                raise ValueError("equity_curve must be strictly ascending by timestamp")
        if self.equity_curve[0].equity != self.initial_equity:
            raise ValueError("equity_curve[0].equity must equal initial_equity")
        for prev_trade, curr_trade in zip(self.trade_log, self.trade_log[1:]):
            if curr_trade.exit_timestamp < prev_trade.exit_timestamp:
                raise ValueError("trade_log must be ascending by exit_timestamp")

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "symbols": list(self.symbols),
            "initial_equity": self.initial_equity,
            "final_equity": self.final_equity,
            "cagr": self.cagr,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "calmar_ratio": self.calmar_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "average_holding_period_seconds": self.average_holding_period.total_seconds(),
            "exposure": self.exposure,
            "turnover": self.turnover,
            "trade_log": [t.to_dict() for t in self.trade_log],
            "equity_curve": [e.to_dict() for e in self.equity_curve],
            "replay_run": self.replay_run.to_dict(),
            "generated_at": self.generated_at.isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BacktestResult:
        return cls(
            start_date=datetime.fromisoformat(data["start_date"]),
            end_date=datetime.fromisoformat(data["end_date"]),
            symbols=tuple(data["symbols"]),
            initial_equity=data["initial_equity"],
            final_equity=data["final_equity"],
            cagr=data["cagr"],
            sharpe_ratio=data["sharpe_ratio"],
            sortino_ratio=data["sortino_ratio"],
            calmar_ratio=data["calmar_ratio"],
            max_drawdown=data["max_drawdown"],
            win_rate=data["win_rate"],
            profit_factor=data["profit_factor"],
            average_holding_period=timedelta(seconds=data["average_holding_period_seconds"]),
            exposure=data["exposure"],
            turnover=data["turnover"],
            trade_log=tuple(TradeRecord.from_dict(t) for t in data["trade_log"]),
            equity_curve=tuple(EquityPoint.from_dict(e) for e in data["equity_curve"]),
            replay_run=ReplayRun.from_dict(data["replay_run"]),
            generated_at=datetime.fromisoformat(data["generated_at"]),
            metadata=dict(data["metadata"]),
        )


@dataclass(frozen=True)
class OpenPosition:
    """Internal, unfrozen tracking type for one currently-open position --
    never appears in `BacktestResult`. `portfolio.PortfolioEngine` closes
    an `OpenPosition` into a `TradeRecord` on exit."""

    symbol: str
    sector: str
    strategy_id: str
    regime_id: int
    entry_timestamp: datetime
    entry_price: float
    quantity: int

    def __post_init__(self) -> None:
        require_utc(self.entry_timestamp, "entry_timestamp")
        if not self.symbol:
            raise ValueError("symbol must not be empty")
        if self.entry_price <= 0:
            raise ValueError(f"entry_price must be > 0, got {self.entry_price}")
        if self.quantity < 1:
            raise ValueError(f"quantity must be >= 1, got {self.quantity}")

    def market_value(self, current_price: float) -> float:
        """Mark-to-market value at `current_price` -- deliberately not a
        cached property, since the right price to mark at changes every
        replay step and this type has no notion of "now" itself."""
        return current_price * self.quantity


__all__ = [
    "BacktestResult",
    "EquityPoint",
    "OpenPosition",
    "ReplayRun",
    "TradeRecord",
]

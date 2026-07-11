"""Continuous Learning Loop: Thompson Sampling contextual bandit over closed
trades (Spec Sec. 4).

Each "arm" is a (strategy, regime, RSI-bucket) setup -- e.g. exactly the
spec's own example, "RSI > 70 in a BULL regime". Every arm carries a
Beta(alpha, beta) posterior over "this setup is profitable"; closed trades
update it (alpha += 1 on a win, beta += 1 on a loss), and posteriors persist
to `learning_weights.json` so they accumulate across weekly cron runs instead
of resetting each time.

Scope note: the context key is deliberately narrow -- strategy x regime x RSI
bucket -- because that is the exact example the spec gives. Extending it to
also bucket on ADX/volatility would multiply the arm count and dilute the
sample count per arm; treat that as a deliberate follow-up decision, not an
oversight.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS_PATH = Path("data/learning_weights.json")
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
PRIOR_ALPHA = 1.0  # Beta(1,1) == uniform prior: no arm is assumed good or bad before evidence
PRIOR_BETA = 1.0


# --------------------------------------------------------------------------
# Trade context (read side of trade_context_db.json)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TradeContext:
    """One row of trade_context_db.json, as written by `signal_generator.py`
    on entry and completed on position closure (Spec Sec. 4). `regime_label`
    is whatever tier/state name the strategy layer assigns (e.g. "LOW_VOL",
    "MID_VOL", "HIGH_VOL", "NEUTRAL") -- this module treats it as an opaque
    string rather than importing `hmm_engine`/`regime_strategies`, so the two
    modules don't have to agree on an internal representation, only on this
    string contract.
    """

    trade_id: str
    strategy: str
    regime_label: str
    rsi_14: float
    entry_timestamp: str
    exit_timestamp: str | None = None
    pnl: float | None = None

    @property
    def is_closed(self) -> bool:
        return self.pnl is not None and self.exit_timestamp is not None


def load_trade_contexts(path: Path) -> list[TradeContext]:
    if not path.exists():
        raise FileNotFoundError(f"Trade context DB not found at {path}")

    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON list of trade contexts in {path}, got {type(raw).__name__}")

    contexts = []
    for i, entry in enumerate(raw):
        try:
            contexts.append(
                TradeContext(
                    trade_id=entry["trade_id"],
                    strategy=entry["strategy"],
                    regime_label=entry["regime_label"],
                    rsi_14=float(entry["rsi_14"]),
                    entry_timestamp=entry["entry_timestamp"],
                    exit_timestamp=entry.get("exit_timestamp"),
                    pnl=entry.get("pnl"),
                )
            )
        except KeyError as exc:
            raise ValueError(f"Trade context entry {i} missing required field: {exc}") from exc
    return contexts


# --------------------------------------------------------------------------
# Context key
# --------------------------------------------------------------------------

def _rsi_bucket(rsi_14: float) -> str:
    if rsi_14 >= RSI_OVERBOUGHT:
        return "RSI_OVERBOUGHT"
    if rsi_14 <= RSI_OVERSOLD:
        return "RSI_OVERSOLD"
    return "RSI_NEUTRAL"


def context_key(strategy: str, regime_label: str, rsi_14: float) -> tuple[str, str, str]:
    return (strategy, regime_label, _rsi_bucket(rsi_14))


def _serialize_key(key: tuple[str, str, str]) -> str:
    return "|".join(key)


# --------------------------------------------------------------------------
# Beta-Bernoulli arm
# --------------------------------------------------------------------------

@dataclass
class BetaArm:
    alpha: float = PRIOR_ALPHA
    beta: float = PRIOR_BETA

    @property
    def posterior_mean(self) -> float:
        """Deterministic confidence weight in (0, 1) -- for inspection/logging,
        not live decisioning (see `LearningEngine.sample_confidence_weight`)."""
        return self.alpha / (self.alpha + self.beta)

    @property
    def n_observations(self) -> int:
        return int(self.alpha + self.beta - PRIOR_ALPHA - PRIOR_BETA)

    def sample(self, rng: np.random.Generator) -> float:
        return float(rng.beta(self.alpha, self.beta))

    def update(self, won: bool) -> None:
        if won:
            self.alpha += 1.0
        else:
            self.beta += 1.0


@dataclass(frozen=True)
class WeeklyOptimizationReport:
    trades_updated: int
    trades_skipped: int
    arm_snapshot: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------

class LearningEngine:
    """Thompson Sampling contextual bandit over (strategy, regime, RSI-bucket)
    arms. Posterior state persists to `weights_path` so it survives process
    restarts and compounds across weekly runs rather than resetting.
    """

    def __init__(self, weights_path: Path = DEFAULT_WEIGHTS_PATH, seed: int | None = None):
        self.weights_path = weights_path
        self._rng = np.random.default_rng(seed)
        self._arms: dict[str, BetaArm] = self._load_weights()

    def _load_weights(self) -> dict[str, BetaArm]:
        if not self.weights_path.exists():
            return {}
        raw = json.loads(self.weights_path.read_text())
        return {k: BetaArm(alpha=v["alpha"], beta=v["beta"]) for k, v in raw.items()}

    def _save_weights(self) -> None:
        serializable = {k: {"alpha": arm.alpha, "beta": arm.beta} for k, arm in self._arms.items()}
        self.weights_path.parent.mkdir(parents=True, exist_ok=True)
        self.weights_path.write_text(json.dumps(serializable, indent=2, sort_keys=True))

    def _get_or_create_arm(self, key: tuple[str, str, str]) -> BetaArm:
        skey = _serialize_key(key)
        if skey not in self._arms:
            self._arms[skey] = BetaArm()
        return self._arms[skey]

    def posterior_mean(self, strategy: str, regime_label: str, rsi_14: float) -> float:
        key = context_key(strategy, regime_label, rsi_14)
        return self._get_or_create_arm(key).posterior_mean

    def sample_confidence_weight(self, strategy: str, regime_label: str, rsi_14: float) -> float:
        """Draw a live Thompson sample from the arm's posterior. This is what
        `signal_generator.py` should call at decision time to scale proposed
        allocation for a given setup: arms with few observations have wide
        posteriors and occasionally sample high (exploration), while arms
        with a consistent losing record cluster near zero (exploitation) --
        both fall out of the same Beta draw with no extra branching needed.
        """
        key = context_key(strategy, regime_label, rsi_14)
        return self._get_or_create_arm(key).sample(self._rng)

    def update_from_trade(self, trade: TradeContext) -> None:
        if not trade.is_closed:
            raise ValueError(f"Trade {trade.trade_id} has no PnL/exit_timestamp; cannot update a bandit from an open trade")
        key = context_key(trade.strategy, trade.regime_label, trade.rsi_14)
        self._get_or_create_arm(key).update(won=trade.pnl > 0)

    def run_weekly_optimization(
        self,
        trade_context_db_path: Path,
        as_of: datetime | None = None,
    ) -> WeeklyOptimizationReport:
        """Spec Sec. 6 weekend cron entrypoint. Updates arm posteriors from
        every trade closed within the trailing 7 days of `as_of` (default:
        now, UTC), then persists. Trades that are still open, or that closed
        outside the window, are skipped -- this keeps the job idempotent to
        re-run and prevents a trade from being counted twice across
        consecutive weekly runs.
        """
        as_of = as_of or datetime.now(timezone.utc)
        window_start = as_of - timedelta(days=7)

        contexts = load_trade_contexts(trade_context_db_path)
        updated, skipped = 0, 0
        for trade in contexts:
            if not trade.is_closed:
                skipped += 1
                continue
            exit_ts = datetime.fromisoformat(trade.exit_timestamp)
            if exit_ts.tzinfo is None:
                exit_ts = exit_ts.replace(tzinfo=timezone.utc)
            if not (window_start <= exit_ts <= as_of):
                skipped += 1
                continue
            self.update_from_trade(trade)
            updated += 1

        self._save_weights()
        logger.info(
            "Weekly optimization: %d trades updated, %d skipped, %d arms tracked",
            updated, skipped, len(self._arms),
        )
        return WeeklyOptimizationReport(
            trades_updated=updated,
            trades_skipped=skipped,
            arm_snapshot={
                k: {"alpha": a.alpha, "beta": a.beta, "posterior_mean": a.posterior_mean, "n": a.n_observations}
                for k, a in self._arms.items()
            },
        )

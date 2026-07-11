"""
Runs the SMA optimization and dumps everything needed for a report:
full grid results, and equity curves (train+test) for the top candidates
plus buy & hold, each paired with real timestamps.
"""
import json
import sys
from datetime import datetime, timezone

from sma_crossover import fetch_klines_paginated, backtest, sma
from optimize_sma import grid_search

SYMBOL = "BTCUSDT"
INTERVAL = "1h"
TOTAL = 3000
TOP_N_CURVES = 3


def equity_curve(closes, times, fast_window, slow_window, fee_pct=0.1):
    fast = sma(closes, fast_window)
    slow = sma(closes, slow_window)
    fee = fee_pct / 100

    position = None
    equity = 1.0
    curve = []
    for i in range(len(closes)):
        if fast[i] is not None and slow[i] is not None and position is not None:
            unrealized = (closes[i] - position) / position
            curve.append({"t": times[i], "equity": equity * (1 + unrealized)})
        else:
            curve.append({"t": times[i], "equity": equity})

        if i == 0 or fast[i - 1] is None or slow[i - 1] is None:
            continue
        crossed_up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        crossed_down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        if crossed_up and position is None:
            position = closes[i]
        elif crossed_down and position is not None:
            ret = (closes[i] - position) / position - 2 * fee
            equity *= (1 + ret)
            position = None
            curve[-1]["equity"] = equity
    return curve


def buy_hold_curve(closes, times):
    base = closes[0]
    return [{"t": t, "equity": c / base} for t, c in zip(times, closes)]


def main():
    klines = fetch_klines_paginated(SYMBOL, INTERVAL, TOTAL)
    closes = [k["close"] for k in klines]
    times = [datetime.fromtimestamp(k["open_time"] / 1000, tz=timezone.utc).isoformat() for k in klines]

    split = int(len(closes) * 0.7)
    train_closes = closes[:split]

    ranked = grid_search(train_closes)
    top = [r for r in ranked if r["score"] != float("-inf")][:TOP_N_CURVES]

    full_grid = [
        {"fast": r["fast"], "slow": r["slow"], "trades": r["num_trades"],
         "win_rate": round(r["win_rate"] * 100, 1), "train_return": round(r["total_return_pct"], 2),
         "train_dd": round(r["max_drawdown_pct"], 2), "score": round(r["score"], 2)}
        for r in ranked if r["score"] != float("-inf")
    ]

    strategies = []
    for r in top:
        test_closes = closes[split:]
        t = backtest(test_closes, r["fast"], r["slow"])
        curve = equity_curve(closes, times, r["fast"], r["slow"])
        strategies.append({
            "label": f"SMA({r['fast']},{r['slow']})",
            "fast": r["fast"], "slow": r["slow"],
            "train_return": round(r["total_return_pct"], 2),
            "train_dd": round(r["max_drawdown_pct"], 2),
            "test_return": round(t["total_return_pct"], 2),
            "test_dd": round(t["max_drawdown_pct"], 2),
            "test_trades": t["num_trades"],
            "curve": curve,
        })

    bh_curve = buy_hold_curve(closes, times)

    out = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "total_candles": len(closes),
        "split_index": split,
        "split_time": times[split],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "full_grid": full_grid,
        "strategies": strategies,
        "buy_hold_curve": bh_curve,
    }

    with open(sys.argv[1] if len(sys.argv) > 1 else "report_data.json", "w") as f:
        json.dump(out, f)
    print("wrote report data")


if __name__ == "__main__":
    main()

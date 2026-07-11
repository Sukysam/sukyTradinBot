"""
SMA crossover backtest against Binance public klines.
Usage: python3 sma_crossover.py [SYMBOL] [INTERVAL] [FAST] [SLOW] [LIMIT]
"""
import sys
import urllib.request
import json

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def fetch_klines(symbol="BTCUSDT", interval="1h", limit=1000):
    url = f"{BINANCE_KLINES_URL}?symbol={symbol}&interval={interval}&limit={limit}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        raw = json.loads(resp.read())
    return [
        {"open_time": row[0], "close": float(row[4])}
        for row in raw
    ]


def fetch_klines_paginated(symbol="BTCUSDT", interval="1h", total=3000):
    """Fetch more than Binance's 1000-candle-per-request cap by paging backwards in time."""
    all_rows = []
    end_time = None
    while len(all_rows) < total:
        batch_limit = min(1000, total - len(all_rows))
        url = f"{BINANCE_KLINES_URL}?symbol={symbol}&interval={interval}&limit={batch_limit}"
        if end_time is not None:
            url += f"&endTime={end_time}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            raw = json.loads(resp.read())
        if not raw:
            break
        all_rows = raw + all_rows
        end_time = raw[0][0] - 1
        if len(raw) < batch_limit:
            break
    return [{"open_time": row[0], "close": float(row[4])} for row in all_rows]


def sma(values, window):
    out = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def backtest(closes, fast_window, slow_window, fee_pct=0.1):
    """fee_pct is per-side (e.g. 0.1 = 0.1% taker fee), charged on entry and exit."""
    fast = sma(closes, fast_window)
    slow = sma(closes, slow_window)
    fee = fee_pct / 100

    position = None  # entry price while long, else None
    equity = 1.0
    trades = []

    for i in range(1, len(closes)):
        if fast[i - 1] is None or slow[i - 1] is None:
            continue
        crossed_up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        crossed_down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]

        if crossed_up and position is None:
            position = closes[i]
        elif crossed_down and position is not None:
            ret = (closes[i] - position) / position - 2 * fee
            equity *= (1 + ret)
            trades.append(ret)
            position = None

    if position is not None:
        ret = (closes[-1] - position) / position - 2 * fee
        equity *= (1 + ret)
        trades.append(ret)

    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]

    curve = [1.0]
    for t in trades:
        curve.append(curve[-1] * (1 + t))
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    return {
        "num_trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "total_return_pct": (equity - 1) * 100,
        "buy_hold_return_pct": (closes[-1] - closes[0]) / closes[0] * 100,
        "avg_win_pct": (sum(wins) / len(wins) * 100) if wins else 0.0,
        "avg_loss_pct": (sum(losses) / len(losses) * 100) if losses else 0.0,
        "max_drawdown_pct": max_dd * 100,
    }


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "1h"
    fast_window = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    slow_window = int(sys.argv[4]) if len(sys.argv) > 4 else 50
    limit = int(sys.argv[5]) if len(sys.argv) > 5 else 1000

    klines = fetch_klines(symbol, interval, limit)
    closes = [k["close"] for k in klines]

    print(f"Fetched {len(closes)} {interval} candles for {symbol}")
    print(f"Strategy: SMA({fast_window}) / SMA({slow_window}) crossover\n")

    results = backtest(closes, fast_window, slow_window)
    for k, v in results.items():
        if isinstance(v, float):
            print(f"{k:22s} {v:.2f}")
        else:
            print(f"{k:22s} {v}")


if __name__ == "__main__":
    main()

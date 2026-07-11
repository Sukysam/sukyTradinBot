"""
Grid-search SMA crossover windows on BTC/USDT 1h data, with a train/test
split so results aren't just overfit to a single historical window.

Usage: python3 optimize_sma.py [SYMBOL] [INTERVAL] [TOTAL_CANDLES]
"""
import sys

from sma_crossover import fetch_klines_paginated, backtest

FAST_RANGE = range(5, 55, 5)     # 5,10,...,50
SLOW_RANGE = range(20, 220, 20)  # 20,40,...,200
MIN_GAP = 10                     # require slow - fast >= this, avoid noisy near-duplicate crossovers
MIN_TRADES = 5                   # discard combos with too few trades to mean anything


def score(result):
    # Calmar-like: return per unit of max drawdown. Penalize thin trade counts.
    if result["num_trades"] < MIN_TRADES:
        return float("-inf")
    dd = max(result["max_drawdown_pct"], 1.0)
    return result["total_return_pct"] / dd


def grid_search(closes):
    results = []
    for fast in FAST_RANGE:
        for slow in SLOW_RANGE:
            if slow - fast < MIN_GAP:
                continue
            r = backtest(closes, fast, slow)
            r["fast"] = fast
            r["slow"] = slow
            r["score"] = score(r)
            results.append(r)
    return sorted(results, key=lambda r: r["score"], reverse=True)


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "1h"
    total = int(sys.argv[3]) if len(sys.argv) > 3 else 3000

    print(f"Fetching {total} {interval} candles for {symbol}...")
    klines = fetch_klines_paginated(symbol, interval, total)
    closes = [k["close"] for k in klines]
    print(f"Got {len(closes)} candles\n")

    split = int(len(closes) * 0.7)
    train, test = closes[:split], closes[split:]
    print(f"Train: {len(train)} candles | Test (out-of-sample): {len(test)} candles\n")

    ranked = grid_search(train)
    top5 = [r for r in ranked if r["score"] != float("-inf")][:5]

    print("Top 5 on TRAIN data (ranked by return/drawdown):")
    print(f"{'fast':>5} {'slow':>5} {'trades':>7} {'win%':>7} {'return%':>9} {'maxdd%':>8} {'score':>7}")
    for r in top5:
        print(f"{r['fast']:>5} {r['slow']:>5} {r['num_trades']:>7} "
              f"{r['win_rate']*100:>6.1f} {r['total_return_pct']:>9.2f} "
              f"{r['max_drawdown_pct']:>8.2f} {r['score']:>7.2f}")

    print(f"\nBuy & hold on train: {(train[-1]-train[0])/train[0]*100:.2f}%\n")

    print("Same params evaluated OUT-OF-SAMPLE (test set) — this is what actually matters:")
    print(f"{'fast':>5} {'slow':>5} {'trades':>7} {'win%':>7} {'return%':>9} {'maxdd%':>8}")
    for r in top5:
        t = backtest(test, r["fast"], r["slow"])
        print(f"{r['fast']:>5} {r['slow']:>5} {t['num_trades']:>7} "
              f"{t['win_rate']*100:>6.1f} {t['total_return_pct']:>9.2f} "
              f"{t['max_drawdown_pct']:>8.2f}")

    print(f"\nBuy & hold on test: {(test[-1]-test[0])/test[0]*100:.2f}%")


if __name__ == "__main__":
    main()

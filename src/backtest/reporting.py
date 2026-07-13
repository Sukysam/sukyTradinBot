"""`generate_report` -- a minimal, human-readable text summary of a
`BacktestResult`. Consumes the contract, never shapes it (ADR-014
Scope). Not a frozen contract itself: this is a rendering, free to
change shape without a new ADR.
"""

from __future__ import annotations

from backtest.models import BacktestResult


def generate_report(result: BacktestResult) -> str:
    symbols = ", ".join(result.symbols)
    total_return_pct = (result.final_equity / result.initial_equity - 1.0) * 100.0
    lines = [
        f"Backtest Report -- {result.replay_run.dataset}",
        f"  run_id:        {result.replay_run.run_id}",
        f"  git_commit:    {result.replay_run.git_commit}",
        f"  period:        {result.start_date.date()} to {result.end_date.date()}",
        f"  symbols:       {symbols}",
        "",
        f"  initial_equity:  ${result.initial_equity:,.2f}",
        f"  final_equity:    ${result.final_equity:,.2f}",
        f"  total_return:    {total_return_pct:+.2f}%",
        f"  cagr:            {result.cagr:+.2%}",
        "",
        f"  sharpe_ratio:    {result.sharpe_ratio:.2f}",
        f"  sortino_ratio:   {result.sortino_ratio:.2f}",
        f"  calmar_ratio:    {result.calmar_ratio:.2f}",
        f"  max_drawdown:    {result.max_drawdown:.2%}",
        "",
        f"  trades:          {len(result.trade_log)}",
        f"  win_rate:        {result.win_rate:.2%}",
        f"  profit_factor:   {result.profit_factor:.2f}",
        f"  avg_holding:     {result.average_holding_period}",
        f"  exposure:        {result.exposure:.2%}",
        f"  turnover:        {result.turnover:.2f}",
    ]
    return "\n".join(lines)


__all__ = ["generate_report"]

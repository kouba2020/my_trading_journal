from __future__ import annotations

import pandas as pd
import numpy as np


def equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["exit_time", "net_pnl", "equity"])
    eq = trades.sort_values("exit_time")[["exit_time", "net_pnl"]].copy()
    eq["equity"] = eq["net_pnl"].cumsum()
    return eq


def max_drawdown(trades: pd.DataFrame) -> float:
    eq = equity_curve(trades)
    if eq.empty:
        return 0.0
    running_max = eq["equity"].cummax()
    dd = eq["equity"] - running_max
    return float(dd.min())


def summary_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {
            "total_trades": 0, "net_pnl": 0.0, "win_rate": 0.0,
            "profit_factor": 0.0, "expectancy": 0.0, "avg_win": 0.0,
            "avg_loss": 0.0, "largest_win": 0.0, "largest_loss": 0.0,
            "max_drawdown": 0.0, "avg_hold_minutes": 0.0,
        }

    pnl = trades["net_pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = wins.sum()
    gross_loss = abs(losses.sum())
    total = len(trades)

    return {
        "total_trades": int(total),
        "net_pnl": float(pnl.sum()),
        "win_rate": float((pnl > 0).mean() * 100),
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else float("inf") if gross_profit else 0.0,
        "expectancy": float(pnl.mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "largest_win": float(pnl.max()),
        "largest_loss": float(pnl.min()),
        "max_drawdown": max_drawdown(trades),
        "avg_hold_minutes": float(trades["hold_minutes"].dropna().mean()) if "hold_minutes" in trades else 0.0,
    }


def group_report(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    if trades.empty or by not in trades.columns:
        return pd.DataFrame()
    report = trades.groupby(by).agg(
        trades=("net_pnl", "count"),
        net_pnl=("net_pnl", "sum"),
        avg_pnl=("net_pnl", "mean"),
        win_rate=("net_pnl", lambda s: (s > 0).mean() * 100),
        avg_hold_min=("hold_minutes", "mean"),
    ).reset_index()
    return report.sort_values("net_pnl", ascending=False)

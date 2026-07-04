from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional

REQUIRED_COLUMNS = ["Symbol", "Action", "Fill qty", "Fill price", "Exec time"]


def clean_executions(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a broker executions CSV into a predictable dataframe."""
    df = df.copy()
    df = df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")], errors="ignore")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df["Action"] = df["Action"].astype(str).str.strip().str.lower()
    df["qty"] = pd.to_numeric(df["Fill qty"], errors="coerce").fillna(0).astype(float)
    df["price"] = pd.to_numeric(df["Fill price"], errors="coerce").astype(float)
    df["exec_time"] = pd.to_datetime(df["Exec time"], format="%d %b %Y %I:%M:%S %p", errors="coerce")

    if "Account" not in df.columns:
        df["Account"] = "Default"
    df["Account"] = df["Account"].fillna("Default").astype(str).str.strip()

    df = df.dropna(subset=["exec_time", "price"])
    df = df[df["qty"] > 0]
    df = df[df["Action"].isin(["buy", "sell"])]
    df = df.sort_values(["exec_time", "Symbol"]).reset_index(drop=True)
    df["signed_qty"] = np.where(df["Action"].eq("buy"), df["qty"], -df["qty"])
    df["notional"] = df["qty"] * df["price"]
    return df


@dataclass
class OpenTrade:
    account: str
    symbol: str
    side: Optional[str] = None  # Long or Short
    entry_time: Optional[pd.Timestamp] = None
    exit_time: Optional[pd.Timestamp] = None
    position: float = 0.0  # positive long, negative short
    entry_qty: float = 0.0
    exit_qty: float = 0.0
    entry_value: float = 0.0
    exit_value: float = 0.0
    realized_pnl: float = 0.0
    executions: int = 0

    def reset(self) -> None:
        self.side = None
        self.entry_time = None
        self.exit_time = None
        self.position = 0.0
        self.entry_qty = 0.0
        self.exit_qty = 0.0
        self.entry_value = 0.0
        self.exit_value = 0.0
        self.realized_pnl = 0.0
        self.executions = 0

    def avg_entry(self) -> float:
        return self.entry_value / self.entry_qty if self.entry_qty else 0.0

    def avg_exit(self) -> float:
        return self.exit_value / self.exit_qty if self.exit_qty else 0.0

    def close_record(self) -> dict:
        hold_minutes = None
        if self.entry_time is not None and self.exit_time is not None:
            hold_minutes = (self.exit_time - self.entry_time).total_seconds() / 60
        return {
            "account": self.account,
            "symbol": self.symbol,
            "side": self.side,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "shares": self.exit_qty,
            "avg_entry": self.avg_entry(),
            "avg_exit": self.avg_exit(),
            "gross_pnl": self.realized_pnl,
            "net_pnl": self.realized_pnl,
            "hold_minutes": hold_minutes,
            "executions": self.executions,
        }


def reconstruct_trades(executions: pd.DataFrame) -> pd.DataFrame:
    """
    Reconstruct round-trip trades using average-cost logic.

    A trade starts when a symbol/account goes from flat to non-flat and closes
    when it returns to flat. Handles scaling in, scaling out, and reversals.
    """
    df = clean_executions(executions)
    states: Dict[Tuple[str, str], OpenTrade] = {}
    closed: List[dict] = []

    for _, row in df.iterrows():
        key = (row["Account"], row["Symbol"])
        state = states.setdefault(key, OpenTrade(account=row["Account"], symbol=row["Symbol"]))

        qty = float(row["qty"])
        signed_qty = float(row["signed_qty"])
        price = float(row["price"])
        t = row["exec_time"]

        remaining_signed = signed_qty

        while abs(remaining_signed) > 1e-9:
            # Flat: open a new trade.
            if abs(state.position) < 1e-9:
                state.reset()
                state.account = row["Account"]
                state.symbol = row["Symbol"]
                state.side = "Long" if remaining_signed > 0 else "Short"
                state.entry_time = t
                state.position = remaining_signed
                state.entry_qty = abs(remaining_signed)
                state.entry_value = abs(remaining_signed) * price
                state.executions = 1
                remaining_signed = 0.0
                continue

            same_direction = (state.position > 0 and remaining_signed > 0) or (state.position < 0 and remaining_signed < 0)

            # Add to the existing position.
            if same_direction:
                state.position += remaining_signed
                state.entry_qty += abs(remaining_signed)
                state.entry_value += abs(remaining_signed) * price
                state.executions += 1
                remaining_signed = 0.0
                continue

            # Opposite direction: reduce/close/reverse.
            closing_qty = min(abs(state.position), abs(remaining_signed))
            avg_entry = state.avg_entry()

            if state.position > 0:  # closing long with a sell
                pnl = (price - avg_entry) * closing_qty
                state.position -= closing_qty
                remaining_signed += closing_qty
            else:  # closing short with a buy
                pnl = (avg_entry - price) * closing_qty
                state.position += closing_qty
                remaining_signed -= closing_qty

            state.exit_qty += closing_qty
            state.exit_value += closing_qty * price
            state.realized_pnl += pnl
            state.exit_time = t
            state.executions += 1

            # If flat, record closed trade. If there is remaining quantity, loop opens reversal.
            if abs(state.position) < 1e-9:
                closed.append(state.close_record())
                state.reset()
                state.account = row["Account"]
                state.symbol = row["Symbol"]

    trades = pd.DataFrame(closed)
    if trades.empty:
        return trades

    trades["date"] = pd.to_datetime(trades["exit_time"]).dt.date
    trades["weekday"] = pd.to_datetime(trades["exit_time"]).dt.day_name()
    trades["entry_hour"] = pd.to_datetime(trades["entry_time"]).dt.hour
    trades["r_multiple"] = np.nan  # placeholder for later risk-based journaling
    return trades

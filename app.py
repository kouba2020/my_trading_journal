from __future__ import annotations

import io
import pandas as pd
import streamlit as st
import plotly.express as px

from engine.reconstruction import clean_executions, reconstruct_trades
from engine.metrics import summary_metrics, equity_curve, group_report

st.set_page_config(page_title="Trading Journal MVP", page_icon="📈", layout="wide")

st.title("📈 Trading Journal MVP")
st.caption("Tradervue-style first version: upload executions, reconstruct trades, and analyze metrics.")

with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Upload broker executions CSV", type=["csv"])
    use_sample = st.checkbox("Use included sample CSV", value=uploaded is None)
    commission_per_trade = st.number_input("Commission/fees per closed trade", min_value=0.0, value=0.0, step=0.01)

@st.cache_data
def load_csv(file_bytes: bytes | None, use_sample: bool) -> pd.DataFrame:
    if file_bytes is not None:
        return pd.read_csv(io.BytesIO(file_bytes))
    if use_sample:
        return pd.read_csv("data/Executions_15juin.csv")
    return pd.DataFrame()

raw = load_csv(uploaded.getvalue() if uploaded else None, use_sample)

if raw.empty:
    st.info("Upload your executions CSV to begin.")
    st.stop()

try:
    executions = clean_executions(raw)
    trades = reconstruct_trades(raw)
except Exception as e:
    st.error(f"Could not process file: {e}")
    st.stop()

if not trades.empty and commission_per_trade:
    trades["net_pnl"] = trades["gross_pnl"] - commission_per_trade

metrics = summary_metrics(trades)

st.subheader("Summary")
cols = st.columns(6)
cols[0].metric("Closed Trades", f"{metrics['total_trades']:,}")
cols[1].metric("Net P&L", f"${metrics['net_pnl']:,.2f}")
cols[2].metric("Win Rate", f"{metrics['win_rate']:.1f}%")
cols[3].metric("Profit Factor", "∞" if metrics['profit_factor'] == float('inf') else f"{metrics['profit_factor']:.2f}")
cols[4].metric("Expectancy", f"${metrics['expectancy']:,.2f}")
cols[5].metric("Max Drawdown", f"${metrics['max_drawdown']:,.2f}")

cols2 = st.columns(4)
cols2[0].metric("Avg Win", f"${metrics['avg_win']:,.2f}")
cols2[1].metric("Avg Loss", f"${metrics['avg_loss']:,.2f}")
cols2[2].metric("Largest Win", f"${metrics['largest_win']:,.2f}")
cols2[3].metric("Largest Loss", f"${metrics['largest_loss']:,.2f}")

st.divider()

left, right = st.columns([2, 1])

with left:
    st.subheader("Equity Curve")
    eq = equity_curve(trades)
    if not eq.empty:
        st.plotly_chart(px.line(eq, x="exit_time", y="equity", markers=True), use_container_width=True)
    else:
        st.warning("No closed trades found yet.")

with right:
    st.subheader("Daily P&L")
    daily = trades.groupby("date", as_index=False)["net_pnl"].sum() if not trades.empty else pd.DataFrame()
    if not daily.empty:
        st.plotly_chart(px.bar(daily, x="date", y="net_pnl"), use_container_width=True)

st.subheader("Reports")
tab1, tab2, tab3, tab4 = st.tabs(["Trades", "By Symbol", "By Side", "By Hour"])

with tab1:
    st.subheader("Trade Blotter")

    symbols = sorted(trades["symbol"].dropna().unique().tolist())
    sides = sorted(trades["side"].dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)

    selected_symbols = c1.multiselect(
        "Filter by symbol",
        options=symbols,
        default=symbols,
    )

    selected_sides = c2.multiselect(
        "Filter by side",
        options=sides,
        default=sides,
    )

    pnl_filter = c3.selectbox(
        "P&L filter",
        ["All trades", "Winners only", "Losers only", "Breakeven only"],
    )

    filtered = trades.copy()

    if selected_symbols:
        filtered = filtered[filtered["symbol"].isin(selected_symbols)]

    if selected_sides:
        filtered = filtered[filtered["side"].isin(selected_sides)]

    if pnl_filter == "Winners only":
        filtered = filtered[filtered["net_pnl"] > 0]
    elif pnl_filter == "Losers only":
        filtered = filtered[filtered["net_pnl"] < 0]
    elif pnl_filter == "Breakeven only":
        filtered = filtered[filtered["net_pnl"] == 0]

    st.caption(f"Showing {len(filtered):,} of {len(trades):,} trades")

    display_cols = [
        "date",
        "symbol",
        "side",
        "shares",
        "entry_time",
        "exit_time",
        "avg_entry",
        "avg_exit",
        "gross_pnl",
        "net_pnl",
        "hold_minutes",
    ]

    display_cols = [c for c in display_cols if c in filtered.columns]

    st.dataframe(
        filtered.sort_values("exit_time", ascending=False)[display_cols],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download filtered trades CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="filtered_trades.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download reconstructed trades CSV",
        trades.to_csv(index=False).encode("utf-8"),
        file_name="reconstructed_trades.csv",
        mime="text/csv",
    )

with tab2:
    st.subheader("Symbol Analysis")

    symbol_stats = (
        trades.groupby("symbol")
        .agg(
            trades=("symbol", "count"),
            net_pnl=("net_pnl", "sum"),
            gross_pnl=("gross_pnl", "sum"),
            avg_pnl=("net_pnl", "mean"),
            largest_win=("net_pnl", "max"),
            largest_loss=("net_pnl", "min"),
        )
        .reset_index()
    )

    wins = trades[trades["net_pnl"] > 0].groupby("symbol").size()
    losses = trades[trades["net_pnl"] < 0].groupby("symbol").size()

    symbol_stats["wins"] = symbol_stats["symbol"].map(wins).fillna(0).astype(int)
    symbol_stats["losses"] = symbol_stats["symbol"].map(losses).fillna(0).astype(int)
    symbol_stats["win_rate"] = symbol_stats["wins"] / symbol_stats["trades"]

    symbol_stats = symbol_stats.sort_values("net_pnl", ascending=False)

    st.dataframe(
        symbol_stats,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Top Winning Symbols")
    st.bar_chart(
        symbol_stats.head(10).set_index("symbol")["net_pnl"]
    )

    st.subheader("Top Losing Symbols")
    st.bar_chart(
        symbol_stats.tail(10).sort_values("net_pnl").set_index("symbol")["net_pnl"]
    )

    st.download_button(
        "Download symbol analysis CSV",
        symbol_stats.to_csv(index=False).encode("utf-8"),
        file_name="symbol_analysis.csv",
        mime="text/csv",
    )

with tab3:
    st.dataframe(group_report(trades, "side"), use_container_width=True, hide_index=True)

with tab4:
    hourly = group_report(trades, "entry_hour")
    st.dataframe(hourly, use_container_width=True, hide_index=True)
    if not hourly.empty:
        st.plotly_chart(px.bar(hourly, x="entry_hour", y="net_pnl"), use_container_width=True)

with st.expander("Raw cleaned executions"):
    st.dataframe(executions, use_container_width=True, hide_index=True)

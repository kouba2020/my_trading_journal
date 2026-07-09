from __future__ import annotations

import io
import pandas as pd
import streamlit as st
import plotly.express as px

from pathlib import Path
from datetime import datetime
import pandas as pd

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

ANNOTATIONS_PATH = Path("data/trade_annotations.csv")

def load_annotations():
    if ANNOTATIONS_PATH.exists():
        return pd.read_csv(ANNOTATIONS_PATH)

    return pd.DataFrame(
        columns=[
            "trade_index",
            "symbol",
            "tag",
            "grade",
            "emotion",
            "mistake",
            "notes",
            "updated_at",
        ]
    )

annotations = load_annotations()

journal_trades = trades.merge(
    annotations,
    left_index=True,
    right_on="trade_index",
    how="left",
)

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Trades",
        "By Symbol",
        "By Side",
        "By Hour",
        "Journal",
        "Setups",
    ]
)

with tab1:
    st.subheader("Trade Blotter")

    symbols = sorted(trades["symbol"].dropna().unique().tolist())
    sides = sorted(trades["side"].dropna().unique().tolist())

    c1, c2, c3, c4 = st.columns(4)

    selected_symbol = c1.selectbox(
        "Symbol",
        ["All Symbols"] + symbols,
        key="tab1_symbol_filter",
    )

    selected_side = c2.selectbox(
        "Side",
        ["All Sides"] + sides,
        key="tab1_side_filter",
    )

    pnl_filter = c3.selectbox(
        "P&L",
        ["All trades", "Winners only", "Losers only", "Breakeven only"],
        key="tab1_pnl_filter",
    )

    only_unjournaled = c4.checkbox(
        "Only unjournaled",
        key="tab1_only_unjournaled",
    )

    filtered = trades.copy()

    if selected_symbol != "All Symbols":
        filtered = filtered[filtered["symbol"] == selected_symbol]

    if selected_side != "All Sides":
        filtered = filtered[filtered["side"] == selected_side]

    if pnl_filter == "Winners only":
        filtered = filtered[filtered["net_pnl"] > 0]
    elif pnl_filter == "Losers only":
        filtered = filtered[filtered["net_pnl"] < 0]
    elif pnl_filter == "Breakeven only":
        filtered = filtered[filtered["net_pnl"] == 0]

    journaled_trade_ids = annotations["trade_index"].dropna().astype(int).tolist()

    if only_unjournaled:
        filtered = filtered[~filtered.index.isin(journaled_trade_ids)]

    total_trades = len(trades)
    journaled_count = len(set(journaled_trade_ids))
    progress = journaled_count / total_trades if total_trades > 0 else 0

    st.progress(progress)
    st.caption(
        f"Journal progress: {journaled_count:,} / {total_trades:,} trades completed "
        f"({progress:.0%})"
    )

    st.caption(f"Showing {len(filtered):,} of {len(trades):,} trades")

    if filtered.empty:
        st.warning("No trades match the selected filters.")
    else:
        trade_options = filtered.sort_values("exit_time", ascending=False).copy()

        trade_options["trade_label"] = (
            trade_options.index.astype(str)
            + " | "
            + trade_options["date"].astype(str)
            + " | "
            + trade_options["symbol"].astype(str)
            + " | "
            + trade_options["side"].astype(str)
            + " | P&L: "
            + trade_options["net_pnl"].round(2).astype(str)
        )

        selected_label = st.selectbox(
            "Select trade",
            trade_options["trade_label"].tolist(),
            key="tab1_trade_selector",
        )

        selected_index = int(selected_label.split(" | ")[0])
        trade = trades.loc[selected_index]

        st.divider()
        st.subheader("Trade Details")

        d1, d2, d3, d4 = st.columns(4)

        d1.metric("Symbol", trade["symbol"])
        d2.metric("Side", trade["side"])
        d3.metric("Shares", int(trade["shares"]))
        d4.metric("Net P&L", f"${trade['net_pnl']:,.2f}")

        d5, d6, d7, d8 = st.columns(4)

        d5.metric("Avg Entry", f"${trade['avg_entry']:,.4f}")
        d6.metric("Avg Exit", f"${trade['avg_exit']:,.4f}")
        d7.metric("Hold Minutes", f"{trade['hold_minutes']:,.1f}")
        d8.metric("R Multiple", f"{trade['r_multiple']:,.2f}")

        st.write("Entry Time:", trade["entry_time"])
        st.write("Exit Time:", trade["exit_time"])
        st.write("Executions:", trade["executions"])

        st.divider()
        st.subheader("Journal Entry")

        existing = annotations[annotations["trade_index"] == selected_index]

        if not existing.empty:
            existing = existing.iloc[-1]
        else:
            existing = None

        tag_options = [
            "",
            "Gap & Go",
            "ORB",
            "VWAP Reclaim",
            "Pullback",
            "Reversal",
            "News",
            "FOMO",
            "A+ Setup",
            "Bad Entry",
            "Bad Exit",
        ]

        grade_options = ["", "A+", "A", "B", "C", "D", "F"]

        emotion_options = [
            "",
            "Calm",
            "Confident",
            "Patient",
            "FOMO",
            "Fearful",
            "Greedy",
            "Revenge",
            "Frustrated",
        ]

        mistake_options = [
            "",
            "None",
            "Chased",
            "Held too long",
            "Exited too early",
            "Averaged down",
            "Ignored stop",
            "Oversized",
            "Overtraded",
        ]

        def option_index(options, value):
            if pd.isna(value):
                return 0
            return options.index(value) if value in options else 0

        tag = st.selectbox(
            "Setup / Tag",
            tag_options,
            index=option_index(tag_options, existing["tag"] if existing is not None else ""),
            key=f"tab1_tag_{selected_index}",
        )

        grade = st.selectbox(
            "Trade Grade",
            grade_options,
            index=option_index(grade_options, existing["grade"] if existing is not None else ""),
            key=f"tab1_grade_{selected_index}",
        )

        emotion = st.selectbox(
            "Emotion",
            emotion_options,
            index=option_index(emotion_options, existing["emotion"] if existing is not None else ""),
            key=f"tab1_emotion_{selected_index}",
        )

        mistake = st.selectbox(
            "Mistake",
            mistake_options,
            index=option_index(mistake_options, existing["mistake"] if existing is not None else ""),
            key=f"tab1_mistake_{selected_index}",
        )

        notes = st.text_area(
            "Trade Notes",
            value=existing["notes"] if existing is not None and not pd.isna(existing["notes"]) else "",
            placeholder="What happened? What did you do well? What should you improve?",
            key=f"tab1_notes_{selected_index}",
        )

        if st.button("Save Journal Entry", key=f"save_journal_{selected_index}"):
            new_entry = {
                "trade_index": selected_index,
                "symbol": trade["symbol"],
                "tag": tag,
                "grade": grade,
                "emotion": emotion,
                "mistake": mistake,
                "notes": notes,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            annotations = annotations[annotations["trade_index"] != selected_index]
            annotations = pd.concat(
                [annotations, pd.DataFrame([new_entry])],
                ignore_index=True,
            )

            ANNOTATIONS_PATH.parent.mkdir(exist_ok=True)
            annotations.to_csv(ANNOTATIONS_PATH, index=False)

            st.success("Journal entry saved.")

        st.divider()
        st.subheader("Filtered Trades")

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
    st.subheader("Performance by Side")

    side_stats = (
        trades.groupby("side")
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

    wins = trades[trades["net_pnl"] > 0].groupby("side").size()
    losses = trades[trades["net_pnl"] < 0].groupby("side").size()

    side_stats["wins"] = side_stats["side"].map(wins).fillna(0).astype(int)
    side_stats["losses"] = side_stats["side"].map(losses).fillna(0).astype(int)
    side_stats["win_rate"] = side_stats["wins"] / side_stats["trades"]

    side_stats = side_stats.sort_values("net_pnl", ascending=False)

    st.dataframe(
        side_stats,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Net P&L by Side")
    st.bar_chart(side_stats.set_index("side")["net_pnl"])

    st.download_button(
        "Download side analysis CSV",
        side_stats.to_csv(index=False).encode("utf-8"),
        file_name="side_analysis.csv",
        mime="text/csv",
    )

with tab4:
    st.subheader("Time of Day Analysis")

    hourly = (
        trades.groupby("entry_hour")
        .agg(
            trades=("symbol", "count"),
            net_pnl=("net_pnl", "sum"),
            avg_pnl=("net_pnl", "mean"),
        )
        .reset_index()
    )

    wins = trades[trades["net_pnl"] > 0].groupby("entry_hour").size()
    losses = trades[trades["net_pnl"] < 0].groupby("entry_hour").size()

    hourly["wins"] = hourly["entry_hour"].map(wins).fillna(0).astype(int)
    hourly["losses"] = hourly["entry_hour"].map(losses).fillna(0).astype(int)
    hourly["win_rate"] = hourly["wins"] / hourly["trades"]

    hourly = hourly.sort_values("entry_hour")

    st.dataframe(hourly, use_container_width=True, hide_index=True)

    st.subheader("Net P&L by Hour")
    st.bar_chart(hourly.set_index("entry_hour")["net_pnl"])

    st.subheader("Win Rate by Hour")
    st.bar_chart(hourly.set_index("entry_hour")["win_rate"])

    st.download_button(
        "Download hourly analysis CSV",
        hourly.to_csv(index=False).encode("utf-8"),
        file_name="hourly_analysis.csv",
        mime="text/csv",
    )
    
with tab5:
    st.write("Coming soon...")
    #st.subheader("Journal Entry")

    # j1, j2, j3 = st.columns(3)

    # journal_symbols = sorted(trades["symbol"].dropna().unique().tolist())
    # journal_sides = sorted(trades["side"].dropna().unique().tolist())

    # selected_journal_symbols = j1.multiselect(
        # "Symbol",
        # options=journal_symbols,
        # default=[],
        # key="journal_symbol_filter",
    # )

    # selected_journal_sides = j2.multiselect(
        # "Side",
        # options=journal_sides,
        # default=[],
        # key="journal_side_filter",
    # )

    # journal_pnl_filter = j3.selectbox(
        # "P&L",
        # ["All trades", "Winners only", "Losers only", "Breakeven only"],
        # key="journal_pnl_filter",
    # )

    # journal_filtered = trades.copy()

    # if selected_journal_symbols:
        # journal_filtered = journal_filtered[
            # journal_filtered["symbol"].isin(selected_journal_symbols)
        # ]

    # if selected_journal_sides:
        # journal_filtered = journal_filtered[
            # journal_filtered["side"].isin(selected_journal_sides)
        # ]

    # if journal_pnl_filter == "Winners only":
        # journal_filtered = journal_filtered[journal_filtered["net_pnl"] > 0]
    # elif journal_pnl_filter == "Losers only":
        # journal_filtered = journal_filtered[journal_filtered["net_pnl"] < 0]
    # elif journal_pnl_filter == "Breakeven only":
        # journal_filtered = journal_filtered[journal_filtered["net_pnl"] == 0]

    # st.caption(
        # f"Showing {len(journal_filtered):,} of {len(trades):,} trades"
    # )

    # if journal_filtered.empty:
        # st.warning("No trades match the selected journal filters.")
        # st.stop()
        # trade_options = journal_filtered.sort_values(
        # "exit_time",
        # ascending=False,
    # ).copy()

    # trade_options["trade_label"] = (
        # trade_options.index.astype(str)
        # + " | "
        # + trade_options["date"].astype(str)
        # + " | "
        # + trade_options["symbol"].astype(str)
        # + " | "
        # + trade_options["side"].astype(str)
        # + " | P&L: "
        # + trade_options["net_pnl"].round(2).astype(str)
    # )

    # selected_label = st.selectbox(
        # "Select trade to journal",
        # trade_options["trade_label"].tolist(),
        # key="journal_trade_selector",
    # )

    # selected_index = int(selected_label.split(" | ")[0])
    # trade = trades.loc[selected_index]    

    # existing = annotations[annotations["trade_index"] == selected_index]

    # if not existing.empty:
        # existing = existing.iloc[-1]
    # else:
        # existing = None

    # tag_options = [
        # "",
        # "Gap & Go",
        # "ORB",
        # "VWAP Reclaim",
        # "Pullback",
        # "Reversal",
        # "News",
        # "FOMO",
        # "A+ Setup",
        # "Bad Entry",
        # "Bad Exit",
    # ]

    # grade_options = ["", "A+", "A", "B", "C", "D", "F"]

    # emotion_options = [
        # "",
        # "Calm",
        # "Confident",
        # "Patient",
        # "FOMO",
        # "Fearful",
        # "Greedy",
        # "Revenge",
        # "Frustrated",
    # ]

    # mistake_options = [
        # "",
        # "None",
        # "Chased",
        # "Held too long",
        # "Exited too early",
        # "Averaged down",
        # "Ignored stop",
        # "Oversized",
        # "Overtraded",
    # ]

    # def option_index(options, value):
        # if pd.isna(value):
            # return 0
        # return options.index(value) if value in options else 0

    # tag = st.selectbox(
        # "Setup / Tag",
        # tag_options,
        # index=option_index(tag_options, existing["tag"] if existing is not None else ""),
        # key=f"tag_{selected_index}",
    # )

    # grade = st.selectbox(
        # "Trade Grade",
        # grade_options,
        # index=option_index(grade_options, existing["grade"] if existing is not None else ""),
        # key=f"grade_{selected_index}",
    # )

    # emotion = st.selectbox(
        # "Emotion",
        # emotion_options,
        # index=option_index(emotion_options, existing["emotion"] if existing is not None else ""),
        # key=f"emotion_{selected_index}",
    # )

    # mistake = st.selectbox(
        # "Mistake",
        # mistake_options,
        # index=option_index(mistake_options, existing["mistake"] if existing is not None else ""),
        # key=f"mistake_{selected_index}",
    # )

    # notes = st.text_area(
        # "Trade Notes",
        # value=existing["notes"] if existing is not None and not pd.isna(existing["notes"]) else "",
        # placeholder="What happened? What did you do well? What should you improve?",
        # key=f"notes_{selected_index}",
    # )

    # if st.button("Save Journal Entry"):
        # new_entry = {
            # "trade_index": selected_index,
            # "symbol": trade["symbol"],
            # "tag": tag,
            # "grade": grade,
            # "emotion": emotion,
            # "mistake": mistake,
            # "notes": notes,
            # "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # }

        # annotations = annotations[annotations["trade_index"] != selected_index]
        # annotations = pd.concat(
            # [annotations, pd.DataFrame([new_entry])],
            # ignore_index=True,
        # )

        # ANNOTATIONS_PATH.parent.mkdir(exist_ok=True)
        # annotations.to_csv(ANNOTATIONS_PATH, index=False)

        # st.success("Journal entry saved.")

with tab6:

    st.subheader("Setup Performance")
    setup_trades = journal_trades[
    journal_trades["tag"].notna()
    ]

    setup_trades = setup_trades[
        setup_trades["tag"] != ""
    ]
    
    if setup_trades.empty:
        st.info("No tagged trades yet.")
    else:
        setup_stats = (
            setup_trades.groupby("tag")
            .agg(
                trades=("tag", "count"),
                net_pnl=("net_pnl", "sum"),
                avg_pnl=("net_pnl", "mean"),
                largest_win=("net_pnl", "max"),
                largest_loss=("net_pnl", "min"),
            )
        .reset_index()
        )
    wins = (
        setup_trades[setup_trades["net_pnl"] > 0]
        .groupby("tag")
        .size()
    )

    losses = (
        setup_trades[setup_trades["net_pnl"] < 0]
        .groupby("tag")
        .size()
    )

    setup_stats["wins"] = (
        setup_stats["tag"]
        .map(wins)
        .fillna(0)
        .astype(int)
    )

    setup_stats["losses"] = (
        setup_stats["tag"]
        .map(losses)
        .fillna(0)
        .astype(int)
    )

    setup_stats["win_rate"] = (
        100
        * setup_stats["wins"]
        / setup_stats["trades"]
    )

    setup_stats = setup_stats.sort_values(
        "net_pnl",
        ascending=False
    )

    st.dataframe(
        setup_stats,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Net P&L by Setup")

    st.bar_chart(
        setup_stats.set_index("tag")["net_pnl"]
    )

    st.subheader("Win Rate by Setup")

    st.bar_chart(
        setup_stats.set_index("tag")["win_rate"]
    )

    st.download_button(
        "Download Setup Report",
        setup_stats.to_csv(index=False).encode("utf-8"),
        file_name="setup_report.csv",
        mime="text/csv",
    )
        
with st.expander("Raw cleaned executions"):
    st.dataframe(executions, use_container_width=True, hide_index=True)
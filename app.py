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

annotation_cols = [
    "trade_index",
    "tag",
    "grade",
    "emotion",
    "mistake",
    "notes",
    "updated_at",
]

journal_trades = trades.merge(
    annotations[annotation_cols],
    left_index=True,
    right_on="trade_index",
    how="left",
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs(
    [
        "Trades",
        "By Symbol",
        "By Side",
        "By Hour",
        "Journal",
        "Setups",
        "Emotions",
        "Mistakes",
        "Grades",
        "Daily Review",
        "Insights",
        "Expectancy & Risk",
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


        
        table_data = filtered.copy()

        journaled_ids = (
            annotations["trade_index"]
            .dropna()
            .astype(int)
            .tolist()
        )

        table_data["journaled"] = table_data.index.isin(journaled_ids)

        table_data["journaled"] = table_data["journaled"].map(
            {
                True: "✅",
                False: "❌",
            }
        )
        
        display_cols = [
            "journaled",
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

        display_cols = [c for c in display_cols if c in table_data.columns]
        
        st.dataframe(
            table_data.sort_values("exit_time", ascending=False)[display_cols],
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
      
with tab7:

    st.subheader("Emotion Analysis")
    emotion_trades = journal_trades[
    journal_trades["emotion"].notna()
    ]

    emotion_trades = emotion_trades[
        emotion_trades["emotion"] != ""
    ]
    if emotion_trades.empty:
        st.info("No emotion data available yet.")
    else:
        emotion_stats = (
            emotion_trades.groupby("emotion")
            .agg(
                trades=("emotion", "count"),
                net_pnl=("net_pnl", "sum"),
                avg_pnl=("net_pnl", "mean"),
                largest_win=("net_pnl", "max"),
                largest_loss=("net_pnl", "min"),
            )
            .reset_index()
        )
    wins = (
        emotion_trades[emotion_trades["net_pnl"] > 0]
        .groupby("emotion")
        .size()
    )

    losses = (
        emotion_trades[emotion_trades["net_pnl"] < 0]
        .groupby("emotion")
        .size()
    )

    emotion_stats["wins"] = (
        emotion_stats["emotion"]
        .map(wins)
        .fillna(0)
        .astype(int)
    )

    emotion_stats["losses"] = (
        emotion_stats["emotion"]
        .map(losses)
        .fillna(0)
        .astype(int)
    )

    emotion_stats["win_rate"] = (
        100
        * emotion_stats["wins"]
        / emotion_stats["trades"]
    )
    
    emotion_stats = emotion_stats.sort_values(
        "net_pnl",
        ascending=False
    )
    
    st.dataframe(
        emotion_stats,
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Net P&L by Emotion")

    st.bar_chart(
        emotion_stats.set_index("emotion")["net_pnl"]
    )
    
    st.subheader("Win Rate by Emotion")

    st.bar_chart(
        emotion_stats.set_index("emotion")["win_rate"]
    )

    st.download_button(
        "Download Emotion Report",
        emotion_stats.to_csv(index=False).encode("utf-8"),
        file_name="emotion_report.csv",
        mime="text/csv",
    )

with tab8:

    st.subheader("Mistake Analysis")

    mistake_trades = journal_trades[
        journal_trades["mistake"].notna()
    ]

    mistake_trades = mistake_trades[
        mistake_trades["mistake"] != ""
    ]

    if mistake_trades.empty:
        st.info("No mistake data available yet.")

    else:
        mistake_stats = (
            mistake_trades.groupby("mistake")
            .agg(
                trades=("mistake", "count"),
                net_pnl=("net_pnl", "sum"),
                avg_pnl=("net_pnl", "mean"),
                largest_win=("net_pnl", "max"),
                largest_loss=("net_pnl", "min"),
            )
            .reset_index()
        )

        wins = (
            mistake_trades[mistake_trades["net_pnl"] > 0]
            .groupby("mistake")
            .size()
        )

        losses = (
            mistake_trades[mistake_trades["net_pnl"] < 0]
            .groupby("mistake")
            .size()
        )

        mistake_stats["wins"] = (
            mistake_stats["mistake"]
            .map(wins)
            .fillna(0)
            .astype(int)
        )

        mistake_stats["losses"] = (
            mistake_stats["mistake"]
            .map(losses)
            .fillna(0)
            .astype(int)
        )

        mistake_stats["win_rate"] = (
            100
            * mistake_stats["wins"]
            / mistake_stats["trades"]
        )

        mistake_stats = mistake_stats.sort_values(
            "net_pnl",
            ascending=False,
        )

        st.dataframe(
            mistake_stats,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Net P&L by Mistake")

        st.bar_chart(
            mistake_stats.set_index("mistake")["net_pnl"]
        )

        st.subheader("Win Rate by Mistake")

        st.bar_chart(
            mistake_stats.set_index("mistake")["win_rate"]
        )

        st.download_button(
            "Download Mistake Report",
            mistake_stats.to_csv(index=False).encode("utf-8"),
            file_name="mistake_report.csv",
            mime="text/csv",
        )

with tab9:

    st.subheader("Grade Analysis")

    grade_trades = journal_trades[
        journal_trades["grade"].notna()
    ].copy()

    grade_trades = grade_trades[
        grade_trades["grade"].astype(str).str.strip() != ""
    ]

    if grade_trades.empty:
        st.info("No grade data available yet.")

    else:
        grade_stats = (
            grade_trades.groupby("grade")
            .agg(
                trades=("grade", "count"),
                net_pnl=("net_pnl", "sum"),
                avg_pnl=("net_pnl", "mean"),
                largest_win=("net_pnl", "max"),
                largest_loss=("net_pnl", "min"),
                avg_r_multiple=("r_multiple", "mean"),
            )
            .reset_index()
        )

        wins = (
            grade_trades[grade_trades["net_pnl"] > 0]
            .groupby("grade")
            .size()
        )

        losses = (
            grade_trades[grade_trades["net_pnl"] < 0]
            .groupby("grade")
            .size()
        )

        breakeven = (
            grade_trades[grade_trades["net_pnl"] == 0]
            .groupby("grade")
            .size()
        )

        grade_stats["wins"] = (
            grade_stats["grade"]
            .map(wins)
            .fillna(0)
            .astype(int)
        )

        grade_stats["losses"] = (
            grade_stats["grade"]
            .map(losses)
            .fillna(0)
            .astype(int)
        )

        grade_stats["breakeven"] = (
            grade_stats["grade"]
            .map(breakeven)
            .fillna(0)
            .astype(int)
        )

        grade_stats["win_rate"] = (
            100
            * grade_stats["wins"]
            / grade_stats["trades"]
        )

        grade_order = ["A+", "A", "B", "C", "D", "F"]

        grade_stats["grade"] = pd.Categorical(
            grade_stats["grade"],
            categories=grade_order,
            ordered=True,
        )

        grade_stats = grade_stats.sort_values("grade")

        st.dataframe(
            grade_stats,
            use_container_width=True,
            hide_index=True,
            column_config={
                "net_pnl": st.column_config.NumberColumn(
                    "Net P&L",
                    format="$%.2f",
                ),
                "avg_pnl": st.column_config.NumberColumn(
                    "Avg P&L",
                    format="$%.2f",
                ),
                "largest_win": st.column_config.NumberColumn(
                    "Largest Win",
                    format="$%.2f",
                ),
                "largest_loss": st.column_config.NumberColumn(
                    "Largest Loss",
                    format="$%.2f",
                ),
                "avg_r_multiple": st.column_config.NumberColumn(
                    "Avg R",
                    format="%.2f",
                ),
                "win_rate": st.column_config.NumberColumn(
                    "Win Rate",
                    format="%.1f%%",
                ),
            },
        )

        st.subheader("Net P&L by Grade")

        st.bar_chart(
            grade_stats.set_index("grade")["net_pnl"]
        )

        st.subheader("Average P&L by Grade")

        st.bar_chart(
            grade_stats.set_index("grade")["avg_pnl"]
        )

        st.subheader("Win Rate by Grade")

        st.bar_chart(
            grade_stats.set_index("grade")["win_rate"]
        )

        st.download_button(
            "Download Grade Report",
            grade_stats.to_csv(index=False).encode("utf-8"),
            file_name="grade_report.csv",
            mime="text/csv",
        )

with tab10:

    st.subheader("Daily Review")
    available_dates = sorted(
    trades["date"].dropna().unique(),
    reverse=True
    )

    selected_day = st.selectbox(
        "Select Trading Day",
        available_dates
    )

    day_trades = journal_trades[
    journal_trades["date"] == selected_day
    ]
    
    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Trades",
        len(day_trades)
    )

    col2.metric(
        "Net P&L",
        f"${day_trades['net_pnl'].sum():,.2f}"
    )

    col3.metric(
        "Avg Trade",
        f"${day_trades['net_pnl'].mean():,.2f}"
    )

    wins = (day_trades["net_pnl"] > 0).sum()

    win_rate = (
        100 * wins / len(day_trades)
        if len(day_trades) > 0
        else 0
    )

    col4.metric(
        "Win Rate",
        f"{win_rate:.1f}%"
    )
    
    st.subheader("Best & Worst Trade")

    valid_day_trades = day_trades.dropna(
    subset=["net_pnl"]
    ).copy()

    valid_day_trades["net_pnl"] = pd.to_numeric(
        valid_day_trades["net_pnl"],
        errors="coerce",
    )

    valid_day_trades = valid_day_trades.dropna(
        subset=["net_pnl"]
    )

    if valid_day_trades.empty:
        st.info("No trades available for this day.")
        
    else:
        best_trade = valid_day_trades.iloc[
        valid_day_trades["net_pnl"].argmax()
        ]

        worst_trade = valid_day_trades.iloc[
            valid_day_trades["net_pnl"].argmin()
        ]

        col1, col2 = st.columns(2)

        with col1:
            st.success(
                f"""
        Best Trade

        {best_trade['symbol']}

        P&L: ${best_trade['net_pnl']:.2f}
        """
            )

    with col2:
        st.error(
            f"""
        Worst Trade

        {worst_trade['symbol']}

        P&L: ${worst_trade['net_pnl']:.2f}
        """
        )

    st.subheader("Behavior Summary")
    
    if day_trades["tag"].notna().any():

        top_setup = (
            day_trades["tag"]
            .value_counts()
            .idxmax()
        )

        st.write(
            f"**Most Traded Setup:** {top_setup}"
        )
    
    if day_trades["emotion"].notna().any():

        top_emotion = (
            day_trades["emotion"]
            .value_counts()
            .idxmax()
        )

        st.write(
            f"**Most Common Emotion:** {top_emotion}"
        )
    
    if day_trades["mistake"].notna().any():

        top_mistake = (
            day_trades["mistake"]
            .value_counts()
            .idxmax()
        )

        st.write(
            f"**Most Common Mistake:** {top_mistake}"
        )
    
    st.subheader("Trades")

    st.dataframe(
        day_trades[
            [
                "symbol",
                "side",
                "shares",
                "net_pnl",
                "tag",
                "emotion",
                "mistake",
                "grade",
            ]
        ],
        use_container_width=True,
    )

with tab11:

    st.subheader("Trading Insights")
    
    journaled_count = len(
        annotations["trade_index"].dropna().unique()
    )

    coverage = (
        100 * journaled_count / len(trades)
    )

    if coverage < 25:
        st.warning(
            f"""
            Only {coverage:.1f}% of trades have been journaled.

            Insights may not yet be statistically reliable.
            Consider journaling at least 25-30% of trades.
            """
        )


    insight_trades = journal_trades.copy()

    insight_trades["net_pnl"] = pd.to_numeric(
        insight_trades["net_pnl"],
        errors="coerce",
    )

    insight_trades = insight_trades.dropna(
        subset=["net_pnl"]
    )

    if insight_trades.empty:
        st.info("No trading data available.")

    else:
        # ---------------------------------
        # Best symbol
        # ---------------------------------
        symbol_results = (
            insight_trades.groupby("symbol")["net_pnl"]
            .agg(["sum", "count"])
        )

        best_symbol = symbol_results["sum"].idxmax()
        best_symbol_pnl = symbol_results.loc[best_symbol, "sum"]

        # ---------------------------------
        # Best trading hour
        # ---------------------------------
        hour_results = (
            insight_trades.groupby("entry_hour")["net_pnl"]
            .agg(["sum", "count"])
        )

        best_hour = hour_results["sum"].idxmax()
        best_hour_pnl = hour_results.loc[best_hour, "sum"]

        # ---------------------------------
        # Best setup
        # ---------------------------------
        setup_trades = insight_trades[
            insight_trades["tag"].notna()
            & (insight_trades["tag"].astype(str).str.strip() != "")
        ]

        if not setup_trades.empty:
            setup_results = (
                setup_trades.groupby("tag")["net_pnl"]
                .agg(["sum", "count"])
            )

            best_setup = setup_results["sum"].idxmax()
            best_setup_pnl = setup_results.loc[best_setup, "sum"]

        else:
            best_setup = "No data"
            best_setup_pnl = 0

        # ---------------------------------
        # Best emotion
        # ---------------------------------
        emotion_trades = insight_trades[
            insight_trades["emotion"].notna()
            & (
                insight_trades["emotion"]
                .astype(str)
                .str.strip()
                != ""
            )
        ]

        if not emotion_trades.empty:
            emotion_results = (
                emotion_trades.groupby("emotion")["net_pnl"]
                .agg(["sum", "count"])
            )

            best_emotion = emotion_results["sum"].idxmax()
            best_emotion_pnl = emotion_results.loc[
                best_emotion,
                "sum",
            ]

            worst_emotion = emotion_results["sum"].idxmin()
            worst_emotion_pnl = emotion_results.loc[
                worst_emotion,
                "sum",
            ]

        else:
            best_emotion = "No data"
            best_emotion_pnl = 0
            worst_emotion = "No data"
            worst_emotion_pnl = 0

        # ---------------------------------
        # Most expensive mistake
        # ---------------------------------
        mistake_trades = insight_trades[
            insight_trades["mistake"].notna()
            & (
                insight_trades["mistake"]
                .astype(str)
                .str.strip()
                != ""
            )
            & (
                insight_trades["mistake"]
                .astype(str)
                .str.lower()
                != "none"
            )
        ]

        if not mistake_trades.empty:
            mistake_results = (
                mistake_trades.groupby("mistake")["net_pnl"]
                .agg(["sum", "count"])
            )

            worst_mistake = mistake_results["sum"].idxmin()
            worst_mistake_pnl = mistake_results.loc[
                worst_mistake,
                "sum",
            ]

        else:
            worst_mistake = "No data"
            worst_mistake_pnl = 0
    
        row1_col1, row1_col2, row1_col3 = st.columns(3)

        row1_col1.metric(
            "Best Symbol",
            str(best_symbol),
            f"${best_symbol_pnl:,.2f}",
        )

        row1_col2.metric(
            "Best Trading Hour",
            f"{int(best_hour):02d}:00",
            f"${best_hour_pnl:,.2f}",
        )

        row1_col3.metric(
            "Best Setup",
            str(best_setup),
            f"${best_setup_pnl:,.2f}",
        )

        row2_col1, row2_col2, row2_col3 = st.columns(3)

        row2_col1.metric(
            "Best Emotion",
            str(best_emotion),
            f"${best_emotion_pnl:,.2f}",
        )

        row2_col2.metric(
            "Worst Emotion",
            str(worst_emotion),
            f"${worst_emotion_pnl:,.2f}",
        )

        row2_col3.metric(
            "Most Expensive Mistake",
            str(worst_mistake),
            f"${worst_mistake_pnl:,.2f}",
        )
        
        st.subheader("Current Streak")

        streak_trades = insight_trades.sort_values(
            "exit_time"
        ).copy()

        streak_trades = streak_trades[
            streak_trades["net_pnl"] != 0
        ]

        current_streak = 0
        streak_type = "No streak"

        if not streak_trades.empty:
            last_result_is_win = (
                streak_trades.iloc[-1]["net_pnl"] > 0
            )

            streak_type = (
                "Winning streak"
                if last_result_is_win
                else "Losing streak"
            )

            for pnl in reversed(
                streak_trades["net_pnl"].tolist()
            ):
                is_win = pnl > 0

                if is_win == last_result_is_win:
                    current_streak += 1
                else:
                    break

        st.metric(
            streak_type,
            current_streak,
        )
        
        st.subheader("Summary")

        st.write(
            f"""
            Your most profitable symbol is **{best_symbol}**, generating
            **${best_symbol_pnl:,.2f}**.

            Your strongest trading hour is **{int(best_hour):02d}:00**, with
            **${best_hour_pnl:,.2f}** in net P&L.

            Your best-performing setup is **{best_setup}**, while your most
            expensive mistake is **{worst_mistake}**.

            Your best-performing emotional state is **{best_emotion}**.
            """
        )

with tab12:

    st.subheader("Expectancy & Risk Metrics")

    risk_trades = trades.copy()

    risk_trades["net_pnl"] = pd.to_numeric(
        risk_trades["net_pnl"],
        errors="coerce",
    )

    risk_trades = risk_trades.dropna(
        subset=["net_pnl"]
    )

    if risk_trades.empty:
        st.info("No valid trade data available.")

    else:
        total_trades = len(risk_trades)

        winning_trades = risk_trades[
            risk_trades["net_pnl"] > 0
        ]

        losing_trades = risk_trades[
            risk_trades["net_pnl"] < 0
        ]

        breakeven_trades = risk_trades[
            risk_trades["net_pnl"] == 0
        ]

        wins = len(winning_trades)
        losses = len(losing_trades)
        breakeven = len(breakeven_trades)

        win_rate = (
            100 * wins / total_trades
            if total_trades > 0
            else 0
        )

        loss_rate = (
            100 * losses / total_trades
            if total_trades > 0
            else 0
        )

        avg_win = (
            winning_trades["net_pnl"].mean()
            if not winning_trades.empty
            else 0
        )

        avg_loss = (
            losing_trades["net_pnl"].mean()
            if not losing_trades.empty
            else 0
        )

        gross_profit = winning_trades["net_pnl"].sum()

        gross_loss = abs(
            losing_trades["net_pnl"].sum()
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else float("inf")
        )

        payoff_ratio = (
            avg_win / abs(avg_loss)
            if avg_loss != 0
            else float("inf")
        )

        expectancy = (
            (win_rate / 100) * avg_win
            + (loss_rate / 100) * avg_loss
        )

        total_net_pnl = risk_trades["net_pnl"].sum()

        avg_trade = risk_trades["net_pnl"].mean()
        
        equity_trades = risk_trades.sort_values(
            "exit_time"
        ).copy()

        equity_trades["cumulative_pnl"] = (
            equity_trades["net_pnl"].cumsum()
        )

        equity_trades["running_peak"] = (
            equity_trades["cumulative_pnl"].cummax()
        )

        equity_trades["drawdown"] = (
            equity_trades["cumulative_pnl"]
            - equity_trades["running_peak"]
        )

        max_drawdown = equity_trades["drawdown"].min()

        max_drawdown = abs(max_drawdown)
        
    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)

    row1_col1.metric(
        "Total Trades",
        total_trades,
    )

    row1_col2.metric(
        "Net P&L",
        f"${total_net_pnl:,.2f}",
    )

    row1_col3.metric(
        "Win Rate",
        f"{win_rate:.1f}%",
    )

    row1_col4.metric(
        "Average Trade",
        f"${avg_trade:,.2f}",
    )

    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)

    row2_col1.metric(
        "Average Win",
        f"${avg_win:,.2f}",
    )

    row2_col2.metric(
        "Average Loss",
        f"${avg_loss:,.2f}",
    )

    row2_col3.metric(
        "Payoff Ratio",
        (
            f"{payoff_ratio:.2f}"
            if payoff_ratio != float("inf")
            else "∞"
        ),
    )

    row2_col4.metric(
        "Profit Factor",
        (
            f"{profit_factor:.2f}"
            if profit_factor != float("inf")
            else "∞"
        ),
    )

    row3_col1, row3_col2, row3_col3, row3_col4 = st.columns(4)

    row3_col1.metric(
        "Expectancy / Trade",
        f"${expectancy:,.2f}",
    )

    row3_col2.metric(
        "Max Drawdown",
        f"${max_drawdown:,.2f}",
    )

    row3_col3.metric(
        "Winning Trades",
        wins,
    )

    row3_col4.metric(
        "Losing Trades",
        losses,
    )
    
    st.subheader("Interpretation")

    if expectancy > 0:
        st.success(
            f"Positive expectancy: on average, each trade earns "
            f"${expectancy:,.2f}."
        )
    elif expectancy < 0:
        st.error(
            f"Negative expectancy: on average, each trade loses "
            f"${abs(expectancy):,.2f}."
        )
    else:
        st.info("Expectancy is currently at breakeven.")

    if profit_factor > 1.5:
        st.success(
            "Profit factor is strong. Gross profits meaningfully "
            "exceed gross losses."
        )
    elif profit_factor >= 1:
        st.warning(
            "Profit factor is positive but still modest."
        )
    else:
        st.error(
            "Profit factor is below 1. Gross losses exceed gross profits."
        )

    if payoff_ratio >= 1:
        st.write(
            "Your average winner is at least as large as your average loser."
        )
    else:
        st.write(
            "Your average winner is smaller than your average loser, "
            "so a higher win rate may be required."
        )
   
    st.subheader("Cumulative Net P&L")

    st.line_chart(
        equity_trades.set_index("exit_time")[
            "cumulative_pnl"
        ]
    )

    st.subheader("Drawdown")

    st.line_chart(
        equity_trades.set_index("exit_time")[
            "drawdown"
        ]
    )
    
    metric_summary = pd.DataFrame(
        {
            "Metric": [
                "Total Trades",
                "Winning Trades",
                "Losing Trades",
                "Breakeven Trades",
                "Win Rate",
                "Loss Rate",
                "Average Win",
                "Average Loss",
                "Payoff Ratio",
                "Gross Profit",
                "Gross Loss",
                "Profit Factor",
                "Expectancy per Trade",
                "Net P&L",
                "Maximum Drawdown",
            ],
            "Value": [
                total_trades,
                wins,
                losses,
                breakeven,
                f"{win_rate:.1f}%",
                f"{loss_rate:.1f}%",
                f"${avg_win:,.2f}",
                f"${avg_loss:,.2f}",
                (
                    f"{payoff_ratio:.2f}"
                    if payoff_ratio != float("inf")
                    else "∞"
                ),
                f"${gross_profit:,.2f}",
                f"${gross_loss:,.2f}",
                (
                    f"{profit_factor:.2f}"
                    if profit_factor != float("inf")
                    else "∞"
                ),
                f"${expectancy:,.2f}",
                f"${total_net_pnl:,.2f}",
                f"${max_drawdown:,.2f}",
            ],
        }
    )

    st.dataframe(
        metric_summary,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Risk Metrics",
        metric_summary.to_csv(index=False).encode("utf-8"),
        file_name="expectancy_risk_metrics.csv",
        mime="text/csv",
    )
  
with st.expander("Raw cleaned executions"):
    st.dataframe(executions, use_container_width=True, hide_index=True)
    
#st.write(day_trades.columns.tolist())
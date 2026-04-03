"""Signal Ledger Dashboard.

Displays the tamper-evident JSON trade record: open positions, closed positions,
cumulative stats, and per-factor signal decay curves.

The ledger is stored in data/ledger.json — committed to GitHub so the commit
history provides a timestamped audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from src.analysis.ledger import add_signal, get_all_signals, get_closed_positions, get_open_positions
from src.analysis.signal_decay import get_signal_decay_table
from src.ui.theme import inject_css, page_header

st.set_page_config(
    page_title="Signal Ledger — jaja-money",
    page_icon="📒",
    layout="wide",
)
inject_css()
page_header(
    "Signal Ledger",
    subtitle="Tamper-evident track record — committed signals, auditable outcomes",
    icon="📒",
)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def _load():
    return (
        get_open_positions(),
        get_closed_positions(),
        get_all_signals(),
    )


open_positions, closed_positions, all_signals = _load()

total = len(all_signals)
n_open = len(open_positions)
n_closed = len(closed_positions)

# ---------------------------------------------------------------------------
# Stats header
# ---------------------------------------------------------------------------

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Signals", total)
col2.metric("Open", n_open)
col3.metric("Closed", n_closed)

if closed_positions:
    wins = [p for p in closed_positions if (p.get("pnl_pct") or 0) > 0]
    hit_rate = len(wins) / n_closed * 100
    avg_pnl = sum(p.get("pnl_pct") or 0 for p in closed_positions) / n_closed

    # vs SPY alpha
    pnl_values = [p.get("pnl_pct") for p in closed_positions if p.get("pnl_pct") is not None]
    spy_values = [p.get("spy_pnl_pct") for p in closed_positions if p.get("spy_pnl_pct") is not None]
    if pnl_values and spy_values and len(pnl_values) == len(spy_values):
        avg_alpha = sum(p - s for p, s in zip(pnl_values, spy_values)) / len(pnl_values)
    else:
        avg_alpha = None

    col4.metric("Hit Rate", f"{hit_rate:.1f}%")
    col5.metric("Avg P&L %", f"{avg_pnl:+.2f}%", delta=f"{avg_alpha:+.2f}% vs SPY" if avg_alpha is not None else None)
else:
    col4.metric("Hit Rate", "—")
    col5.metric("Avg P&L %", "—")

st.divider()

# ---------------------------------------------------------------------------
# Open Positions
# ---------------------------------------------------------------------------

st.subheader("Open Positions")

if not open_positions:
    st.info("No open positions. Run the daily cron or log a signal manually below.")
else:
    CORE_FACTORS = [
        "Valuation (P/E)", "Trend (SMA)", "Momentum (RSI)", "MACD Signal",
        "News Sentiment", "Earnings Quality", "Analyst Consensus", "52-Wk Strength",
    ]

    for pos in open_positions:
        with st.container():
            days_held = 0
            try:
                fired = datetime.fromisoformat(pos["fired_at"].replace("Z", "+00:00"))
                days_held = (datetime.now(timezone.utc) - fired).days
            except Exception:
                pass

            c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 3])
            c1.markdown(f"**{pos['ticker']}**")
            score = pos.get("composite_score", 0)
            score_color = "#1a7f37" if score >= 70 else "#2da44e" if score >= 55 else "#888888"
            c2.markdown(
                f"<span style='color:{score_color};font-weight:bold'>{score:.0f}</span>",
                unsafe_allow_html=True,
            )
            c3.caption(f"Entry: ${pos.get('price_at_signal', 0):.2f}")
            c4.caption(f"{days_held}d held")

            # Factor mini-bars (8 core factors)
            fs = pos.get("factor_scores", {})
            mini_bar_html = "<div style='display:flex;gap:2px;align-items:flex-end;height:24px'>"
            for fname in CORE_FACTORS:
                score_val = fs.get(fname, 50)
                height = max(4, int(float(score_val) / 100 * 24))
                bar_color = "#2da44e" if float(score_val) > 50 else "#484F58"
                mini_bar_html += (
                    f"<div title='{fname}: {score_val:.0f}' "
                    f"style='width:6px;height:{height}px;"
                    f"background:{bar_color};border-radius:1px'></div>"
                )
            mini_bar_html += "</div>"
            c5.markdown(mini_bar_html, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Closed Positions
# ---------------------------------------------------------------------------

st.subheader("Closed Positions")

if not closed_positions:
    st.caption("No closed positions yet.")
else:
    import pandas as pd

    rows = []
    for pos in sorted(closed_positions, key=lambda p: p.get("exit_at") or "", reverse=True):
        pnl = pos.get("pnl_pct")
        spy_pnl = pos.get("spy_pnl_pct")
        alpha = ((pnl - spy_pnl) if pnl is not None and spy_pnl is not None else None)
        rows.append({
            "Ticker": pos["ticker"],
            "Entry Date": pos["fired_at"][:10],
            "Exit Date": (pos.get("exit_at") or "")[:10],
            "Score": f"{pos.get('composite_score', 0):.0f}",
            "Entry $": f"${pos.get('price_at_signal', 0):.2f}",
            "Exit $": f"${pos.get('exit_price', 0):.2f}" if pos.get("exit_price") else "—",
            "P&L %": f"{pnl:+.2f}%" if pnl is not None else "—",
            "vs SPY": f"{alpha:+.2f}%" if alpha is not None else "—",
            "Result": "WIN" if (pnl or 0) > 0 else "LOSS",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Signal Decay
# ---------------------------------------------------------------------------

st.subheader("Signal Decay Curves")
st.caption(
    "Win rate (exit price > entry price) by leading factor at T+5/T+10/T+30 calendar days. "
    "Shown once a factor has ≥ 5 closed positions."
)

decay_df = get_signal_decay_table(min_n=5)
sufficient = decay_df[decay_df["sufficient"]]
insufficient = decay_df[~decay_df["sufficient"]]

if sufficient.empty:
    st.info(
        "Waiting for data. Need ≥ 5 closed positions per factor group. "
        "Each factor group accumulates as signals close over 30 days."
    )
    total_closed = n_closed
    st.progress(min(total_closed / 5, 1.0), text=f"{total_closed} / 5 minimum closed positions")
else:
    import plotly.graph_objects as go

    # Sort by win_t30 descending
    plot_df = sufficient.sort_values("win_t30", ascending=False)

    tab_win, tab_pnl = st.tabs(["Win Rate (with 95% CI)", "Avg P&L %"])

    with tab_win:
        fig = go.Figure()
        for _, row in plot_df.iterrows():
            factor = row["factor"]
            xs = ["T+5", "T+10", "T+30"]
            ys = [(row[f"win_{h}"] or 0) * 100 for h in ("t5", "t10", "t30")]
            # Wilson CI error bars (already 0-1 scale, convert to %)
            err_lo = [
                max(0.0, (row[f"win_{h}"] or 0) - (row[f"ci_lo_{h}"] or 0)) * 100
                for h in ("t5", "t10", "t30")
            ]
            err_hi = [
                max(0.0, (row[f"ci_hi_{h}"] or 0) - (row[f"win_{h}"] or 0)) * 100
                for h in ("t5", "t10", "t30")
            ]
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines+markers",
                    name=f"{factor} (n={int(row['n'])})",
                    error_y=dict(
                        type="data",
                        symmetric=False,
                        array=err_hi,
                        arrayminus=err_lo,
                        thickness=1.5,
                        width=4,
                    ),
                )
            )

        fig.add_hline(y=50, line_dash="dash", line_color="#484F58", annotation_text="50% (coin flip)")
        fig.update_layout(
            height=400,
            margin=dict(l=0, r=0, t=20, b=20),
            xaxis_title="Horizon",
            yaxis_title="Win Rate %",
            yaxis=dict(range=[0, 100]),
            plot_bgcolor="#0D1117",
            paper_bgcolor="#0D1117",
            font=dict(color="#E6EDF3"),
            legend=dict(bgcolor="#161B22", bordercolor="#30363D"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Error bars = 95% Wilson score confidence intervals.")

    with tab_pnl:
        fig2 = go.Figure()
        for _, row in plot_df.iterrows():
            factor = row["factor"]
            ys2 = [row.get(f"avg_pnl_{h}") or 0 for h in ("t5", "t10", "t30")]
            fig2.add_trace(
                go.Bar(
                    x=["T+5", "T+10", "T+30"],
                    y=ys2,
                    name=f"{factor} (n={int(row['n'])})",
                )
            )

        fig2.add_hline(y=0, line_dash="solid", line_color="#484F58")
        fig2.update_layout(
            height=400,
            barmode="group",
            margin=dict(l=0, r=0, t=20, b=20),
            xaxis_title="Horizon",
            yaxis_title="Avg P&L %",
            plot_bgcolor="#0D1117",
            paper_bgcolor="#0D1117",
            font=dict(color="#E6EDF3"),
            legend=dict(bgcolor="#161B22", bordercolor="#30363D"),
        )
        st.plotly_chart(fig2, use_container_width=True)

# Insufficient factors summary
if not insufficient.empty:
    total_needed = insufficient["n"].apply(lambda n: max(0, 5 - n)).sum()
    with st.expander(f"{len(insufficient)} factor(s) need more closed positions ({total_needed} more closes total)"):
        for _, row in insufficient.iterrows():
            needed = max(0, 5 - int(row["n"]))
            st.caption(f"• {row['factor']} — {int(row['n'])} / 5 closes ({needed} more needed)")

st.divider()

# ---------------------------------------------------------------------------
# Claude Research Narrative (gated on 20+ closed positions)
# ---------------------------------------------------------------------------

st.subheader("Research Narrative")

_NARRATIVE_MIN = 20

if n_closed < _NARRATIVE_MIN:
    st.info(
        f"Collecting data... ({n_closed}/{_NARRATIVE_MIN} closed positions needed). "
        "Once you have 20+ closed trades, Claude will synthesize your factor track record "
        "— hit rates, which factors had real edge, regime breakdown, and baseline comparison."
    )
    st.progress(min(n_closed / _NARRATIVE_MIN, 1.0), text=f"{n_closed} / {_NARRATIVE_MIN} closed positions")
else:
    if st.button("Generate Research Narrative", key="ledger_narrative_btn"):
        from src.analysis.analyzer import stream_ledger_narrative

        with st.spinner("Synthesizing track record..."):
            narrative_text = ""
            placeholder = st.empty()
            for chunk in stream_ledger_narrative(use_cache=True):
                narrative_text += chunk
                placeholder.markdown(narrative_text)

st.divider()

# ---------------------------------------------------------------------------
# Manual Signal Entry
# ---------------------------------------------------------------------------

st.subheader("Log Signal Manually")

with st.expander("Log a manual signal"):
    with st.form("log_signal_form"):
        ticker_in = st.text_input("Ticker", "").upper().strip()
        score_in = st.number_input("Composite Score", 0, 100, 75)
        price_in = st.number_input("Entry Price", 0.0, value=0.0, step=0.01, format="%.2f")
        spy_in = st.number_input("SPY Entry Price", 0.0, value=0.0, step=0.01, format="%.2f")
        submitted = st.form_submit_button("Log Signal")

        if submitted:
            if not ticker_in:
                st.error("Ticker is required.")
            elif price_in <= 0:
                st.error("Entry price must be > 0.")
            else:
                try:
                    sig_id = add_signal(
                        ticker=ticker_in,
                        composite_score=float(score_in),
                        factor_scores={},
                        price=price_in,
                        spy_price=spy_in if spy_in > 0 else 0.0,
                    )
                    st.success(f"Signal logged: {ticker_in} (ID: {sig_id[:8]}...)")
                    st.cache_data.clear()
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

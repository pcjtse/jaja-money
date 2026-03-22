"""Forward Testing Dashboard (P22.1).

Paper portfolio tracker for forward-testing AI-recommended stocks without
risking real capital.  Supports multiple named portfolios, live P&L tracking,
closed trade history, daily equity curves, and summary statistics.
"""

from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

import src.analysis.forward_test as ft

from src.ui.theme import inject_css, page_header

st.set_page_config(
    page_title="Forward Test",
    page_icon="🧪",
    layout="wide",
)
inject_css()
page_header(
    "Forward Testing — Paper Portfolio",
    subtitle=(
        "Track AI-recommended stocks in a paper portfolio to validate signals "
        "without risking real capital."
    ),
    icon="🧪",
)

# ---------------------------------------------------------------------------
# Portfolio management sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Portfolios")

    # Create new portfolio
    with st.expander("Create New Portfolio", expanded=False):
        new_pf_name = st.text_input("Portfolio name", placeholder="e.g. AI Picks Q1")
        if st.button("Create", key="create_pf_btn"):
            if new_pf_name.strip():
                pf_id = ft.create_portfolio(new_pf_name.strip())
                st.success(f"Created portfolio '{new_pf_name}' (id={pf_id})")
                st.rerun()
            else:
                st.warning("Please enter a portfolio name.")

    # List portfolios
    portfolios = ft.list_portfolios()
    if not portfolios:
        st.caption("No portfolios yet.  Create one above.")
        st.stop()

    pf_names = [p["name"] for p in portfolios]
    selected_name = st.radio("Select portfolio", pf_names, key="pf_radio")
    selected_pf = next(p for p in portfolios if p["name"] == selected_name)
    selected_pf_id = selected_pf["id"]

    st.divider()

    # Rename
    with st.expander("Rename Portfolio"):
        rename_val = st.text_input("New name", value=selected_name, key="rename_input")
        if st.button("Rename", key="rename_btn"):
            if rename_val.strip() and rename_val.strip() != selected_name:
                ft.rename_portfolio(selected_pf_id, rename_val.strip())
                st.success("Renamed.")
                st.rerun()

    # Delete
    with st.expander("Delete Portfolio"):
        st.warning("This permanently deletes the portfolio and all its trades.")
        if st.button("Delete", key="delete_pf_btn", type="secondary"):
            ft.delete_portfolio(selected_pf_id)
            st.success("Portfolio deleted.")
            st.rerun()

# ---------------------------------------------------------------------------
# Add position manually
# ---------------------------------------------------------------------------

st.subheader(f"Portfolio: {selected_name}")
st.caption(f"Created: {selected_pf['created_date']}")

with st.expander("Add Position Manually"):
    ac1, ac2, ac3, ac4 = st.columns(4)
    ap_symbol = (
        ac1.text_input("Symbol", placeholder="AAPL", key="ap_sym").strip().upper()
    )
    ap_price = ac2.number_input(
        "Entry Price ($)", min_value=0.01, value=100.0, key="ap_price"
    )
    ap_shares = ac3.number_input("Shares", min_value=0.01, value=1.0, key="ap_shares")
    ap_factor = ac4.number_input(
        "Factor Score (0-100)", min_value=0, max_value=100, value=0, key="ap_factor"
    )
    ap_risk = ac4.number_input(
        "Risk Score (0-100)", min_value=0, max_value=100, value=0, key="ap_risk"
    )
    if st.button("Add Position", key="ap_btn"):
        if ap_symbol:
            ft.add_position(
                portfolio_id=selected_pf_id,
                symbol=ap_symbol,
                entry_price=ap_price,
                factor_score=ap_factor if ap_factor else None,
                risk_score=ap_risk if ap_risk else None,
                shares=ap_shares,
            )
            ft.snapshot_portfolio(selected_pf_id, {ap_symbol: ap_price})
            st.success(f"Added {ap_symbol} @ ${ap_price:.2f}")
            st.rerun()
        else:
            st.warning("Please enter a symbol.")

# ---------------------------------------------------------------------------
# Open positions
# ---------------------------------------------------------------------------

open_positions = ft.get_open_positions(selected_pf_id)

st.subheader("Open Positions")
if open_positions:
    # Attempt to fetch live prices for P&L
    live_prices: dict[str, float] = {}
    symbols_needed = list({p["symbol"] for p in open_positions})
    with st.spinner("Fetching live quotes..."):
        try:
            from api import get_api

            _api = get_api()
            _fetch_errors = []
            for sym in symbols_needed:
                try:
                    q = _api.get_quote(sym)
                    live_prices[sym] = q.get("c", 0)
                except Exception as _qe:
                    _fetch_errors.append(f"{sym}: {_qe}")
            if _fetch_errors:
                st.warning(
                    f"Could not fetch live quotes for: {', '.join(_fetch_errors)}. "
                    "P&L may use entry prices instead."
                )
        except Exception:
            pass

    rows = []
    for pos in open_positions:
        sym = pos["symbol"]
        entry = pos["entry_price"]
        current = live_prices.get(sym, entry)
        days_held = (pd.Timestamp.today() - pd.Timestamp(pos["entry_date"])).days
        pnl_pct = (current - entry) / entry * 100 if entry else 0.0
        rows.append(
            {
                "ID": pos["id"],
                "Symbol": sym,
                "Entry Price": f"${entry:,.2f}",
                "Current Price": f"${current:,.2f}" if current else "—",
                "Unrealised P&L %": f"{pnl_pct:+.2f}%",
                "Shares": pos["shares"],
                "Days Held": days_held,
                "Factor Score": pos["factor_score_entry"] or "—",
                "Risk Score": pos["risk_score_entry"] or "—",
                "Entry Date": pos["entry_date"],
            }
        )

    df_open = pd.DataFrame(rows)
    st.dataframe(df_open.drop(columns=["ID"]), use_container_width=True)

    # Close position widget
    st.write("**Close a position:**")
    close_cols = st.columns([2, 2, 1])
    close_id = close_cols[0].selectbox(
        "Trade ID",
        [p["id"] for p in open_positions],
        format_func=lambda tid: next(
            (f"{p['symbol']} (id={p['id']})" for p in open_positions if p["id"] == tid),
            str(tid),
        ),
        key="close_trade_id",
    )
    # Pre-fill with live price if available
    _close_pos = next((p for p in open_positions if p["id"] == close_id), None)
    _default_exit = (
        live_prices.get(_close_pos["symbol"], _close_pos["entry_price"])
        if _close_pos
        else 0.0
    )
    close_price = close_cols[1].number_input(
        "Exit Price ($)", min_value=0.01, value=float(_default_exit), key="close_price"
    )
    if close_cols[2].button("Close", key="close_pos_btn"):
        ft.close_position(close_id, close_price)
        # Snapshot after close
        if live_prices:
            ft.snapshot_portfolio(selected_pf_id, live_prices)
        st.success(f"Position {close_id} closed at ${close_price:.2f}")
        st.rerun()

    # Snapshot portfolio with live prices
    if live_prices and st.button("Refresh Snapshot", key="snapshot_btn"):
        ft.snapshot_portfolio(selected_pf_id, live_prices)
        st.success("Portfolio valuation updated.")
        st.rerun()
else:
    st.info("No open positions.  Add positions from the main analysis page or above.")

# ---------------------------------------------------------------------------
# Equity curve
# ---------------------------------------------------------------------------

equity_curve = ft.get_equity_curve(selected_pf_id)
if len(equity_curve) >= 2:
    st.subheader("Equity Curve")
    ec_dates = [r["date"] for r in equity_curve]
    ec_values = [r["total_value"] for r in equity_curve]
    fig_ec = go.Figure()
    fig_ec.add_trace(
        go.Scatter(
            x=ec_dates,
            y=ec_values,
            mode="lines+markers",
            name="Portfolio Value",
            line=dict(color="#2da44e", width=2),
            fill="tozeroy",
            fillcolor="rgba(45,164,78,0.10)",
        )
    )
    fig_ec.update_layout(
        height=280,
        margin=dict(t=10, b=10, l=10, r=10),
        yaxis_title="Total Value ($)",
        xaxis_title="Date",
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_ec, use_container_width=True)

# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

closed_trades = ft.get_closed_trades(selected_pf_id)
stats = ft._calc_stats(equity_curve, closed_trades)

st.subheader("Summary Statistics")
sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
sc1.metric("Total Return", f"{stats['total_return_pct']:+.2f}%")
sc2.metric("Ann. Return", f"{stats['annualized_return_pct']:+.2f}%")
sc3.metric(
    "Sharpe Ratio",
    f"{stats['sharpe_ratio']:.2f}" if stats["sharpe_ratio"] is not None else "—",
)
sc4.metric("Max Drawdown", f"{stats['max_drawdown_pct']:.2f}%")
sc5.metric(
    "Win Rate",
    f"{stats['win_rate_pct']:.1f}%" if stats["win_rate_pct"] is not None else "—",
)
sc6.metric("Closed Trades", stats["trade_count"])

# ---------------------------------------------------------------------------
# Closed trade history
# ---------------------------------------------------------------------------

st.subheader("Closed Trade History")
if closed_trades:
    ct_rows = []
    for t in closed_trades:
        ct_rows.append(
            {
                "Symbol": t["symbol"],
                "Entry Date": t["entry_date"],
                "Exit Date": t["exit_date"],
                "Entry Price": f"${t['entry_price']:,.2f}",
                "Exit Price": f"${t['exit_price']:,.2f}" if t["exit_price"] else "—",
                "Realised P&L %": f"{t['pnl_pct']:+.2f}%",
                "Shares": t["shares"],
                "Factor Score": t["factor_score_entry"] or "—",
                "Risk Score": t["risk_score_entry"] or "—",
            }
        )
    st.dataframe(pd.DataFrame(ct_rows), use_container_width=True)
else:
    st.info("No closed trades yet.")

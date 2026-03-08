"""Backtesting Engine page (P3.2)."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from api import FinnhubAPI
from backtest import run_backtest

st.set_page_config(page_title="Backtest", page_icon="📊", layout="wide")
st.title("Strategy Backtesting")
st.caption(
    "Test the factor signal model against historical price data. "
    "The signal is a price-based composite of SMA trend, RSI, and MACD."
)

# -------------------------------------------------------------------------
# Inputs
# -------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
symbol = col1.text_input("Stock Symbol", value="AAPL").strip().upper()
entry_threshold = col2.slider("Entry signal threshold (Buy when ≥)", 50, 85, 65)
exit_threshold = col3.slider("Exit signal threshold (Sell when ≤)", 20, 60, 40)

col4, col5 = st.columns(2)
lookback = col4.selectbox(
    "Lookback period",
    ["1 year", "2 years", "3 years", "5 years"],
    index=1,
)
lookback_years = {"1 year": 1.0, "2 years": 2.0, "3 years": 3.0, "5 years": 5.0}[lookback]

with st.expander("How the signal works"):
    st.markdown("""
    The **Signal Score (0-100)** is a price-based composite:
    - **40%** — SMA trend (price vs. SMA-50/SMA-200 regime)
    - **30%** — RSI(14) momentum
    - **30%** — MACD histogram direction

    **Entry:** Buy when signal ≥ entry threshold.
    **Exit:** Sell when signal ≤ exit threshold.

    Note: This uses only price data (no fundamental data) for historical backtesting.
    """)

# -------------------------------------------------------------------------
# Run backtest
# -------------------------------------------------------------------------
if st.button("Run Backtest", type="primary"):
    if not symbol:
        st.error("Please enter a symbol.")
        st.stop()

    api = FinnhubAPI()

    with st.spinner(f"Fetching {lookback} of price data for {symbol}..."):
        try:
            daily = api.get_daily(symbol, years=max(3, int(lookback_years) + 1))
            df = pd.DataFrame({
                "Date": pd.to_datetime(daily["t"], unit="s"),
                "Open": daily["o"],
                "High": daily["h"],
                "Low": daily["l"],
                "Close": daily["c"],
                "Volume": daily["v"],
            }).sort_values("Date").reset_index(drop=True)
        except Exception as e:
            st.error(f"Could not fetch price data: {e}")
            st.stop()

    with st.spinner("Running backtest..."):
        try:
            result = run_backtest(
                df=df,
                symbol=symbol,
                entry_threshold=entry_threshold,
                exit_threshold=exit_threshold,
                lookback_years=lookback_years,
            )
        except ValueError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Backtest failed: {e}")
            st.stop()

    # -------------------------------------------------------------------------
    # Performance summary
    # -------------------------------------------------------------------------
    st.subheader("Performance Summary")

    vs_bench = result.total_return_pct - result.benchmark_return_pct
    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    kc1.metric(
        "Strategy Return",
        f"{result.total_return_pct:+.1f}%",
        f"{vs_bench:+.1f}% vs buy-and-hold",
    )
    kc2.metric("CAGR", f"{result.cagr_pct:+.1f}%")
    kc3.metric("Sharpe Ratio", f"{result.sharpe_ratio:.2f}" if result.sharpe_ratio else "N/A")
    kc4.metric("Max Drawdown", f"{result.max_drawdown_pct:.1f}%")
    kc5.metric("Win Rate", f"{result.win_rate_pct:.1f}%",
               f"{result.total_trades} trades")

    st.caption(
        f"Backtest period: {result.start_date} → {result.end_date}  |  "
        f"Buy-and-hold return: {result.benchmark_return_pct:+.1f}%  |  "
        f"Entry threshold: {result.entry_threshold}  Exit threshold: {result.exit_threshold}"
    )

    # -------------------------------------------------------------------------
    # Equity curve
    # -------------------------------------------------------------------------
    st.subheader("Equity Curve vs. Buy-and-Hold")

    fig_equity = go.Figure()
    fig_equity.add_trace(go.Scatter(
        x=result.equity_dates,
        y=[v * 100 for v in result.equity_curve],
        name="Strategy",
        line=dict(color="#2da44e", width=2),
    ))
    fig_equity.add_trace(go.Scatter(
        x=result.equity_dates[:len(result.benchmark_curve)],
        y=[v * 100 for v in result.benchmark_curve],
        name="Buy & Hold",
        line=dict(color="#888", width=2, dash="dot"),
    ))
    fig_equity.add_hline(y=100, line_dash="dot", line_color="#ccc", opacity=0.5)
    fig_equity.update_layout(
        height=450,
        yaxis_title="Portfolio Value (base=100)",
        xaxis_title="Date",
        margin=dict(t=10),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_equity, use_container_width=True)

    # -------------------------------------------------------------------------
    # Trade list
    # -------------------------------------------------------------------------
    if result.trades:
        st.subheader(f"Trade History ({len(result.trades)} trades)")
        trade_rows = []
        for t in result.trades:
            trade_rows.append({
                "Entry Date": t.entry_date,
                "Exit Date": t.exit_date,
                "Entry Price": f"${t.entry_price:,.2f}",
                "Exit Price": f"${t.exit_price:,.2f}",
                "P&L %": f"{t.pnl_pct:+.1f}%",
                "Result": "✅ Win" if t.is_win else "❌ Loss",
                "Signal @ Entry": t.signal_at_entry,
            })
        trade_df = pd.DataFrame(trade_rows)
        st.dataframe(trade_df, use_container_width=True, hide_index=True)

        # P&L histogram
        pnls = [t.pnl_pct for t in result.trades]
        fig_pnl = go.Figure(go.Histogram(
            x=pnls,
            nbinsx=20,
            marker_color=["#2da44e" if p > 0 else "#e05252" for p in pnls],
            opacity=0.8,
        ))
        fig_pnl.add_vline(x=0, line_dash="dash", line_color="#333")
        fig_pnl.update_layout(
            height=250,
            xaxis_title="Trade P&L %",
            yaxis_title="Count",
            margin=dict(t=10),
        )
        st.plotly_chart(fig_pnl, use_container_width=True)

    # -------------------------------------------------------------------------
    # Claude commentary
    # -------------------------------------------------------------------------
    st.subheader("AI Backtest Commentary")
    if st.button("Analyze with Claude"):
        from analyzer import _get_client
        client = _get_client()

        prompt = f"""## Backtest Analysis: {symbol}

**Strategy:** Price-based factor signal (SMA trend 40% + RSI 30% + MACD 30%)
**Entry threshold:** {result.entry_threshold} | **Exit threshold:** {result.exit_threshold}
**Period:** {result.start_date} to {result.end_date}

**Results:**
- Strategy total return: {result.total_return_pct:+.1f}%
- Buy-and-hold return: {result.benchmark_return_pct:+.1f}%
- Alpha vs. buy-and-hold: {result.total_return_pct - result.benchmark_return_pct:+.1f}%
- CAGR: {result.cagr_pct:+.1f}%
- Sharpe ratio: {result.sharpe_ratio}
- Max drawdown: {result.max_drawdown_pct:.1f}%
- Win rate: {result.win_rate_pct:.1f}% ({result.total_trades} trades)

Please provide:
1. **Performance Assessment** — is this strategy adding value over buy-and-hold?
2. **Risk Assessment** — drawdown and Sharpe analysis
3. **Strategy Robustness** — what could be driving the results (genuine alpha vs. luck)
4. **Weaknesses** — specific risks in using this strategy going forward
5. **Improvement Ideas** — concrete suggestions to improve the signal

Be analytical and honest about limitations."""

        placeholder = st.empty()
        text = ""
        with st.spinner("Claude is analyzing backtest results..."):
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for event in stream:
                    if (event.type == "content_block_delta" and
                            event.delta.type == "text_delta"):
                        text += event.delta.text
                        placeholder.markdown(text)
else:
    st.info("Configure parameters above and click **Run Backtest** to start.")

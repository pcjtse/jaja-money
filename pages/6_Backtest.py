"""Backtesting Engine page (P3.2 + P6.1 + P6.2 + P6.3 + P9.3)."""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

from src.data.api import get_api, MOCK_MODE
from src.analysis.backtest import run_backtest, run_walk_forward, run_parameter_sweep
from src.analysis.analyzer import stream_backtest_narrative

from src.ui.theme import inject_css, page_header

st.set_page_config(page_title="Backtest", page_icon="📊", layout="wide")
inject_css()
page_header(
    "Strategy Backtesting",
    subtitle=(
        "Test the factor signal model against historical price data. "
        "The signal is a price-based composite of SMA trend, RSI, and MACD."
    ),
    icon="📊",
)

# -------------------------------------------------------------------------
# Inputs
# -------------------------------------------------------------------------
if MOCK_MODE:
    st.info("**Mock Data Mode** — Using synthetic data.", icon="🧪")

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
lookback_years = {"1 year": 1.0, "2 years": 2.0, "3 years": 3.0, "5 years": 5.0}[
    lookback
]

# P6.3: Transaction costs
with st.expander("Transaction Costs (P6.3)", expanded=False):
    tc_col1, tc_col2 = st.columns(2)
    commission_pct = (
        tc_col1.number_input(
            "Commission per trade (%)",
            min_value=0.0,
            max_value=1.0,
            value=0.1,
            step=0.05,
        )
        / 100
    )
    slippage_pct = (
        tc_col2.number_input(
            "Slippage per side (%)", min_value=0.0, max_value=0.5, value=0.05, step=0.01
        )
        / 100
    )

# P6.1: Walk-forward validation toggle
enable_walkforward = st.checkbox(
    "Enable walk-forward validation (70%/30% in/out-of-sample)", value=False
)

# P6.2: Parameter sweep toggle
enable_sweep = st.checkbox("Enable parameter sensitivity sweep", value=False)

with st.expander("How the signal works"):
    st.markdown("""
    The **Signal Score (0-100)** is a price-based composite:
    - **40%** — SMA trend (price vs. SMA-50/SMA-200 regime)
    - **30%** — RSI(14) momentum
    - **30%** — MACD histogram direction

    **Entry:** Buy when signal ≥ entry threshold.
    **Exit:** Sell when signal ≤ exit threshold.

    **Note (P6.1 Fix):** Signal computation uses an expanding window — only data
    available up to each bar is used, eliminating look-ahead bias.

    Transaction costs (commission + slippage) are deducted from each trade (P6.3).
    """)

# -------------------------------------------------------------------------
# Run backtest
# -------------------------------------------------------------------------
if st.button("Run Backtest", type="primary"):
    if not symbol:
        st.error("Please enter a symbol.")
        st.stop()

    api = get_api()

    with st.spinner(f"Fetching {lookback} of price data for {symbol}..."):
        try:
            daily = api.get_daily(symbol, years=max(3, int(lookback_years) + 1))
            df = (
                pd.DataFrame(
                    {
                        "Date": pd.to_datetime(daily["t"], unit="s"),
                        "Open": daily["o"],
                        "High": daily["h"],
                        "Low": daily["l"],
                        "Close": daily["c"],
                        "Volume": daily["v"],
                    }
                )
                .sort_values("Date")
                .reset_index(drop=True)
            )
        except Exception as e:
            st.error(f"Could not fetch price data: {e}")
            st.stop()

    # P6.3: Fetch historical dividends for reinvestment simulation
    dividends = None
    try:
        dividends = api.get_dividends(symbol, years=max(3, int(lookback_years) + 1))
    except Exception:
        pass  # non-paying stocks simply have no dividends

    # -------------------------------------------------------------------------
    # Walk-forward validation (P6.1)
    # -------------------------------------------------------------------------
    if enable_walkforward:
        st.subheader("Walk-Forward Validation (P6.1)")
        with st.spinner("Running walk-forward validation..."):
            try:
                in_result, out_result = run_walk_forward(
                    df=df,
                    symbol=symbol,
                    entry_threshold=entry_threshold,
                    exit_threshold=exit_threshold,
                    commission_pct=commission_pct,
                    slippage_pct=slippage_pct,
                )
            except ValueError as e:
                st.error(str(e))
                st.stop()

        wf_col1, wf_col2 = st.columns(2)
        with wf_col1:
            st.markdown("**In-Sample (70% of history)**")
            st.metric(
                "Strategy Return",
                f"{in_result.total_return_pct:+.1f}%",
                f"{in_result.total_return_pct - in_result.benchmark_return_pct:+.1f}% vs B&H",
            )
            st.metric(
                "Sharpe Ratio",
                f"{in_result.sharpe_ratio:.2f}" if in_result.sharpe_ratio else "N/A",
            )
            st.metric("Max Drawdown", f"{in_result.max_drawdown_pct:.1f}%")
            st.metric(
                "Win Rate",
                f"{in_result.win_rate_pct:.1f}% ({in_result.total_trades} trades)",
            )
        with wf_col2:
            st.markdown("**Out-of-Sample (30% of history)**")
            st.metric(
                "Strategy Return",
                f"{out_result.total_return_pct:+.1f}%",
                f"{out_result.total_return_pct - out_result.benchmark_return_pct:+.1f}% vs B&H",
            )
            st.metric(
                "Sharpe Ratio",
                f"{out_result.sharpe_ratio:.2f}" if out_result.sharpe_ratio else "N/A",
            )
            st.metric("Max Drawdown", f"{out_result.max_drawdown_pct:.1f}%")
            st.metric(
                "Win Rate",
                f"{out_result.win_rate_pct:.1f}% ({out_result.total_trades} trades)",
            )

        if in_result.sharpe_ratio and out_result.sharpe_ratio:
            degradation = in_result.sharpe_ratio - out_result.sharpe_ratio
            if degradation > 0.5:
                st.warning(
                    f"⚠️ Significant Sharpe degradation out-of-sample ({degradation:+.2f}). "
                    f"Strategy may be overfitted to historical data."
                )
            elif degradation < 0.1:
                st.success(
                    f"✅ Minimal Sharpe degradation out-of-sample ({degradation:+.2f}). "
                    f"Strategy appears robust."
                )

    # -------------------------------------------------------------------------
    # Parameter Sensitivity Sweep (P6.2)
    # -------------------------------------------------------------------------
    if enable_sweep:
        st.subheader("Parameter Sensitivity Sweep (P6.2)")
        with st.spinner("Running parameter sweep (up to 16 combinations)..."):
            try:
                sweep = run_parameter_sweep(
                    df=df,
                    symbol=symbol,
                    commission_pct=commission_pct,
                    slippage_pct=slippage_pct,
                    lookback_years=lookback_years,
                )
            except Exception as e:
                st.error(f"Parameter sweep failed: {e}")
                sweep = None

        if sweep:
            best = sweep["best_params"]
            sharpe_str = f"{best['sharpe']:.2f}" if best.get("sharpe") else "N/A"
            ret_str = (
                f"{best['total_return']:.1f}%"
                if best.get("total_return") is not None
                else "N/A"
            )
            st.info(
                f"**Best parameters:** Entry={best['entry']}, Exit={best['exit']}, "
                f"Sharpe={sharpe_str}, Return={ret_str}"
            )
            if sweep["boundary_warning"]:
                st.warning(
                    "⚠️ Optimal parameters are at the boundary of the tested range. "
                    "This may indicate overfitting — consider expanding the parameter grid."
                )

            sharpe_grid = sweep["grid_sharpe"]
            if not sharpe_grid.empty:
                fig_heat = px.imshow(
                    sharpe_grid.astype(float).round(2),
                    labels=dict(
                        x="Exit Threshold", y="Entry Threshold", color="Sharpe"
                    ),
                    title="Sharpe Ratio by Entry/Exit Threshold",
                    color_continuous_scale="RdYlGn",
                    text_auto=True,
                )
                fig_heat.update_layout(height=300, margin=dict(t=40))
                st.plotly_chart(fig_heat, use_container_width=True)

            return_grid = sweep["grid_return"]
            if not return_grid.empty:
                fig_heat2 = px.imshow(
                    return_grid.astype(float).round(1),
                    labels=dict(
                        x="Exit Threshold", y="Entry Threshold", color="Return %"
                    ),
                    title="Total Return % by Entry/Exit Threshold",
                    color_continuous_scale="RdYlGn",
                    text_auto=True,
                )
                fig_heat2.update_layout(height=300, margin=dict(t=40))
                st.plotly_chart(fig_heat2, use_container_width=True)

    # -------------------------------------------------------------------------
    # Main backtest results
    # -------------------------------------------------------------------------
    with st.spinner("Running backtest..."):
        try:
            result = run_backtest(
                df=df,
                symbol=symbol,
                entry_threshold=entry_threshold,
                exit_threshold=exit_threshold,
                lookback_years=lookback_years,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
                dividends=dividends,
            )
        except ValueError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Backtest failed: {e}")
            st.stop()

    # Performance summary
    st.subheader("Performance Summary")

    vs_bench = result.total_return_pct - result.benchmark_return_pct
    kc1, kc2, kc3, kc4, kc5, kc6 = st.columns(6)
    kc1.metric(
        "Net Strategy Return",
        f"{result.total_return_pct:+.1f}%",
        f"{vs_bench:+.1f}% vs buy-and-hold",
    )
    kc2.metric(
        "Gross Return",
        f"{result.gross_return_pct:+.1f}%",
        f"Costs: -{result.total_cost_pct:.2f}%",
    )
    kc3.metric("CAGR", f"{result.cagr_pct:+.1f}%")
    kc4.metric(
        "Sharpe Ratio", f"{result.sharpe_ratio:.2f}" if result.sharpe_ratio else "N/A"
    )
    kc5.metric("Max Drawdown", f"{result.max_drawdown_pct:.1f}%")
    kc6.metric(
        "Win Rate", f"{result.win_rate_pct:.1f}%", f"{result.total_trades} trades"
    )

    # P6.3: Dividend reinvestment comparison
    if result.dividend_return_pct > 0:
        div_col1, div_col2 = st.columns(2)
        div_col1.metric(
            "Return (with Dividends Reinvested)",
            f"{result.total_return_with_dividends_pct:+.1f}%",
            f"+{result.dividend_return_pct:.2f}% from dividends",
        )
        div_col2.info(
            f"Dividends received while in position added "
            f"**{result.dividend_return_pct:.2f}%** to strategy return."
        )

    st.caption(
        f"Period: {result.start_date} → {result.end_date}  |  "
        f"Buy-and-hold: {result.benchmark_return_pct:+.1f}%  |  "
        f"Entry: {result.entry_threshold}  Exit: {result.exit_threshold}  |  "
        f"Commission: {commission_pct * 100:.2f}%  Slippage: {slippage_pct * 100:.2f}%/side"
    )

    # Equity curve
    st.subheader("Equity Curve vs. Buy-and-Hold")

    fig_equity = go.Figure()
    fig_equity.add_trace(
        go.Scatter(
            x=result.equity_dates,
            y=[v * 100 for v in result.equity_curve],
            name="Strategy (Net of Costs)",
            line=dict(color="#2da44e", width=2),
        )
    )
    # P6.3: Dividend-reinvested equity curve
    if result.dividend_return_pct > 0 and result.equity_curve_with_dividends:
        fig_equity.add_trace(
            go.Scatter(
                x=result.equity_dates,
                y=[v * 100 for v in result.equity_curve_with_dividends],
                name="Strategy + Dividends Reinvested",
                line=dict(color="#1f77b4", width=2, dash="dash"),
            )
        )
    fig_equity.add_trace(
        go.Scatter(
            x=result.equity_dates[: len(result.benchmark_curve)],
            y=[v * 100 for v in result.benchmark_curve],
            name="Buy & Hold",
            line=dict(color="#888", width=2, dash="dot"),
        )
    )
    fig_equity.add_hline(y=100, line_dash="dot", line_color="#ccc", opacity=0.5)
    fig_equity.update_layout(
        height=450,
        yaxis_title="Portfolio Value (base=100)",
        xaxis_title="Date",
        margin=dict(t=10),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_equity, use_container_width=True)

    # Trade list
    if result.trades:
        st.subheader(f"Trade History ({len(result.trades)} trades)")
        trade_rows = []
        for t in result.trades:
            trade_rows.append(
                {
                    "Entry Date": t.entry_date,
                    "Exit Date": t.exit_date,
                    "Entry Price": f"${t.entry_price:,.2f}",
                    "Exit Price": f"${t.exit_price:,.2f}",
                    "P&L % (Net)": f"{t.pnl_pct:+.1f}%",
                    "Result": "✅ Win" if t.is_win else "❌ Loss",
                    "Signal @ Entry": t.signal_at_entry,
                }
            )
        trade_df = pd.DataFrame(trade_rows)
        st.dataframe(trade_df, use_container_width=True, hide_index=True)

        pnls = [t.pnl_pct for t in result.trades]
        fig_pnl = go.Figure(
            go.Histogram(
                x=pnls,
                nbinsx=20,
                marker_color=["#2da44e" if p > 0 else "#e05252" for p in pnls],
                opacity=0.8,
            )
        )
        fig_pnl.add_vline(x=0, line_dash="dash", line_color="#333")
        fig_pnl.update_layout(
            height=250,
            xaxis_title="Trade P&L % (Net of Costs)",
            yaxis_title="Count",
            margin=dict(t=10),
        )
        st.plotly_chart(fig_pnl, use_container_width=True)

    # -------------------------------------------------------------------------
    # Claude commentary (P9.3)
    # -------------------------------------------------------------------------
    st.subheader("AI Backtest Commentary (P9.3)")
    use_cache = st.checkbox(
        "Use cached Claude analysis if available", value=True, key="bt_cache"
    )
    if st.button("Analyze with Claude"):
        placeholder = st.empty()
        text = ""
        with st.spinner("Claude is analyzing backtest results..."):
            try:
                for chunk in stream_backtest_narrative(result, use_cache=use_cache):
                    text += chunk
                    placeholder.markdown(text)
            except Exception as e:
                st.error(f"Analysis failed: {e}")
else:
    st.info("Configure parameters above and click **Run Backtest** to start.")

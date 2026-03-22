"""Portfolio-Level Risk & Correlation Analysis page (P2.4 + P17.1–P17.5)."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from src.data.api import get_api, MOCK_MODE
from src.analysis.portfolio_analysis import (
    analyze_portfolio,
    compute_risk_parity_weights,
    run_stress_tests,
    find_tax_loss_opportunities,
    compute_portfolio_drift,
)

from src.ui.theme import inject_css, page_header

st.set_page_config(page_title="Portfolio Analysis", page_icon="💼", layout="wide")
inject_css()
page_header(
    "Portfolio Analysis",
    subtitle="Enter a multi-stock portfolio to compute correlation, risk, and diversification metrics.",
    icon="💼",
)

if MOCK_MODE:
    st.info("**Mock Data Mode** — Using synthetic data.", icon="🧪")

# -------------------------------------------------------------------------
# Portfolio input
# -------------------------------------------------------------------------
st.subheader("Portfolio Composition")

default_tickers = "AAPL, MSFT, GOOGL, JPM, XOM"
raw_tickers = st.text_input(
    "Tickers (comma-separated)",
    value=default_tickers,
    placeholder="AAPL, MSFT, GOOGL",
)

tickers = [t.strip().upper() for t in raw_tickers.split(",") if t.strip()]
tickers = list(dict.fromkeys(tickers))  # deduplicate

if len(tickers) < 2:
    st.warning("Enter at least 2 tickers.")
    st.stop()

# Weight inputs
st.subheader("Weights")
st.caption(
    "Set portfolio weights (must sum to 100%). Equal weights applied by default."
)

weight_mode = st.radio(
    "Weight mode", ["Equal weights", "Custom weights"], horizontal=True
)

if weight_mode == "Equal weights":
    eq_w = round(100 / len(tickers), 1)
    weights_pct = [eq_w] * len(tickers)
    # Adjust last to fix rounding
    weights_pct[-1] = round(100 - sum(weights_pct[:-1]), 1)
    for t, w in zip(tickers, weights_pct):
        st.caption(f"{t}: {w}%")
else:
    cols = st.columns(min(len(tickers), 5))
    weights_pct = []
    for i, t in enumerate(tickers):
        col = cols[i % 5]
        w = col.number_input(
            f"{t} %",
            min_value=0.0,
            max_value=100.0,
            value=round(100 / len(tickers), 1),
            key=f"w_{t}",
        )
        weights_pct.append(w)

total_w = sum(weights_pct)
if total_w == 0:
    st.error(
        "All weights are zero. Please assign positive weights to at least one ticker."
    )
    st.stop()
if abs(total_w - 100) > 0.5:
    st.warning(
        f"Weights sum to {total_w:.1f}% (should be 100%). They will be normalized."
    )

# Normalize
weights = [w / total_w for w in weights_pct]

# -------------------------------------------------------------------------
# Run analysis
# -------------------------------------------------------------------------
if st.button("Analyze Portfolio", type="primary"):
    api = get_api()

    with st.spinner("Fetching data and computing portfolio metrics..."):
        try:
            result = analyze_portfolio(tickers, weights, api, include_spy_beta=True)
        except Exception as e:
            st.error(f"Portfolio analysis failed: {e}")
            st.stop()

    stats = result.get("stats", {})
    beta = result.get("portfolio_beta")
    corr = result.get("correlation")

    # -------------------------------------------------------------------------
    # Portfolio KPIs
    # -------------------------------------------------------------------------
    st.subheader("Portfolio Overview")
    kc1, kc2, kc3, kc4, kc5 = st.columns(5)
    kc1.metric("Ann. Return (est.)", f"{stats.get('portfolio_return_pct', 0):.1f}%")
    kc2.metric("Ann. Volatility", f"{stats.get('portfolio_vol_pct', 0):.1f}%")
    sharpe = stats.get("sharpe")
    kc3.metric("Sharpe Ratio", f"{sharpe:.2f}" if sharpe else "N/A")
    kc4.metric("Portfolio Beta", f"{beta:.2f}" if beta is not None else "N/A")
    kc5.metric("Effective Positions", f"{stats.get('effective_n', 0):.1f}")

    div_ratio = stats.get("diversification_ratio", 1.0)
    st.caption(
        f"Diversification ratio: {div_ratio:.2f}  "
        f"(>1 = diversification benefit, =1 = no diversification)"
    )

    # -------------------------------------------------------------------------
    # Correlation heatmap
    # -------------------------------------------------------------------------
    if corr is not None and not corr.empty:
        st.subheader("Return Correlation Matrix")

        z = corr.values.tolist()
        x = corr.columns.tolist()
        y = corr.index.tolist()

        fig_heatmap = go.Figure(
            go.Heatmap(
                z=z,
                x=x,
                y=y,
                colorscale="RdYlGn",
                zmin=-1,
                zmax=1,
                text=[[f"{v:.2f}" for v in row] for row in z],
                texttemplate="%{text}",
                textfont={"size": 12},
                colorbar=dict(title="Correlation"),
            )
        )
        fig_heatmap.update_layout(
            height=400,
            margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)

        st.caption(
            "Green = positively correlated (move together). "
            "Red = negatively correlated (hedge each other). "
            "Yellow = uncorrelated (good for diversification)."
        )

    # -------------------------------------------------------------------------
    # Individual volatility comparison
    # -------------------------------------------------------------------------
    ind_vols = stats.get("individual_vols", {})
    if ind_vols:
        st.subheader("Individual vs. Portfolio Volatility")
        fig_vol = go.Figure()
        vol_tickers = list(ind_vols.keys())
        vol_values = list(ind_vols.values())

        colors_bar = [
            "#2da44e" if v < stats.get("portfolio_vol_pct", 50) else "#e05252"
            for v in vol_values
        ]
        fig_vol.add_trace(
            go.Bar(
                x=vol_tickers,
                y=vol_values,
                marker_color=colors_bar,
                name="Individual Volatility",
                text=[f"{v:.1f}%" for v in vol_values],
                textposition="outside",
            )
        )
        port_vol = stats.get("portfolio_vol_pct", 0)
        fig_vol.add_hline(
            y=port_vol,
            line_dash="dash",
            line_color="#333",
            annotation_text=f"Portfolio Vol: {port_vol:.1f}%",
            annotation_position="right",
        )
        fig_vol.update_layout(
            height=350,
            yaxis_title="Ann. Volatility %",
            margin=dict(t=10),
            showlegend=False,
        )
        st.plotly_chart(fig_vol, use_container_width=True)

    # -------------------------------------------------------------------------
    # Price chart overlay
    # -------------------------------------------------------------------------
    closes = result.get("closes", {})
    if closes:
        st.subheader("Normalized Price History (rebased to 100)")
        fig_prices = go.Figure()
        colors_line = ["#2da44e", "#e05252", "#f0b429", "#6c63ff", "#ff6b35"]
        for i, (ticker, close_s) in enumerate(closes.items()):
            if close_s is None or len(close_s) < 2:
                continue
            normalized = close_s / close_s.iloc[0] * 100
            fig_prices.add_trace(
                go.Scatter(
                    x=close_s.index,
                    y=normalized.values,
                    name=ticker,
                    line=dict(color=colors_line[i % len(colors_line)], width=2),
                )
            )
        fig_prices.add_hline(y=100, line_dash="dot", line_color="#888", opacity=0.5)
        fig_prices.update_layout(
            height=400,
            yaxis_title="Indexed Price (base=100)",
            margin=dict(t=10),
        )
        st.plotly_chart(fig_prices, use_container_width=True)

    # -------------------------------------------------------------------------
    # Claude portfolio memo
    # -------------------------------------------------------------------------
    st.subheader("AI Portfolio Commentary")
    if st.button("Generate Portfolio Commentary with Claude"):
        from analyzer import _get_client

        client = _get_client()

        portfolio_desc = "\n".join(
            f"- {t}: {w * 100:.1f}% weight" for t, w in zip(tickers, weights)
        )

        prompt = f"""## Portfolio Analysis Request

**Composition:**
{portfolio_desc}

**Portfolio Statistics:**
- Estimated annual return: {stats.get("portfolio_return_pct", "N/A")}%
- Annual volatility: {stats.get("portfolio_vol_pct", "N/A")}%
- Sharpe ratio: {stats.get("sharpe", "N/A")}
- Portfolio beta vs SPY: {beta}
- Diversification ratio: {stats.get("diversification_ratio", "N/A")}
- Effective number of positions: {stats.get("effective_n", "N/A")}

Please provide:
1. **Portfolio Assessment** — overall quality and balance
2. **Concentration Risk** — any over-concentration concerns
3. **Diversification** — what the correlation structure tells us
4. **Risk/Return Profile** — how the portfolio compares to typical benchmarks
5. **Suggestions** — 2-3 specific improvements to consider
"""
        placeholder = st.empty()
        text = ""
        with st.spinner("Claude is analyzing your portfolio..."):
            with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=1200,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                    ):
                        text += event.delta.text
                        placeholder.markdown(text)

    # -------------------------------------------------------------------------
    # P17.1: Risk Parity Weights
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("Risk Parity Weights (P17.1)")
    st.caption(
        "Inverse-volatility weighting — allocates more to lower-volatility assets."
    )
    returns_df = result.get("returns_df")
    if returns_df is not None and not returns_df.empty:
        try:
            rp_weights = compute_risk_parity_weights(returns_df)
            rp_cols = st.columns(len(tickers))
            for i, t in enumerate(tickers):
                rp_w = rp_weights.get(t, 0)
                rp_cols[i].metric(t, f"{rp_w * 100:.1f}%")
            st.caption(
                "Compare to your current weights above. Higher allocation = lower volatility stock."
            )
        except Exception as _e:
            st.caption(f"Risk parity weights unavailable: {_e}")
    else:
        st.caption("Run portfolio analysis first to compute risk parity weights.")

    # -------------------------------------------------------------------------
    # P17.2: Stress Tests
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("Historical Stress Tests (P17.2)")
    st.caption("Simulates portfolio loss in major historical market crashes.")
    _positions = [
        {"symbol": t, "weight": w, "sector": "Unknown"}
        for t, w in zip(tickers, weights)
    ]
    _total_value = st.number_input(
        "Portfolio Value ($)", value=100000, step=10000, key="port_val"
    )
    try:
        _stress_results = run_stress_tests(_positions, _total_value)
        if _stress_results:
            stress_rows = []
            for _sr in _stress_results:
                stress_rows.append(
                    {
                        "Scenario": _sr["scenario"],
                        "Est. Loss": f"${_sr['estimated_loss']:,.0f}",
                        "Loss %": f"{_sr['loss_pct']:.1f}%",
                        "Severity": _sr["severity"],
                    }
                )
            st.dataframe(
                pd.DataFrame(stress_rows), use_container_width=True, hide_index=True
            )
    except Exception as _e:
        st.caption(f"Stress tests unavailable: {_e}")

    # -------------------------------------------------------------------------
    # P17.3: Tax-Loss Harvesting
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("Tax-Loss Harvesting Suggestions (P17.3)")
    if returns_df is not None and not returns_df.empty:
        try:
            _tl_opportunities = find_tax_loss_opportunities(_positions, returns_df)
            if _tl_opportunities:
                for _tl in _tl_opportunities:
                    st.info(
                        f"**{_tl['symbol']}** → swap for **{_tl['swap_candidate']}** "
                        f"(correlation: {_tl.get('correlation', 0):.2f}, "
                        f"current loss: {_tl.get('ytd_return_pct', 0):.1f}%)"
                    )
            else:
                st.caption("No tax-loss harvesting opportunities found.")
        except Exception as _e:
            st.caption(f"Tax-loss analysis unavailable: {_e}")
    else:
        st.caption("Run portfolio analysis first.")

    # -------------------------------------------------------------------------
    # P17.5: Portfolio Drift Alerts
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("Portfolio Drift Alerts (P17.5)")
    st.caption(
        "Compares current weights to targets and flags positions that have drifted >5%."
    )
    _target_weights = {
        t: 1 / len(tickers) for t in tickers
    }  # equal-weight target by default
    try:
        _drift_results = compute_portfolio_drift(
            [{**p, "current_weight": w} for p, w in zip(_positions, weights)],
            _target_weights,
        )
        _drifted = [d for d in _drift_results if d.get("needs_rebalance")]
        if _drifted:
            for _dr in _drifted:
                st.warning(
                    f"**{_dr['symbol']}** drifted {_dr['drift_pct']:+.1f}% from target "
                    f"({_dr['target_weight'] * 100:.1f}% → {_dr['current_weight'] * 100:.1f}%)"
                )
        else:
            st.success(
                "Portfolio is within 5% of target weights — no rebalancing needed."
            )
    except Exception as _e:
        st.caption(f"Drift analysis unavailable: {_e}")

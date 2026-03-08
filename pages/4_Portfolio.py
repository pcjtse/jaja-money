"""Portfolio-Level Risk & Correlation Analysis page (P2.4)."""

import streamlit as st
import plotly.graph_objects as go

from api import FinnhubAPI
from portfolio_analysis import analyze_portfolio

st.set_page_config(page_title="Portfolio Analysis", page_icon="💼", layout="wide")
st.title("Portfolio Analysis")
st.caption(
    "Enter a multi-stock portfolio to compute correlation, risk, and diversification metrics."
)

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
st.caption("Set portfolio weights (must sum to 100%). Equal weights applied by default.")

weight_mode = st.radio("Weight mode", ["Equal weights", "Custom weights"], horizontal=True)

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
        w = col.number_input(f"{t} %", min_value=0.0, max_value=100.0,
                             value=round(100/len(tickers), 1), key=f"w_{t}")
        weights_pct.append(w)

total_w = sum(weights_pct)
if abs(total_w - 100) > 0.5:
    st.warning(f"Weights sum to {total_w:.1f}% (should be 100%). They will be normalized.")

# Normalize
weights = [w / total_w for w in weights_pct]

# -------------------------------------------------------------------------
# Run analysis
# -------------------------------------------------------------------------
if st.button("Analyze Portfolio", type="primary"):
    api = FinnhubAPI()

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

        fig_heatmap = go.Figure(go.Heatmap(
            z=z, x=x, y=y,
            colorscale="RdYlGn",
            zmin=-1, zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in z],
            texttemplate="%{text}",
            textfont={"size": 12},
            colorbar=dict(title="Correlation"),
        ))
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

        colors_bar = ["#2da44e" if v < stats.get("portfolio_vol_pct", 50) else "#e05252"
                      for v in vol_values]
        fig_vol.add_trace(go.Bar(
            x=vol_tickers, y=vol_values,
            marker_color=colors_bar, name="Individual Volatility",
            text=[f"{v:.1f}%" for v in vol_values],
            textposition="outside",
        ))
        port_vol = stats.get("portfolio_vol_pct", 0)
        fig_vol.add_hline(
            y=port_vol, line_dash="dash", line_color="#333",
            annotation_text=f"Portfolio Vol: {port_vol:.1f}%",
            annotation_position="right",
        )
        fig_vol.update_layout(
            height=350, yaxis_title="Ann. Volatility %",
            margin=dict(t=10), showlegend=False,
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
            normalized = (close_s / close_s.iloc[0] * 100)
            fig_prices.add_trace(go.Scatter(
                x=close_s.index,
                y=normalized.values,
                name=ticker,
                line=dict(color=colors_line[i % len(colors_line)], width=2),
            ))
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
            f"- {t}: {w*100:.1f}% weight"
            for t, w in zip(tickers, weights)
        )

        prompt = f"""## Portfolio Analysis Request

**Composition:**
{portfolio_desc}

**Portfolio Statistics:**
- Estimated annual return: {stats.get('portfolio_return_pct', 'N/A')}%
- Annual volatility: {stats.get('portfolio_vol_pct', 'N/A')}%
- Sharpe ratio: {stats.get('sharpe', 'N/A')}
- Portfolio beta vs SPY: {beta}
- Diversification ratio: {stats.get('diversification_ratio', 'N/A')}
- Effective number of positions: {stats.get('effective_n', 'N/A')}

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
                    if (event.type == "content_block_delta" and
                            event.delta.type == "text_delta"):
                        text += event.delta.text
                        placeholder.markdown(text)

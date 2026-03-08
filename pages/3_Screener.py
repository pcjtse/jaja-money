"""Stock Screener page (P2.1 + P3.1)."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from screener import run_screen, default_universe, apply_filters
from config import cfg

st.set_page_config(page_title="Stock Screener", page_icon="🔍", layout="wide")
st.title("Stock Screener")
st.caption(
    "Filter stocks by factor score, risk score, P/E, RSI, and more. "
    "Supports both manual rule-based filters and AI natural-language queries."
)

# -------------------------------------------------------------------------
# Ticker universe
# -------------------------------------------------------------------------
st.subheader("Ticker Universe")
universe_mode = st.radio(
    "Universe", ["Default (S&P 500 sample)", "Custom tickers"], horizontal=True
)

if universe_mode == "Default (S&P 500 sample)":
    universe = default_universe()
    st.caption(f"Using {len(universe)} pre-configured tickers: {', '.join(universe[:10])}...")
else:
    raw = st.text_area(
        "Enter tickers (comma or newline separated)",
        placeholder="AAPL, MSFT, GOOGL, TSLA",
        height=80,
    )
    universe = [t.strip().upper() for t in raw.replace("\n", ",").split(",") if t.strip()]
    if not universe:
        st.warning("Please enter at least one ticker.")
        st.stop()
    st.caption(f"{len(universe)} tickers entered.")

# -------------------------------------------------------------------------
# Query mode
# -------------------------------------------------------------------------
st.subheader("Filters")
query_mode = st.radio("Query mode", ["Manual filters", "AI natural language query"], horizontal=True)

filters = []

if query_mode == "Manual filters":
    with st.expander("Add filters", expanded=True):
        fc1, fc2, fc3 = st.columns(3)
        min_factor = fc1.slider("Min factor score", 0, 100, 55)
        max_risk = fc2.slider("Max risk score", 0, 100, 60)
        min_factor_add = fc3.checkbox("Apply factor filter", value=True)

        rc1, rc2, rc3 = st.columns(3)
        filter_pe = rc1.checkbox("Max P/E")
        max_pe = rc1.number_input("Max P/E value", value=30.0, disabled=not filter_pe)
        filter_rsi_low = rc2.checkbox("RSI > (oversold guard)")
        min_rsi = rc2.number_input("Min RSI", value=30.0, disabled=not filter_rsi_low)
        filter_trend = rc3.checkbox("Only uptrends")

        if min_factor_add:
            filters.append({"dimension": "factor_score", "operator": ">=", "value": min_factor,
                            "label": f"Factor ≥ {min_factor}"})
            filters.append({"dimension": "risk_score", "operator": "<=", "value": max_risk,
                            "label": f"Risk ≤ {max_risk}"})
        if filter_pe:
            filters.append({"dimension": "pe_ratio", "operator": "<=", "value": max_pe,
                            "label": f"P/E ≤ {max_pe}"})
        if filter_rsi_low:
            filters.append({"dimension": "rsi", "operator": ">=", "value": min_rsi,
                            "label": f"RSI ≥ {min_rsi}"})
        if filter_trend:
            filters.append({"dimension": "trend", "operator": "==", "value": "uptrend",
                            "label": "Uptrend"})

    if filters:
        st.caption("Active filters: " + " · ".join(f["label"] for f in filters))

else:  # AI NL query
    nl_query = st.text_input(
        "Describe what you're looking for",
        placeholder="Find undervalued tech stocks with low risk and strong momentum",
    )
    parsed_filters = []
    if nl_query and st.button("Parse Query with Claude", key="parse_nl"):
        with st.spinner("Claude is parsing your query..."):
            try:
                from analyzer import parse_nl_screen
                parsed = parse_nl_screen(nl_query)
                parsed_filters = parsed.get("filters", [])
                st.success(f"Parsed: {parsed.get('description', '')}")
                if parsed_filters:
                    st.json(parsed_filters)
                    filters = parsed_filters
            except Exception as e:
                st.error(f"Could not parse query: {e}")

# -------------------------------------------------------------------------
# Run screen
# -------------------------------------------------------------------------
if st.button("Run Screen", type="primary"):
    if not universe:
        st.error("No tickers to screen.")
        st.stop()

    progress_bar = st.progress(0)
    status = st.empty()
    results_container = st.empty()

    status.info(f"Screening {len(universe)} tickers... (this may take a minute)")

    try:
        results = run_screen(universe, filters=filters, max_workers=3, delay_between=0.3)
    except Exception as e:
        st.error(f"Screen failed: {e}")
        st.stop()
    finally:
        progress_bar.empty()
        status.empty()

    if not results:
        st.warning("No stocks passed the filters. Try relaxing your criteria.")
        st.stop()

    st.success(f"Found **{len(results)}** stocks matching your criteria.")

    # Display results table
    rows = []
    for r in results:
        rows.append({
            "Symbol": r["symbol"],
            "Name": r.get("name", "")[:25],
            "Sector": r.get("sector", "N/A"),
            "Price": f"${r['price']:,.2f}" if r.get("price") else "N/A",
            "Factor Score": r["factor_score"],
            "Signal": r["composite_label"],
            "Risk Score": r["risk_score"],
            "Risk Level": r["risk_level"],
            "P/E": f"{r['pe_ratio']:.1f}" if r.get("pe_ratio") else "N/A",
            "RSI": f"{r['rsi']:.1f}" if r.get("rsi") else "N/A",
            "Trend": r.get("trend", "N/A"),
            "Flags": r.get("flag_count", 0),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Factor Score": st.column_config.ProgressColumn(
                "Factor Score", min_value=0, max_value=100, format="%d"
            ),
            "Risk Score": st.column_config.ProgressColumn(
                "Risk Score", min_value=0, max_value=100, format="%d"
            ),
        },
    )

    # Factor score distribution
    st.subheader("Factor Score Distribution")
    scores = [r["factor_score"] for r in results]
    fig_hist = go.Figure(go.Histogram(
        x=scores, nbinsx=20,
        marker_color="#2da44e",
        opacity=0.8,
    ))
    fig_hist.update_layout(
        height=300,
        xaxis_title="Factor Score",
        yaxis_title="Count",
        margin=dict(t=10),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # Top 10 scatter: factor score vs. risk score
    st.subheader("Factor Score vs. Risk Score")
    fig_scatter = go.Figure()
    for r in results[:50]:  # limit for readability
        color = r.get("composite_color", "#888")
        fig_scatter.add_trace(go.Scatter(
            x=[r["risk_score"]],
            y=[r["factor_score"]],
            mode="markers+text",
            text=[r["symbol"]],
            textposition="top center",
            marker=dict(size=10, color=color),
            showlegend=False,
            hovertemplate=f"<b>{r['symbol']}</b><br>Factor: {r['factor_score']}<br>Risk: {r['risk_score']}<extra></extra>",
        ))
    # Add quadrant lines
    fig_scatter.add_hline(y=55, line_dash="dot", line_color="#888", opacity=0.5)
    fig_scatter.add_vline(x=45, line_dash="dot", line_color="#888", opacity=0.5)
    fig_scatter.update_layout(
        height=450,
        xaxis_title="Risk Score (lower = less risky)",
        yaxis_title="Factor Score (higher = better)",
        margin=dict(t=10),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # AI summary of top results (P3.1)
    if query_mode == "AI natural language query" and nl_query:
        st.subheader("AI Analysis of Top Results")
        if st.button("Explain top results with Claude"):
            summary_placeholder = st.empty()
            summary_text = ""
            try:
                from analyzer import stream_screener_summary
                with st.spinner("Claude is analyzing top picks..."):
                    for chunk in stream_screener_summary(results[:10], nl_query):
                        summary_text += chunk
                        summary_placeholder.markdown(summary_text)
            except Exception as e:
                st.error(f"Summary failed: {e}")

"""Multi-Stock Comparison page (P1.1)."""

import streamlit as st
import plotly.graph_objects as go

from api import FinnhubAPI
from comparison import compare_tickers, comparison_dataframe

st.set_page_config(page_title="Compare Stocks", page_icon="⚖️", layout="wide")
st.title("Multi-Stock Comparison")
st.caption(
    "Compare up to 5 stocks side-by-side across factor scores, risk, and key metrics."
)

# --- Input ---
raw_input = st.text_input(
    "Enter 2–5 stock symbols (comma-separated)",
    placeholder="e.g. AAPL, MSFT, GOOGL",
)

if not raw_input:
    st.info("Enter stock symbols above to compare them.")
    st.stop()

symbols = [s.strip().upper() for s in raw_input.split(",") if s.strip()]
symbols = list(dict.fromkeys(symbols))  # deduplicate, preserve order

if len(symbols) < 2:
    st.warning("Please enter at least 2 symbols.")
    st.stop()

if len(symbols) > 5:
    st.warning("Limiting to first 5 symbols.")
    symbols = symbols[:5]

if st.button("Run Comparison", type="primary"):
    api = FinnhubAPI()

    results = []
    with st.spinner(f"Analyzing {', '.join(symbols)}..."):
        progress = st.progress(0)
        for i, sym in enumerate(symbols):
            r = compare_tickers([sym], api)
            results.extend(r)
            progress.progress((i + 1) / len(symbols))

    if not results:
        st.error("Could not fetch data for any of the symbols.")
        st.stop()

    # --- Summary table ---
    st.subheader("Summary Comparison")
    df_comp = comparison_dataframe(results)
    st.dataframe(
        df_comp,
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

    # --- Factor score bar chart ---
    st.subheader("Factor Score Comparison")
    fig_bar = go.Figure()
    for r in results:
        color = r.get("composite_color", "#888")
        fig_bar.add_trace(
            go.Bar(
                name=r["symbol"],
                x=[r["symbol"]],
                y=[r["factor_score"]],
                marker_color=color,
                text=[f"{r['factor_score']}/100<br>{r['composite_label']}"],
                textposition="outside",
            )
        )
    fig_bar.update_layout(
        height=350,
        yaxis=dict(range=[0, 110]),
        showlegend=False,
        margin=dict(t=10),
        title="Composite Factor Score",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- Radar chart overlay ---
    st.subheader("Factor Profile Overlay")
    factor_names = [f["name"] for f in results[0]["factors"]]
    factor_names_closed = factor_names + [factor_names[0]]

    colors = ["#2da44e", "#e05252", "#f0b429", "#6c63ff", "#ff6b35"]
    fig_radar = go.Figure()

    for i, r in enumerate(results):
        scores = [f["score"] for f in r["factors"]]
        scores_closed = scores + [scores[0]]
        fig_radar.add_trace(
            go.Scatterpolar(
                r=scores_closed,
                theta=factor_names_closed,
                fill="toself",
                fillcolor=f"rgba({int(colors[i][1:3], 16)},{int(colors[i][3:5], 16)},{int(colors[i][5:], 16)},0.1)",
                line=dict(color=colors[i], width=2),
                name=r["symbol"],
            )
        )

    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9)),
            angularaxis=dict(tickfont=dict(size=10)),
        ),
        showlegend=True,
        height=450,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

    # --- Risk comparison ---
    st.subheader("Risk Score Comparison")
    fig_risk = go.Figure()
    for r in results:
        risk_color = r.get("risk_color", "#888")
        fig_risk.add_trace(
            go.Bar(
                name=r["symbol"],
                x=[r["symbol"]],
                y=[r["risk_score"]],
                marker_color=risk_color,
                text=[f"{r['risk_score']}/100<br>{r['risk_level']}"],
                textposition="outside",
            )
        )
    fig_risk.update_layout(
        height=350,
        yaxis=dict(range=[0, 120]),
        showlegend=False,
        margin=dict(t=10),
        title="Risk Score (higher = more risk)",
    )
    st.plotly_chart(fig_risk, use_container_width=True)

    # --- Key metrics grid ---
    st.subheader("Key Metrics")
    cols = st.columns(len(results))
    for col, r in zip(cols, results):
        with col:
            st.markdown(f"### {r['symbol']}")
            st.caption(r["name"][:30])
            st.metric(
                "Price",
                f"${r['price']:,.2f}" if r["price"] else "N/A",
                f"{r['change_pct']:+.2f}%" if r.get("change_pct") is not None else None,
            )
            st.metric("P/E", f"{r['pe']:.1f}×" if r.get("pe") else "N/A")
            st.metric("Sector", r.get("sector", "N/A"))
            st.metric("Volatility", f"{r['hv']:.1f}%" if r.get("hv") else "N/A")
            st.metric(
                "Drawdown",
                f"{r['drawdown_pct']:.1f}%"
                if r.get("drawdown_pct") is not None
                else "N/A",
            )
            st.metric("Risk Flags", r.get("flag_count", 0))

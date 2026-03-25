"""Signal Quality Dashboard — 21.3.

Shows whether the composite factor score has historically predicted forward
stock returns, using data accumulated in analysis_history / signal_returns.
"""

from __future__ import annotations

import streamlit as st

from src.analysis.signal_validity import (
    backfill_all_forward_returns,
    compute_ic_trend,
    compute_quartile_analysis,
    compute_spearman_correlations,
)
from src.data.history import get_signal_returns
from src.ui.theme import inject_css, page_header

st.set_page_config(
    page_title="Signal Quality — jaja-money",
    page_icon="📊",
    layout="wide",
)
inject_css()
page_header(
    "Signal Quality",
    subtitle="Does the composite score actually predict returns?",
    icon="📊",
)

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Controls")
    horizon = st.selectbox(
        "Return horizon",
        options=[21, 63, 126],
        format_func=lambda d: (
            f"{d} days (~{d // 21} month{'s' if d // 21 != 1 else ''})"
        ),
        index=1,
    )
    if st.button("Refresh Forward Returns", type="primary"):
        with st.spinner("Fetching forward prices…"):
            result = backfill_all_forward_returns()
        st.success(
            f"Done — processed {result['processed']}, "
            f"skipped {result['skipped']}, errors {result['errors']}"
        )
        st.rerun()
    st.caption(
        "Click **Refresh** to compute forward returns for all historical signals "
        "stored in your local history database."
    )

# ---------------------------------------------------------------------------
# Data availability check
# ---------------------------------------------------------------------------

all_rows = get_signal_returns()
rows_with_data = [r for r in all_rows if r.get(f"return_{horizon}d") is not None]

col_left, col_right = st.columns([2, 1])
with col_left:
    st.metric("Total signals in history", len(all_rows))
with col_right:
    st.metric(f"With {horizon}d return data", len(rows_with_data))

if len(rows_with_data) < 4:
    st.info(
        "Not enough forward-return data yet.  "
        "Analyse more stocks over time, then click **Refresh Forward Returns** "
        "in the sidebar once the signal dates are at least 21 days in the past."
    )
    st.stop()

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 1: Quartile return analysis
# ---------------------------------------------------------------------------

st.subheader(f"Quartile Return Analysis — {horizon}-day horizon")

q_data = compute_quartile_analysis(horizon_days=horizon)
quartiles = q_data.get("quartiles", [])

if quartiles:
    import plotly.graph_objects as go

    labels = [q["label"] for q in quartiles]
    medians = [
        q["median_return"] if q["median_return"] is not None else 0.0 for q in quartiles
    ]
    counts = [q["count"] for q in quartiles]
    colors = ["#cf2929" if m < 0 else "#1a7f37" for m in medians]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=medians,
            text=[f"{m:.1f}%" for m in medians],
            textposition="outside",
            marker_color=colors,
            customdata=[[q["count"], q["score_range"]] for q in quartiles],
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Median return: %{y:.2f}%<br>"
                "Sample size: %{customdata[0]}<br>"
                "Score range: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        title=f"Median {horizon}-day Forward Return by Score Quartile",
        yaxis_title="Median Forward Return (%)",
        height=350,
        margin=dict(l=0, r=0, t=50, b=0),
        yaxis=dict(zeroline=True, zerolinewidth=1, zerolinecolor="#888"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Quartile table
    import pandas as pd

    qt_df = pd.DataFrame(
        [
            {
                "Quartile": q["label"],
                "Score Range": q["score_range"],
                "Median Return (%)": q["median_return"],
                "Mean Return (%)": q["mean_return"],
                "Sample Size": q["count"],
            }
            for q in quartiles
        ]
    )
    st.dataframe(qt_df, use_container_width=True, hide_index=True)
else:
    st.caption("Insufficient data for quartile analysis.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 2: Spearman correlation table
# ---------------------------------------------------------------------------

st.subheader("Rank Correlation — Score vs. Forward Return")

corrs = compute_spearman_correlations()

if corrs:
    import pandas as pd

    corr_df = pd.DataFrame(
        [
            {
                "Horizon": f"{c['horizon_days']} days",
                "Spearman ρ": c["correlation"],
                "p-value": c["p_value"],
                "Sample Size": c["sample_size"],
                "Significant (p<0.05)": "✓" if c["significant"] else "✗",
            }
            for c in corrs
        ]
    )
    st.dataframe(corr_df, use_container_width=True, hide_index=True)

    # Highlight interpretation
    corr_for_horizon = next((c for c in corrs if c["horizon_days"] == horizon), None)
    if corr_for_horizon and corr_for_horizon["correlation"] is not None:
        rho = corr_for_horizon["correlation"]
        sig = corr_for_horizon["significant"]
        if abs(rho) >= 0.3 and sig:
            st.success(
                f"**Strong signal** — Spearman ρ = {rho:.3f} at {horizon}d horizon "
                f"(statistically significant)."
            )
        elif abs(rho) >= 0.1 and sig:
            st.info(
                f"**Moderate signal** — Spearman ρ = {rho:.3f} at {horizon}d horizon "
                f"(statistically significant)."
            )
        elif not sig:
            st.warning(
                f"**Not significant** — Spearman ρ = {rho:.3f} at {horizon}d horizon "
                f"(p = {corr_for_horizon['p_value']:.3f}). More data needed."
            )
else:
    st.caption("Insufficient data for correlation analysis.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 3: IC trend
# ---------------------------------------------------------------------------

st.subheader(f"Information Coefficient Trend — {horizon}-day horizon")

ic_data = compute_ic_trend(horizon_days=horizon)
trend_label = ic_data.get("trend", "Insufficient data")
latest_ic = ic_data.get("latest_ic")

trend_col, ic_col = st.columns(2)
trend_col.metric("Signal Trend", trend_label)
if latest_ic is not None:
    ic_col.metric("Latest Monthly IC", f"{latest_ic:.3f}")
else:
    ic_col.metric("Latest Monthly IC", "N/A")

months = ic_data.get("months", [])
ic_values = ic_data.get("ic_values", [])

if months and any(v is not None for v in ic_values):
    import plotly.graph_objects as go

    # Replace None with gaps for the line chart
    clean_ic = [v if v is not None else None for v in ic_values]

    fig2 = go.Figure(
        go.Scatter(
            x=months,
            y=clean_ic,
            mode="lines+markers",
            line=dict(color="#3b82f6"),
            connectgaps=False,
            name=f"IC ({horizon}d)",
            hovertemplate="%{x}: IC = %{y:.3f}<extra></extra>",
        )
    )
    fig2.add_hline(y=0, line_dash="dash", line_color="#888", annotation_text="IC = 0")
    fig2.update_layout(
        title=f"Monthly Information Coefficient — {horizon}-day Horizon",
        yaxis_title="Spearman IC",
        height=300,
        margin=dict(l=0, r=0, t=50, b=0),
    )
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "IC > 0 means higher scores predicted positive returns that month. "
        "A declining trend suggests model decay."
    )
else:
    st.caption("Not enough monthly data to plot IC trend yet.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 4: Raw signal data
# ---------------------------------------------------------------------------

with st.expander("Raw signal return data"):
    if all_rows:
        import pandas as pd

        raw_df = pd.DataFrame(
            [
                {
                    "Symbol": r["symbol"],
                    "Signal Date": r["signal_date"],
                    "Score": r["signal_score"],
                    "Price": r["price_at_signal"],
                    "Return 21d (%)": r["return_21d"],
                    "Return 63d (%)": r["return_63d"],
                    "Return 126d (%)": r["return_126d"],
                }
                for r in all_rows
            ]
        )
        st.dataframe(raw_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No signal return data cached yet.")

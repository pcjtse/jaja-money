"""Sector & Industry Rotation Tracker page (P3.3)."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from api import FinnhubAPI
from sectors import get_sector_data, classify_rotation_phase

st.set_page_config(page_title="Sector Rotation", page_icon="🔄", layout="wide")
st.title("Sector & Industry Rotation Tracker")
st.caption(
    "Tracks relative strength across 11 S&P 500 sector ETFs to identify "
    "rotation trends, leading sectors, and lagging sectors."
)

if st.button("Load Sector Data", type="primary"):
    api = FinnhubAPI()

    with st.spinner("Fetching sector ETF data... (11 API calls)"):
        data = get_sector_data(api)

    if not data:
        st.error("Could not fetch sector data.")
        st.stop()

    # Add rotation phase
    for d in data:
        d["phase"] = classify_rotation_phase(
            d.get("score", 50),
            d.get("perf_1m"),
            d.get("perf_3m"),
        )

    # -------------------------------------------------------------------------
    # Sector momentum heatmap
    # -------------------------------------------------------------------------
    st.subheader("Sector Momentum Scores")

    df = pd.DataFrame(data)
    df = df.sort_values("score", ascending=False)

    # Color map for scores
    def score_color(s):
        if s is None:
            return "#888"
        if s >= 70:
            return "#1a7f37"
        elif s >= 55:
            return "#2da44e"
        elif s >= 45:
            return "#888"
        elif s >= 30:
            return "#e05252"
        return "#cf2929"

    # Horizontal bar chart
    fig_bars = go.Figure()
    for _, row in df.iterrows():
        color = score_color(row.get("score", 50))
        fig_bars.add_trace(go.Bar(
            x=[row.get("score", 50)],
            y=[f"{row['ticker']} — {row['name']}"],
            orientation="h",
            marker_color=color,
            text=[f"{row.get('score', 50)}/100 ({row.get('phase', '')})"
                  f"  |  1M: {row.get('perf_1m', 'N/A'):+.1f}%"
                  if row.get('perf_1m') is not None else f"{row.get('score', 50)}/100"],
            textposition="outside",
            showlegend=False,
        ))

    fig_bars.update_layout(
        height=450,
        xaxis=dict(range=[0, 120], title="Momentum Score"),
        margin=dict(t=10, l=200),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_bars, use_container_width=True)

    # -------------------------------------------------------------------------
    # Performance table
    # -------------------------------------------------------------------------
    st.subheader("Sector Performance Summary")
    table_rows = []
    for row in data:
        table_rows.append({
            "Ticker": row["ticker"],
            "Sector": row["name"],
            "Score": row.get("score", 50),
            "Phase": row.get("phase", "N/A"),
            "1M %": f"{row['perf_1m']:+.1f}%" if row.get("perf_1m") is not None else "N/A",
            "3M %": f"{row['perf_3m']:+.1f}%" if row.get("perf_3m") is not None else "N/A",
            "6M %": f"{row['perf_6m']:+.1f}%" if row.get("perf_6m") is not None else "N/A",
            "RSI": f"{row['rsi']:.1f}" if row.get("rsi") is not None else "N/A",
            "Volatility": f"{row['volatility']:.1f}%" if row.get("volatility") is not None else "N/A",
            "> SMA50": "✅" if row.get("above_sma50") else ("❌" if row.get("above_sma50") is not None else "N/A"),
            "> SMA200": "✅" if row.get("above_sma200") else ("❌" if row.get("above_sma200") is not None else "N/A"),
        })

    st.dataframe(
        pd.DataFrame(table_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d"
            ),
        },
    )

    # -------------------------------------------------------------------------
    # Rotation quadrant chart
    # -------------------------------------------------------------------------
    st.subheader("Rotation Quadrant: 1M vs 3M Performance")
    st.caption(
        "**Leading** = Strong recent + strong medium term. "
        "**Improving** = Recent uptick, still recovering longer-term. "
        "**Weakening** = Recent weakness after prior strength. "
        "**Lagging** = Weakness across both timeframes."
    )

    fig_quad = go.Figure()
    phase_colors = {
        "Leading": "#1a7f37",
        "Improving": "#f0b429",
        "Weakening": "#e05252",
        "Lagging": "#cf2929",
        "Neutral": "#888",
    }

    for row in data:
        perf_1m = row.get("perf_1m")
        perf_3m = row.get("perf_3m")
        if perf_1m is None or perf_3m is None:
            continue
        phase = row.get("phase", "Neutral")
        color = phase_colors.get(phase, "#888")

        fig_quad.add_trace(go.Scatter(
            x=[perf_3m],
            y=[perf_1m],
            mode="markers+text",
            text=[row["ticker"]],
            textposition="top center",
            marker=dict(size=14, color=color, line=dict(width=1, color="white")),
            showlegend=False,
            name=phase,
            hovertemplate=(
                f"<b>{row['ticker']} — {row['name']}</b><br>"
                f"1M: {perf_1m:+.1f}%<br>"
                f"3M: {perf_3m:+.1f}%<br>"
                f"Phase: {phase}<extra></extra>"
            ),
        ))

    fig_quad.add_hline(y=0, line_dash="dot", line_color="#888", opacity=0.5)
    fig_quad.add_vline(x=0, line_dash="dot", line_color="#888", opacity=0.5)

    # Quadrant labels
    for (x, y, text) in [
        (5, 5, "Leading"), (-5, 5, "Improving"),
        (5, -5, "Weakening"), (-5, -5, "Lagging")
    ]:
        fig_quad.add_annotation(
            x=x, y=y, text=f"<b>{text}</b>",
            showarrow=False, font=dict(size=11, color="#aaa"),
        )

    fig_quad.update_layout(
        height=500,
        xaxis_title="3-Month Performance %",
        yaxis_title="1-Month Performance %",
        margin=dict(t=10),
    )
    st.plotly_chart(fig_quad, use_container_width=True)

    # -------------------------------------------------------------------------
    # Claude commentary
    # -------------------------------------------------------------------------
    st.subheader("AI Sector Rotation Commentary")
    if st.button("Generate Sector Analysis with Claude"):
        from analyzer import _get_client
        client = _get_client()

        sector_summary = "\n".join(
            f"- {d['ticker']} ({d['name']}): score={d.get('score', 'N/A')}, "
            f"phase={d.get('phase', 'N/A')}, "
            f"1M={d['perf_1m']:+.1f}%, 3M={d['perf_3m']:+.1f}%"
            if d.get('perf_1m') is not None and d.get('perf_3m') is not None
            else f"- {d['ticker']} ({d['name']}): data unavailable"
            for d in data
        )

        prompt = f"""## Sector Rotation Analysis

**Current Sector Momentum (sorted by score):**
{sector_summary}

Please provide:
1. **Leading Sectors** — what's driving them and the macro narrative
2. **Lagging Sectors** — key headwinds and potential turning points
3. **Rotation Signals** — any notable rotation patterns (e.g., defensive to cyclical, or vice versa)
4. **Macro Implications** — what this sector picture tells us about the economic cycle
5. **Tactical Recommendations** — 2-3 actionable ideas for sector positioning

Be specific and data-driven. Reference actual performance numbers."""

        placeholder = st.empty()
        text = ""
        with st.spinner("Claude is analyzing sectors..."):
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
else:
    st.info("Click **Load Sector Data** to fetch and analyze all 11 sector ETFs.")

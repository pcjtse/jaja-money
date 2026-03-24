"""Cross-Sectional Daily Long/Short Rankings Page (21.4).

Full-page view of the daily ranking with sector breakdown, historical
rank trend for a selected symbol, AI theses, and manual run/schedule controls.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.core.log_setup import get_logger
from src.data.api import get_api
from src.data.history import (
    get_latest_ranking,
    get_latest_thesis,
    get_ranking_for_date,
)
from src.ui.theme import inject_css, page_header

log = get_logger(__name__)

st.set_page_config(
    page_title="Rankings — jaja-money",
    page_icon="🏆",
    layout="wide",
)
inject_css()

page_header(
    "Daily Long/Short Rankings", subtitle="Cross-sectional factor ranking", icon="🏆"
)

# ---------------------------------------------------------------------------
# Load latest ranking
# ---------------------------------------------------------------------------

ranking = get_latest_ranking()
thesis = get_latest_thesis()

# ---------------------------------------------------------------------------
# Header metrics
# ---------------------------------------------------------------------------

if ranking:
    run_date = ranking.get("date", "N/A")
    all_rows = ranking.get("all_rows", [])
    meta_col1, meta_col2, meta_col3 = st.columns(3)
    meta_col1.metric("Last Run", run_date)
    meta_col2.metric("Stocks Ranked", len(all_rows))
    meta_col3.metric(
        "Sectors Covered", len({r.get("sector") for r in all_rows if r.get("sector")})
    )
else:
    st.info("No ranking data yet. Run a ranking below.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    all_sectors: list[str] = []
    if ranking:
        all_sectors = sorted(
            {r.get("sector") or "N/A" for r in ranking.get("all_rows", [])}
        )

    selected_sector = st.selectbox("Sector", ["All"] + all_sectors)
    min_score = st.slider("Min Factor Score", 0, 100, 0)
    top_n = st.slider("Top / Bottom N", 5, 50, 10)

# ---------------------------------------------------------------------------
# Full leaderboard
# ---------------------------------------------------------------------------

st.subheader("Full Leaderboard")

if ranking:
    rows = ranking.get("all_rows", [])

    if selected_sector != "All":
        rows = [r for r in rows if (r.get("sector") or "N/A") == selected_sector]
    if min_score > 0:
        rows = [r for r in rows if (r.get("factor_score") or 0) >= min_score]

    if rows:
        df = pd.DataFrame(
            [
                {
                    "Rank": r.get("rank_overall"),
                    "Symbol": r.get("symbol"),
                    "Sector": r.get("sector") or "N/A",
                    "Factor Score": r.get("factor_score"),
                    "Risk Score": r.get("risk_score"),
                    "Percentile": r.get("percentile"),
                    "Sector Rank": r.get("rank_in_sector"),
                    "Signal": r.get("composite_label"),
                }
                for r in rows
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.caption("No stocks match the current filters.")
else:
    st.caption("Run a ranking to see results here.")

# ---------------------------------------------------------------------------
# Top Longs / Shorts panels
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader(f"Today's Top {top_n} Longs & Shorts")

long_col, short_col = st.columns(2)

with long_col:
    st.markdown("**Top Longs (Highest Factor Score)**")
    if ranking:
        longs = ranking.get("all_rows", [])
        if selected_sector != "All":
            longs = [r for r in longs if (r.get("sector") or "N/A") == selected_sector]
        longs = longs[:top_n]
        if longs:
            long_df = pd.DataFrame(
                [
                    {
                        "Symbol": r["symbol"],
                        "Score": r.get("factor_score"),
                        "Sector": r.get("sector") or "N/A",
                        "Rank": r.get("rank_overall"),
                    }
                    for r in longs
                ]
            )
            st.dataframe(long_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No long candidates for this filter.")
    else:
        st.caption("No data.")

with short_col:
    st.markdown("**Top Shorts (Lowest Factor Score)**")
    if ranking:
        shorts = list(reversed(ranking.get("all_rows", [])))
        if selected_sector != "All":
            shorts = [
                r for r in shorts if (r.get("sector") or "N/A") == selected_sector
            ]
        shorts = shorts[:top_n]
        if shorts:
            short_df = pd.DataFrame(
                [
                    {
                        "Symbol": r["symbol"],
                        "Score": r.get("factor_score"),
                        "Sector": r.get("sector") or "N/A",
                        "Rank": r.get("rank_overall"),
                    }
                    for r in shorts
                ]
            )
            st.dataframe(short_df, use_container_width=True, hide_index=True)
        else:
            st.caption("No short candidates for this filter.")
    else:
        st.caption("No data.")

# ---------------------------------------------------------------------------
# Sector breakdown
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Sector Breakdown")

if ranking and ranking.get("all_rows"):
    sector_map: dict[str, list[dict]] = {}
    for r in ranking["all_rows"]:
        s = r.get("sector") or "N/A"
        sector_map.setdefault(s, []).append(r)

    for sector_name, sector_rows in sorted(sector_map.items()):
        sector_sorted = sorted(
            sector_rows, key=lambda r: r.get("rank_in_sector") or 9999
        )
        with st.expander(f"{sector_name} ({len(sector_rows)} stocks)"):
            s_col1, s_col2 = st.columns(2)
            with s_col1:
                st.markdown("**Longs**")
                top5 = sector_sorted[:5]
                if top5:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Symbol": r["symbol"],
                                    "Score": r.get("factor_score"),
                                    "Sector Rank": r.get("rank_in_sector"),
                                }
                                for r in top5
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
            with s_col2:
                st.markdown("**Shorts**")
                bot5 = list(reversed(sector_sorted))[:5]
                if bot5:
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Symbol": r["symbol"],
                                    "Score": r.get("factor_score"),
                                    "Sector Rank": r.get("rank_in_sector"),
                                }
                                for r in bot5
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
else:
    st.caption("No ranking data available.")

# ---------------------------------------------------------------------------
# Historical rank trend for a selected symbol
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Historical Rank Trend")

all_symbols: list[str] = []
if ranking:
    all_symbols = sorted({r["symbol"] for r in ranking.get("all_rows", [])})

if all_symbols:
    selected_sym = st.selectbox("Select symbol for rank history", all_symbols)
    if selected_sym:
        import plotly.graph_objects as go
        from datetime import datetime, timedelta

        # Gather last 30 days of ranking data
        trend_dates = []
        trend_ranks = []
        trend_scores = []

        base_date = datetime.utcnow()
        for i in range(29, -1, -1):
            d = (base_date - timedelta(days=i)).strftime("%Y-%m-%d")
            day_rows = get_ranking_for_date(d)
            for row in day_rows:
                if row["symbol"] == selected_sym:
                    trend_dates.append(d)
                    trend_ranks.append(row.get("rank_overall"))
                    trend_scores.append(row.get("factor_score"))
                    break

        if trend_dates:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=trend_dates,
                    y=trend_ranks,
                    mode="lines+markers",
                    name="Overall Rank",
                    line=dict(color="#3b82f6"),
                )
            )
            fig.update_layout(
                title=f"{selected_sym} — Overall Rank (lower = better)",
                yaxis=dict(autorange="reversed"),
                height=300,
                margin=dict(l=0, r=0, t=40, b=0),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption(f"No historical rank data available for {selected_sym}.")
else:
    st.caption("Run a ranking to see historical trends.")

# ---------------------------------------------------------------------------
# AI Theses
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("AI Theses")

if thesis:
    th_col1, th_col2 = st.columns(2)
    with th_col1:
        long_sym = thesis.get("long_symbol", "")
        st.markdown(f"**#1 Long Candidate: {long_sym}**")
        st.markdown(thesis.get("long_thesis") or "_No thesis available._")
    with th_col2:
        short_sym = thesis.get("short_symbol", "")
        st.markdown(f"**#1 Short Candidate: {short_sym}**")
        st.markdown(thesis.get("short_thesis") or "_No thesis available._")
else:
    st.info("No AI thesis yet. Run a ranking to generate today's long/short theses.")

# ---------------------------------------------------------------------------
# Run / Schedule controls
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("Run & Schedule")

ctrl_col1, ctrl_col2 = st.columns(2)

with ctrl_col1:
    st.markdown("**Manual Run**")
    universe_choice = st.selectbox(
        "Universe", ["sp500", "russell1000"], key="rank_universe"
    )
    if st.button("Run Rankings Now", type="primary"):
        from src.analysis.rankings import run_daily_ranking
        from src.services.digest import generate_ranking_thesis

        api = get_api()
        with st.spinner("Scoring universe and ranking..."):
            result = run_daily_ranking(api, universe=universe_choice, force=True)
        st.success(
            f"Ranked {result['scored_count']} stocks "
            f"({result['universe_size']} in universe). "
            f"Errors: {len(result['errors'])}"
        )
        if result.get("top_longs") and result.get("top_shorts"):
            with st.spinner("Generating AI theses..."):
                generate_ranking_thesis(
                    api,
                    long_symbol=result["top_longs"][0]["symbol"],
                    short_symbol=result["top_shorts"][0]["symbol"],
                    run_date=result["run_date"],
                    long_factor_score=result["top_longs"][0].get("factor_score"),
                    short_factor_score=result["top_shorts"][0].get("factor_score"),
                )
            st.success("AI theses generated.")
        st.rerun()

with ctrl_col2:
    st.markdown("**Nightly Scheduler**")
    from src.services.digest import (
        is_ranking_scheduler_running,
        schedule_daily_ranking,
        stop_ranking_scheduler,
    )

    sched_hour = st.number_input(
        "UTC hour", min_value=0, max_value=23, value=22, key="rank_hour"
    )

    if is_ranking_scheduler_running():
        st.success("Scheduler is running")
        if st.button("Stop Scheduler"):
            stop_ranking_scheduler()
            st.rerun()
    else:
        st.caption("Scheduler is not running")
        if st.button("Start Nightly Scheduler"):
            api = get_api()
            ok = schedule_daily_ranking(api, hour=int(sched_hour))
            if ok:
                st.success(f"Scheduler started at {int(sched_hour):02d}:00 UTC")
            else:
                st.warning(
                    "APScheduler not available. Install it with: pip install apscheduler"
                )
            st.rerun()

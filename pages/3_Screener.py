"""Stock Screener page (P2.1 + P3.1 + P7.1 + P7.2 + P7.3)."""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from screener import (
    run_screen, default_universe, load_universe,
    results_to_csv, sentiment_skipped_warning,
    save_screen_template, load_screen_templates, delete_screen_template,
    SHORT_SQUEEZE_PRESET, apply_esg_filter,
)

st.set_page_config(page_title="Stock Screener", page_icon="🔍", layout="wide")
st.title("Stock Screener")
st.caption(
    "Filter stocks by factor score, risk score, P/E, RSI, and more. "
    "Supports rule-based filters with AND/OR logic and AI natural-language queries."
)

# P7.3: Sentiment warning
st.info(sentiment_skipped_warning())

# -------------------------------------------------------------------------
# P7.1: Ticker universe selector
# -------------------------------------------------------------------------
st.subheader("Ticker Universe")

universe_col1, universe_col2 = st.columns([2, 2])
with universe_col1:
    universe_mode = st.radio(
        "Universe",
        ["Default (config sample)", "S&P 500 (100 largest)", "Russell 1000 (extended)", "Custom tickers"],
        horizontal=False,
    )

with universe_col2:
    # P7.1: Sector filter
    sector_filter = st.selectbox(
        "Sector filter (optional)",
        ["All sectors", "Technology", "Healthcare", "Financials", "Consumer Discretionary",
         "Consumer Staples", "Industrials", "Energy", "Utilities", "Materials",
         "Real Estate", "Communication Services"],
    )
    sector_filter_val = None if sector_filter == "All sectors" else sector_filter

if universe_mode == "Default (config sample)":
    universe = default_universe()
    st.caption(f"Using {len(universe)} pre-configured tickers: {', '.join(universe[:10])}...")
elif universe_mode == "S&P 500 (100 largest)":
    universe = load_universe("sp500")
    st.caption(f"Loaded {len(universe)} S&P 500 tickers.")
elif universe_mode == "Russell 1000 (extended)":
    universe = load_universe("russell1000")
    st.caption(f"Loaded {len(universe)} Russell 1000 tickers.")
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
# P7.3: Screen template save/load
# -------------------------------------------------------------------------
with st.expander("Screen Templates (Save / Load)", expanded=False):
    templates = load_screen_templates()
    tpl_col1, tpl_col2 = st.columns(2)
    with tpl_col1:
        if templates:
            selected_tpl = st.selectbox("Load template", ["— select —"] + list(templates.keys()))
            if selected_tpl != "— select —":
                if st.button("Load Selected Template"):
                    st.session_state.screener_filters = templates[selected_tpl]
                    st.success(f"Loaded template: {selected_tpl}")
                    st.rerun()
            if st.button("Delete Selected Template", type="secondary"):
                delete_screen_template(selected_tpl)
                st.success(f"Deleted: {selected_tpl}")
                st.rerun()
        else:
            st.caption("No saved templates yet.")
    with tpl_col2:
        tpl_name = st.text_input("Save current filters as template", placeholder="Template name")
        if st.button("Save Template") and tpl_name:
            current_filters = st.session_state.get("screener_filters", [])
            if current_filters:
                save_screen_template(tpl_name, current_filters)
                st.success(f"Saved template: {tpl_name}")
                st.rerun()
            else:
                st.warning("No active filters to save.")

# -------------------------------------------------------------------------
# P16.4: Short Squeeze Preset
# -------------------------------------------------------------------------
with st.expander("Quick Presets (P16.4)", expanded=False):
    st.caption("Apply pre-built filter sets for common strategies.")
    if st.button("Short Squeeze Candidates", key="short_squeeze_preset"):
        st.session_state.screener_filters = [
            {"dimension": "momentum_min", "operator": ">=",
             "value": SHORT_SQUEEZE_PRESET["momentum_min"],
             "label": f"Momentum ≥ {SHORT_SQUEEZE_PRESET['momentum_min']}"},
        ]
        st.success(
            f"Short squeeze preset applied: "
            f"short %float ≥ {SHORT_SQUEEZE_PRESET['short_pct_float_min']}%, "
            f"days-to-cover ≥ {SHORT_SQUEEZE_PRESET['days_to_cover_min']}"
        )
        st.rerun()

# -------------------------------------------------------------------------
# P19.3: ESG Filter
# -------------------------------------------------------------------------
_esg_filter_enabled = False
_min_esg_score = 0
with st.expander("ESG Filter (P19.3)", expanded=False):
    _esg_filter_enabled = st.checkbox("Filter by minimum ESG score", value=False)
    if _esg_filter_enabled:
        _min_esg_score = st.slider("Minimum ESG score (0–100)", 0, 100, 50)
        st.caption("Filters out companies with ESG scores below the threshold.")

# -------------------------------------------------------------------------
# Query mode
# -------------------------------------------------------------------------
st.subheader("Filters")
query_mode = st.radio("Query mode", ["Manual filters", "AI natural language query"], horizontal=True)

filters = []

if query_mode == "Manual filters":
    # P7.2: AND/OR group support
    with st.expander("Add filter group", expanded=True):
        st.caption("Add filter groups — each group can use AND or OR logic. Groups are combined with AND.")

        # Group 1 (primary AND group)
        fc1, fc2, fc3 = st.columns(3)
        min_factor = fc1.slider("Min factor score", 0, 100, 55)
        max_risk = fc2.slider("Max risk score", 0, 100, 60)
        min_factor_add = fc3.checkbox("Apply quality filters", value=True)

        rc1, rc2, rc3 = st.columns(3)
        filter_pe = rc1.checkbox("Max P/E")
        max_pe = rc1.number_input("Max P/E value", value=30.0, disabled=not filter_pe)
        filter_rsi_low = rc2.checkbox("RSI > (oversold guard)")
        min_rsi = rc2.number_input("Min RSI", value=30.0, disabled=not filter_rsi_low)
        filter_trend = rc3.checkbox("Only uptrends")

        # P7.2: OR group section
        st.markdown("**OR-Logic Group** (stock must match at least ONE of these criteria)")
        or_col1, or_col2 = st.columns(2)
        use_or_group = or_col1.checkbox("Enable OR criteria group")
        or_filters = []
        if use_or_group:
            filter_high_factor = or_col1.checkbox("High factor score (≥ 75)")
            filter_low_risk = or_col2.checkbox("Low risk score (≤ 30)")
            filter_high_div = or_col2.checkbox("High dividend yield (proxy: factor ≥ 65)")
            if filter_high_factor:
                or_filters.append({"dimension": "factor_score", "operator": ">=", "value": 75,
                                    "label": "Factor ≥ 75"})
            if filter_low_risk:
                or_filters.append({"dimension": "risk_score", "operator": "<=", "value": 30,
                                    "label": "Risk ≤ 30"})
            if filter_high_div:
                or_filters.append({"dimension": "factor_score", "operator": ">=", "value": 65,
                                    "label": "Factor ≥ 65"})

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
        # P7.2: Add OR group if configured
        if use_or_group and or_filters:
            filters.append({"connector": "OR", "filters": or_filters,
                            "label": "OR: " + " / ".join(f["label"] for f in or_filters)})

    # Store in session state for template saving
    st.session_state.screener_filters = filters

    if filters:
        display_filters = [f for f in filters if "connector" not in f]
        or_groups = [f for f in filters if "connector" in f]
        labels = [f["label"] for f in display_filters]
        if or_groups:
            labels += [f["label"] for f in or_groups]
        st.caption("Active filters: " + " · ".join(labels))

else:  # AI NL query
    if "screener_filters" not in st.session_state:
        st.session_state.screener_filters = []
    if "screener_query_history" not in st.session_state:
        st.session_state.screener_query_history = []

    nl_query = st.text_input(
        "Describe what you're looking for",
        placeholder="Find undervalued tech stocks with low risk and strong momentum",
    )
    if nl_query and st.button("Parse Query with Claude", key="parse_nl"):
        with st.spinner("Claude is parsing your query..."):
            try:
                from analyzer import parse_nl_screen
                parsed = parse_nl_screen(nl_query)
                parsed_filters = parsed.get("filters", [])
                st.success(f"Parsed: {parsed.get('description', '')}")
                if parsed_filters:
                    st.json(parsed_filters)
                    st.session_state.screener_filters = parsed_filters
                    st.session_state.screener_query_history = [nl_query]
            except Exception as e:
                st.error(f"Could not parse query: {e}")

    if st.session_state.screener_filters:
        st.caption(
            f"Active filters ({len(st.session_state.screener_filters)}): "
            + " · ".join(
                f"{f.get('dimension')} {f.get('operator')} {f.get('value')}"
                if "connector" not in f
                else f"[OR group: {len(f.get('filters', []))} filters]"
                for f in st.session_state.screener_filters
            )
        )
        refine_query = st.text_input(
            "Refine your search (follow-up)",
            placeholder="Also only show stocks with P/E under 30",
            key="screener_refine",
        )
        rc1, rc2 = st.columns([3, 1])
        if rc1.button("Add Refinement with Claude", key="refine_nl"):
            with st.spinner("Claude is refining your query..."):
                try:
                    from analyzer import parse_nl_screen
                    context = (
                        f"Current filters: {st.session_state.screener_filters}\n"
                        f"Refinement: {refine_query}"
                    )
                    parsed = parse_nl_screen(context)
                    new_filters = parsed.get("filters", [])
                    if new_filters:
                        existing_dims = {f["dimension"] for f in new_filters if "connector" not in f}
                        merged = [
                            f for f in st.session_state.screener_filters
                            if "connector" in f or f["dimension"] not in existing_dims
                        ] + new_filters
                        st.session_state.screener_filters = merged
                        st.session_state.screener_query_history.append(refine_query)
                        st.success(f"Refined: {parsed.get('description', '')}")
                        st.rerun()
                except Exception as e:
                    st.error(f"Refinement failed: {e}")
        if rc2.button("Clear Filters", key="clear_nl"):
            st.session_state.screener_filters = []
            st.session_state.screener_query_history = []
            st.rerun()

        if len(st.session_state.screener_query_history) > 1:
            with st.expander("Query history"):
                for i, q in enumerate(st.session_state.screener_query_history):
                    st.markdown(f"{i + 1}. {q}")

    filters = st.session_state.screener_filters

# -------------------------------------------------------------------------
# Run screen
# -------------------------------------------------------------------------
if st.button("Run Screen", type="primary"):
    if not universe:
        st.error("No tickers to screen.")
        st.stop()

    progress_bar = st.progress(0)
    status = st.empty()

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

    # P19.3: Apply ESG filter if enabled
    if _esg_filter_enabled and _min_esg_score > 0:
        pre_esg_count = len(results)
        results = apply_esg_filter(results, _min_esg_score)
        st.caption(f"ESG filter removed {pre_esg_count - len(results)} stocks below ESG score {_min_esg_score}.")
        if not results:
            st.warning("No stocks passed the ESG filter. Try lowering the minimum ESG score.")
            st.stop()

    st.success(f"Found **{len(results)}** stocks matching your criteria.")

    # P7.3: Export CSV button
    csv_data = results_to_csv(results)
    if csv_data:
        st.download_button(
            label="Export Results to CSV",
            data=csv_data,
            file_name="screener_results.csv",
            mime="text/csv",
        )

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

    # Factor score vs. risk score scatter
    st.subheader("Factor Score vs. Risk Score")
    fig_scatter = go.Figure()
    for r in results[:50]:
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
    if query_mode == "AI natural language query" and st.session_state.get("screener_query_history"):
        _nl_q = st.session_state.screener_query_history[0]
        st.subheader("AI Analysis of Top Results")
        if st.button("Explain top results with Claude"):
            summary_placeholder = st.empty()
            summary_text = ""
            try:
                from analyzer import stream_screener_summary
                with st.spinner("Claude is analyzing top picks..."):
                    for chunk in stream_screener_summary(results[:10], _nl_q):
                        summary_text += chunk
                        summary_placeholder.markdown(summary_text)
            except Exception as e:
                st.error(f"Summary failed: {e}")

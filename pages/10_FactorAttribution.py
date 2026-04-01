"""Factor IC Attribution Dashboard.

Shows per-factor Spearman Information Coefficient (IC) against T+21/T+63/T+126
forward returns, with 95% confidence intervals and BH-adjusted p-values.
"""

from __future__ import annotations

import streamlit as st

from src.analysis.factor_attribution import (
    ALPHA_FACTOR_NAMES,
    CORE_FACTOR_NAMES,
    build_attribution_dataset,
    get_attribution_report,
)
from src.ui.theme import inject_css, page_header

st.set_page_config(
    page_title="Factor Attribution — jaja-money",
    page_icon="🔬",
    layout="wide",
)
inject_css()
page_header(
    "Factor IC Attribution",
    subtitle="Which factors actually predict returns?",
    icon="🔬",
)


# ---------------------------------------------------------------------------
# Dataset — cached per hour
# ---------------------------------------------------------------------------


@st.cache_data(ttl=3600)
def _load_dataset():
    return build_attribution_dataset()


base_df, oldest_date = _load_dataset()

if base_df.empty:
    st.info(
        "No attribution data yet. "
        "Analyse stocks over time, then click **Refresh Forward Returns** on "
        "the Signal Quality page once signals are at least 21 trading days old."
    )
    if oldest_date is None:
        st.caption(
            "No analysis history found. Start by analysing a stock on the main page."
        )
    st.stop()

st.caption(
    f"Dataset: **{len(base_df)}** analysis events "
    f"| Earliest signal: **{oldest_date or '—'}**"
)

# ---------------------------------------------------------------------------
# Chart rendering
# ---------------------------------------------------------------------------


def _build_ic_chart(factor_names_dict: dict, results_dict: dict):
    """Build a Plotly horizontal bar chart for IC values with CI error bars."""
    import plotly.graph_objects as go

    names = []
    ics = []
    colors = []
    error_minus = []
    error_plus = []
    hover_texts = []

    # Reversed so highest-priority factor appears at top
    for display_name, col_key in reversed(list(factor_names_dict.items())):
        r = results_dict[col_key]
        ic = r.get("ic")
        n = r.get("n", 0)
        ci_lo = r.get("ci_lo")
        ci_hi = r.get("ci_hi")
        pval_adj = r.get("pval_adjusted")
        pval = r.get("pval")

        names.append(display_name)

        if ic is not None and n >= 30:
            ics.append(ic)
            if ic > 0.05:
                colors.append("#10B981")  # green — positive signal
            elif ic < -0.05:
                colors.append("#EF4444")  # red — negative signal
            else:
                colors.append("#8B949E")  # gray — near-zero
            if ci_lo is not None and ci_hi is not None:
                error_minus.append(ic - ci_lo)
                error_plus.append(ci_hi - ic)
            else:
                error_minus.append(0)
                error_plus.append(0)
            p_val = pval_adj if pval_adj is not None else pval
            p_str = f"  p={p_val:.3f}" if p_val is not None else ""
            ci_str = (
                f"  CI=[{ci_lo:.2f}, {ci_hi:.2f}]"
                if ci_lo is not None and ci_hi is not None
                else ""
            )
            hover_texts.append(
                f"<b>{display_name}</b><br>IC={ic:.3f}  n={n}{ci_str}{p_str}"
            )
        else:
            ics.append(0)
            colors.append("#2D333B")  # near-invisible — insufficient data
            error_minus.append(0)
            error_plus.append(0)
            reason = "need 30+ observations" if n >= 10 else "too few data points"
            hover_texts.append(f"<b>{display_name}</b><br>n={n} — {reason}")

    fig = go.Figure(
        go.Bar(
            y=names,
            x=ics,
            orientation="h",
            marker_color=colors,
            error_x=dict(
                type="data",
                symmetric=False,
                array=error_plus,
                arrayminus=error_minus,
                visible=True,
                color="#8B949E",
                thickness=1.5,
                width=4,
            ),
            hovertext=hover_texts,
            hoverinfo="text",
        )
    )
    fig.add_vline(x=0, line_dash="dash", line_color="#484F58", line_width=1)
    fig.update_layout(
        height=max(180, len(names) * 32),
        margin=dict(l=0, r=40, t=10, b=20),
        xaxis=dict(
            range=[-1.0, 1.0],
            title="Spearman IC",
            tickfont=dict(color="#8B949E"),
            gridcolor="#21262D",
            zerolinecolor="#484F58",
        ),
        yaxis=dict(
            tickfont=dict(color="#E6EDF3", size=12),
            autorange=True,
        ),
        plot_bgcolor="#0D1117",
        paper_bgcolor="#0D1117",
        font=dict(color="#E6EDF3"),
        showlegend=False,
    )
    return fig


def _n_summary(results_dict: dict) -> tuple[int, int]:
    """Return (n_sufficient, n_total) for a results dict."""
    total = len(results_dict)
    sufficient = sum(1 for r in results_dict.values() if r.get("sufficient"))
    return sufficient, total


def _render_tab(horizon: str) -> None:
    report = get_attribution_report(base_df, horizon)
    horizon_label = horizon.replace("return_", "T+").replace("d", " trading days")

    suf_core, tot_core = _n_summary(report["core"])
    suf_alpha, tot_alpha = _n_summary(report["alpha"])
    total = report["total_rows"]

    col1, col2, col3 = st.columns(3)
    col1.metric("Matched rows", total)
    col2.metric("Core factors with IC", f"{suf_core}/{tot_core}")
    col3.metric("Alpha signals with IC", f"{suf_alpha}/{tot_alpha}")

    st.markdown(f"**Core Factors** — {horizon_label}")
    st.caption(
        "Gray bars = n < 30 (need more data). "
        "Green = IC > 0.05. Red = IC < −0.05. Error bars = 95% CI."
    )
    st.plotly_chart(
        _build_ic_chart(CORE_FACTOR_NAMES, report["core"]),
        use_container_width=True,
    )

    st.markdown("**Alpha Signals** (sparse — fewer observations expected)")
    st.plotly_chart(
        _build_ic_chart(ALPHA_FACTOR_NAMES, report["alpha"]),
        use_container_width=True,
    )

    # Insufficient factor list
    insufficient = [
        f"{name} (n={report['core'].get(key, report['alpha'].get(key, {})).get('n', 0)})"
        for name, key in {**CORE_FACTOR_NAMES, **ALPHA_FACTOR_NAMES}.items()
        if not {**report["core"], **report["alpha"]}[key].get("sufficient")
    ]
    if insufficient:
        with st.expander(f"{len(insufficient)} factor(s) need more data"):
            st.caption(
                "These factors have n < 30 and cannot produce reliable IC estimates. "
                "Continue running daily analyses to accumulate data."
            )
            for item in insufficient:
                st.caption(f"• {item}")

    if oldest_date:
        st.caption(
            f"IC trend charts will appear after approximately 6 months of data "
            f"(earliest signal: {oldest_date})."
        )


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab21, tab63, tab126 = st.tabs(["T+21d", "T+63d", "T+126d"])

with tab21:
    _render_tab("return_21d")

with tab63:
    _render_tab("return_63d")

with tab126:
    _render_tab("return_126d")

"""Dark-first UI theme for jaja-money.

Call ``inject_css()`` once at the top of every page (after ``st.set_page_config``)
to apply the premium dark-theme stylesheet and custom component styles.
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Colour palette (also used by Plotly helpers)
# ---------------------------------------------------------------------------

COLORS = {
    "bg": "#0D1117",
    "surface": "#161B22",
    "surface_elevated": "#1C2333",
    "border": "#30363D",
    "accent": "#6366F1",  # indigo-500
    "accent_glow": "#818CF8",  # indigo-400
    "success": "#10B981",  # emerald-500
    "warning": "#F59E0B",  # amber-500
    "danger": "#EF4444",  # red-500
    "text_primary": "#E6EDF3",
    "text_secondary": "#8B949E",
    "text_muted": "#484F58",
    "gold": "#F0B429",
    "cyan": "#22D3EE",
    "purple": "#A855F7",
}

# ---------------------------------------------------------------------------
# Plotly dark template helper
# ---------------------------------------------------------------------------

PLOTLY_DARK_LAYOUT: dict = {
    "template": "plotly_dark",
    "paper_bgcolor": COLORS["surface"],
    "plot_bgcolor": COLORS["surface"],
    "font": {"color": COLORS["text_primary"], "family": "Inter, sans-serif"},
    "xaxis": {
        "gridcolor": COLORS["border"],
        "linecolor": COLORS["border"],
        "tickcolor": COLORS["text_muted"],
    },
    "yaxis": {
        "gridcolor": COLORS["border"],
        "linecolor": COLORS["border"],
        "tickcolor": COLORS["text_muted"],
    },
    "legend": {
        "bgcolor": "rgba(0,0,0,0)",
        "bordercolor": COLORS["border"],
    },
    "margin": {"l": 48, "r": 24, "t": 48, "b": 40},
}

# ---------------------------------------------------------------------------
# CSS stylesheet
# ---------------------------------------------------------------------------

_CSS = """
/* ── Global reset & typography ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* ── Hide Streamlit chrome ──────────────────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* ── App background ─────────────────────────────────────────────────────── */
.stApp {
    background: #0D1117 !important;
}

.stApp > header {
    background: transparent !important;
}

/* ── Sidebar ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #0D1117 !important;
    border-right: 1px solid #21262D !important;
}

[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem;
}

[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #E6EDF3 !important;
}

/* Sidebar brand header */
[data-testid="stSidebar"] h1 {
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    background: linear-gradient(135deg, #6366F1, #818CF8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.02em;
}

/* ── Nav links ──────────────────────────────────────────────────────────── */
[data-testid="stSidebarNavLink"] {
    border-radius: 8px !important;
    margin: 2px 8px !important;
    transition: background 0.15s ease !important;
}

[data-testid="stSidebarNavLink"]:hover {
    background: #161B22 !important;
}

[data-testid="stSidebarNavLink"][aria-selected="true"] {
    background: rgba(99, 102, 241, 0.15) !important;
    border-left: 3px solid #6366F1 !important;
}

/* ── Main content area ──────────────────────────────────────────────────── */
.main .block-container {
    padding: 2rem 3rem 4rem 3rem !important;
    max-width: 1400px !important;
}

/* ── Headings ────────────────────────────────────────────────────────────── */
h1 {
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
    color: #E6EDF3 !important;
    line-height: 1.2 !important;
}

h2 {
    font-size: 1.35rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
    color: #E6EDF3 !important;
    margin-top: 2rem !important;
    padding-bottom: 0.5rem !important;
    border-bottom: 1px solid #21262D !important;
}

h3 {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    color: #C9D1D9 !important;
}

/* ── Metric cards ────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #161B22 !important;
    border: 1px solid #21262D !important;
    border-radius: 12px !important;
    padding: 1rem 1.25rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

[data-testid="stMetric"]:hover {
    border-color: #30363D !important;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4) !important;
}

[data-testid="stMetricLabel"] > div {
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #8B949E !important;
}

[data-testid="stMetricValue"] > div {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #E6EDF3 !important;
    letter-spacing: -0.02em !important;
}

[data-testid="stMetricDelta"] > div {
    font-size: 0.8rem !important;
    font-weight: 500 !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #6366F1 0%, #7C3AED 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 2px 12px rgba(99, 102, 241, 0.35) !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}

[data-testid="baseButton-primary"]:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.5) !important;
}

[data-testid="baseButton-secondary"],
[data-testid="baseButton-tertiary"] {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    color: #C9D1D9 !important;
    font-weight: 500 !important;
    transition: border-color 0.15s ease, background 0.15s ease !important;
}

[data-testid="baseButton-secondary"]:hover,
[data-testid="baseButton-tertiary"]:hover {
    background: #21262D !important;
    border-color: #6366F1 !important;
    color: #E6EDF3 !important;
}

/* ── Text inputs & selects ───────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
.stSelectbox [data-baseweb="select"] {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    color: #E6EDF3 !important;
    font-size: 0.9rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}

[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color: #6366F1 !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
    outline: none !important;
}

/* ── Expanders ───────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #161B22 !important;
    border: 1px solid #21262D !important;
    border-radius: 10px !important;
    overflow: hidden !important;
}

[data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #C9D1D9 !important;
    padding: 0.75rem 1rem !important;
    transition: background 0.15s ease !important;
}

[data-testid="stExpander"] summary:hover {
    background: #1C2333 !important;
}

/* ── Divider ─────────────────────────────────────────────────────────────── */
hr {
    border-color: #21262D !important;
    margin: 1.5rem 0 !important;
}

/* ── Alerts & info boxes ─────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-width: 1px !important;
    font-size: 0.875rem !important;
}

/* Info */
[data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
    background: rgba(99, 102, 241, 0.1) !important;
    border-color: rgba(99, 102, 241, 0.4) !important;
}

/* Success */
[data-testid="stAlert"][data-baseweb="notification"][kind="positive"] {
    background: rgba(16, 185, 129, 0.1) !important;
    border-color: rgba(16, 185, 129, 0.4) !important;
}

/* Warning */
[data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
    background: rgba(245, 158, 11, 0.1) !important;
    border-color: rgba(245, 158, 11, 0.4) !important;
}

/* Error */
[data-testid="stAlert"][data-baseweb="notification"][kind="error"] {
    background: rgba(239, 68, 68, 0.1) !important;
    border-color: rgba(239, 68, 68, 0.4) !important;
}

/* ── DataFrames & tables ─────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    overflow: hidden !important;
    border: 1px solid #21262D !important;
}

/* ── Progress bars ───────────────────────────────────────────────────────── */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, #6366F1, #818CF8) !important;
    border-radius: 4px !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #21262D !important;
    gap: 0.25rem !important;
}

[data-testid="stTabs"] [data-baseweb="tab"] {
    background: transparent !important;
    border-radius: 8px 8px 0 0 !important;
    color: #8B949E !important;
    font-weight: 500 !important;
    padding: 0.6rem 1.2rem !important;
    transition: color 0.15s ease, background 0.15s ease !important;
}

[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    background: #161B22 !important;
    color: #C9D1D9 !important;
}

[data-testid="stTabs"] [aria-selected="true"][data-baseweb="tab"] {
    background: rgba(99, 102, 241, 0.12) !important;
    color: #818CF8 !important;
    border-bottom: 2px solid #6366F1 !important;
}

/* ── Spinner ─────────────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
    border-top-color: #6366F1 !important;
}

/* ── Scrollbar ───────────────────────────────────────────────────────────── */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: #0D1117;
}

::-webkit-scrollbar-thumb {
    background: #30363D;
    border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
    background: #484F58;
}

/* ── Caption / small text ────────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #8B949E !important;
    font-size: 0.78rem !important;
}

/* ── Code blocks ─────────────────────────────────────────────────────────── */
code {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 4px !important;
    padding: 0.1em 0.4em !important;
    color: #79C0FF !important;
    font-size: 0.85em !important;
}

/* ── Slider ──────────────────────────────────────────────────────────────── */
[data-testid="stSlider"] [role="slider"] {
    background: #6366F1 !important;
}

[data-testid="stSlider"] [data-baseweb="slider"] [data-baseweb="slider-inner-track"] {
    background: #6366F1 !important;
}

/* ── Badge / tag style utility ───────────────────────────────────────────── */
.jaja-badge {
    display: inline-block;
    padding: 0.2em 0.65em;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}

.jaja-badge-green  { background: rgba(16,185,129,0.15); color: #34D399; border: 1px solid rgba(16,185,129,0.3); }
.jaja-badge-red    { background: rgba(239,68,68,0.15);  color: #F87171; border: 1px solid rgba(239,68,68,0.3); }
.jaja-badge-yellow { background: rgba(245,158,11,0.15); color: #FBBF24; border: 1px solid rgba(245,158,11,0.3); }
.jaja-badge-blue   { background: rgba(99,102,241,0.15); color: #818CF8; border: 1px solid rgba(99,102,241,0.3); }

/* ── Card containers ─────────────────────────────────────────────────────── */
.jaja-card {
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}

/* ── Gradient page header ────────────────────────────────────────────────── */
.jaja-page-header {
    background: linear-gradient(135deg, rgba(99,102,241,0.08) 0%, rgba(124,58,237,0.04) 100%);
    border: 1px solid rgba(99,102,241,0.15);
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 2rem;
}

.jaja-page-header h1 {
    margin: 0 !important;
    border: none !important;
}

.jaja-section-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #6366F1;
    margin-bottom: 0.5rem;
}
"""

_CSS_INJECTED: set[str] = set()


def inject_css() -> None:
    """Inject the jaja-money dark-theme stylesheet.

    Safe to call multiple times per session — only injects once per page.
    """
    key = "jaja_css_injected"
    if key not in st.session_state:
        st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)
        st.session_state[key] = True


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Render a styled gradient page header banner."""
    icon_html = (
        f"<span style='font-size:1.8rem;margin-right:0.6rem'>{icon}</span>"
        if icon
        else ""
    )
    sub_html = (
        f"<p style='margin:0.4rem 0 0;color:#8B949E;font-size:0.9rem'>{subtitle}</p>"
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div class="jaja-page-header">
          <h1 style="display:flex;align-items:center;gap:0.3rem">
            {icon_html}{title}
          </h1>
          {sub_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_label(text: str) -> None:
    """Render a small uppercase section label above a group of elements."""
    st.markdown(f'<p class="jaja-section-label">{text}</p>', unsafe_allow_html=True)


def badge(text: str, color: str = "blue") -> str:
    """Return HTML for a coloured badge chip.

    Parameters
    ----------
    text:  label text
    color: one of 'green', 'red', 'yellow', 'blue'
    """
    return f'<span class="jaja-badge jaja-badge-{color}">{text}</span>'


def apply_plotly_dark(fig) -> None:
    """Apply the standard dark-theme layout to a Plotly figure in place."""
    fig.update_layout(**PLOTLY_DARK_LAYOUT)

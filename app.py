import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from api import FinnhubAPI
from analyzer import build_data_prompt, stream_fundamental_analysis, stream_sentiment_themes, stream_portfolio_memo
from sentiment import score_articles, aggregate_sentiment, SENTIMENT_COLOR, SENTIMENT_EMOJI
from factors import compute_factors, composite_score, composite_label_color
from guardrails import compute_risk
from portfolio import suggest_position, RISK_TOLERANCES, HORIZONS


# --- Local technical indicator helpers ---

def calc_sma(series: pd.Series, length: int):
    if len(series) < length:
        return None
    return series.rolling(window=length).mean().iloc[-1]


def calc_rsi(series: pd.Series, length: int = 14):
    if len(series) < length + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return val if not pd.isna(val) else None


def calc_macd(
    series: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
):
    if len(series) < slow + signal:
        return None
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]

st.set_page_config(page_title="Stock Analysis", page_icon="📈", layout="wide")

# --- Cached data fetchers ---

@st.cache_data(ttl=300)
def fetch_quote(symbol: str) -> dict:
    return FinnhubAPI().get_quote(symbol)

@st.cache_data(ttl=300)
def fetch_profile(symbol: str) -> dict:
    return FinnhubAPI().get_profile(symbol)

@st.cache_data(ttl=300)
def fetch_financials(symbol: str) -> dict:
    return FinnhubAPI().get_financials(symbol)

@st.cache_data(ttl=300)
def fetch_daily(symbol: str) -> dict:
    return FinnhubAPI().get_daily(symbol)

@st.cache_data(ttl=300)
def fetch_news(symbol: str) -> list:
    return FinnhubAPI().get_news(symbol)

@st.cache_data(ttl=300)
def fetch_recommendations(symbol: str) -> list:
    return FinnhubAPI().get_recommendations(symbol)

@st.cache_data(ttl=300)
def fetch_earnings(symbol: str) -> list:
    return FinnhubAPI().get_earnings(symbol)

@st.cache_data(ttl=300)
def fetch_peers(symbol: str) -> list:
    return FinnhubAPI().get_peers(symbol)


# --- Sidebar ---

with st.sidebar:
    st.header("Stock Analysis")
    symbol = st.text_input("Stock Symbol", placeholder="e.g. AAPL").strip().upper()
    analyze = st.button("Analyze", type="primary", use_container_width=True)
    st.caption(
        "Finnhub free tier: 60 requests/min. "
        "Each analysis uses ~4 API calls. Results are cached for 5 minutes."
    )

# --- Main area ---

if not analyze:
    st.title("Stock Analysis Dashboard")
    st.info("Enter a stock symbol in the sidebar and click **Analyze** to get started.")
    st.stop()

if not symbol:
    st.error("Please enter a stock symbol.")
    st.stop()

st.title(f"Analysis: {symbol}")

# --- Stock Quote ---

try:
    with st.spinner("Fetching quote..."):
        quote = fetch_quote(symbol)
except Exception as e:
    st.error(f"Failed to fetch quote: {e}")
    st.stop()

st.header("Stock Quote")

price = quote.get("c", 0)
change = quote.get("d", 0)
change_pct = quote.get("dp", 0)
high = quote.get("h", 0)
low = quote.get("l", 0)
prev_close = quote.get("pc", 0)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Price", f"${price:,.2f}", f"{change:+.2f} ({change_pct:+.2f}%)")
col2.metric("Day High", f"${high:,.2f}")
col3.metric("Day Low", f"${low:,.2f}")
col4.metric("Previous Close", f"${prev_close:,.2f}")

# --- Company Overview ---

profile = None
financials = None

try:
    with st.spinner("Fetching company overview..."):
        profile = fetch_profile(symbol)
        financials = fetch_financials(symbol)
except Exception as e:
    st.warning(f"Could not fetch company overview: {e}")

if profile:
    st.header("Company Overview")

    name = profile.get("name", symbol)
    sector = profile.get("finnhubIndustry", "N/A")
    logo = profile.get("logo", "")

    st.subheader(name)

    metrics = financials or {}

    pe = metrics.get("peBasicExclExtraTTM")
    eps = metrics.get("epsBasicExclExtraItemsTTM")
    market_cap = metrics.get("marketCapitalization")
    div_yield = metrics.get("dividendYieldIndicatedAnnual")
    high_52 = metrics.get("52WeekHigh")
    low_52 = metrics.get("52WeekLow")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sector", sector)

    if market_cap is not None:
        mc = float(market_cap)
        if mc >= 1_000_000:
            mc_str = f"${mc / 1_000_000:,.2f}T"
        elif mc >= 1_000:
            mc_str = f"${mc / 1_000:,.2f}B"
        else:
            mc_str = f"${mc:,.2f}M"
    else:
        mc_str = "N/A"
    col2.metric("Market Cap", mc_str)

    pe_str = f"{pe:.2f}" if pe is not None else "N/A"
    col3.metric("P/E Ratio", pe_str)

    eps_str = f"${eps:.2f}" if eps is not None else "N/A"
    col4.metric("EPS", eps_str)

    col1, col2 = st.columns(2)
    div_str = f"{div_yield:.2f}%" if div_yield is not None else "N/A"
    col1.metric("Dividend Yield", div_str)

    if high_52 is not None and low_52 is not None:
        range_str = f"${low_52:,.2f} – ${high_52:,.2f}"
    else:
        range_str = "N/A"
    col2.metric("52-Week Range", range_str)

# --- Daily prices (used for chart + technicals) ---

daily = None
df = None

try:
    with st.spinner("Fetching daily prices..."):
        daily = fetch_daily(symbol)
except Exception as e:
    st.error(f"Could not load price data: {e}")

if daily:
    df = pd.DataFrame({
        "Date": pd.to_datetime(daily["t"], unit="s"),
        "Open": daily["o"],
        "High": daily["h"],
        "Low": daily["l"],
        "Close": daily["c"],
        "Volume": daily["v"],
    })
    df = df.sort_values("Date").reset_index(drop=True)

# --- Technical Indicators (computed locally) ---

if df is not None and len(df) > 0:
    st.header("Technical Indicators")

    close = df["Close"]
    tech_cols = st.columns(5)

    sma50 = calc_sma(close, 50)
    if sma50 is not None:
        tech_cols[0].metric("SMA(50)", f"${sma50:,.2f}")
    else:
        tech_cols[0].metric("SMA(50)", "N/A")

    sma200 = calc_sma(close, 200)
    if sma200 is not None:
        tech_cols[1].metric("SMA(200)", f"${sma200:,.2f}")
    else:
        tech_cols[1].metric("SMA(200)", "N/A")

    rsi_val = calc_rsi(close)
    if rsi_val is not None:
        if rsi_val >= 70:
            rsi_label = "Overbought"
        elif rsi_val <= 30:
            rsi_label = "Oversold"
        else:
            rsi_label = "Neutral"
        tech_cols[2].metric("RSI(14)", f"{rsi_val:.2f}", rsi_label)
    else:
        tech_cols[2].metric("RSI(14)", "N/A")

    macd_result = calc_macd(close)
    if macd_result is not None:
        macd_val, signal_val, hist_val = macd_result
        tech_cols[3].metric("MACD", f"{macd_val:.4f}")
        tech_cols[4].metric("Signal / Histogram", f"{signal_val:.4f}", f"{hist_val:+.4f}")
    else:
        tech_cols[3].metric("MACD", "N/A")
        tech_cols[4].metric("Signal / Histogram", "N/A")

# --- Price Chart ---

if df is not None and len(df) > 0:
    chart_df = df.tail(100)

    st.header("Price Chart (Last 100 Days)")

    fig = go.Figure(data=[
        go.Candlestick(
            x=chart_df["Date"],
            open=chart_df["Open"],
            high=chart_df["High"],
            low=chart_df["Low"],
            close=chart_df["Close"],
            name="Price",
        )
    ])
    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Price (USD)",
        xaxis_rangeslider_visible=False,
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Raw Price Data"):
        st.dataframe(
            chart_df.set_index("Date").sort_index(ascending=False),
            use_container_width=True,
        )

# --- Market Research ---

st.header("Market Research")

# Analyst Recommendations
try:
    with st.spinner("Fetching analyst recommendations..."):
        recs = fetch_recommendations(symbol)
except Exception as e:
    recs = []
    st.warning(f"Could not fetch analyst recommendations: {e}")

if recs:
    latest = recs[0]
    st.subheader("Analyst Recommendations")
    period = latest.get("period", "")
    st.caption(f"Most recent period: {period}")

    buy = latest.get("buy", 0)
    hold = latest.get("hold", 0)
    sell = latest.get("sell", 0)
    strong_buy = latest.get("strongBuy", 0)
    strong_sell = latest.get("strongSell", 0)

    rec_cols = st.columns(5)
    rec_cols[0].metric("Strong Buy", strong_buy)
    rec_cols[1].metric("Buy", buy)
    rec_cols[2].metric("Hold", hold)
    rec_cols[3].metric("Sell", sell)
    rec_cols[4].metric("Strong Sell", strong_sell)

    # Bar chart of recommendation breakdown
    fig_rec = go.Figure(go.Bar(
        x=["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
        y=[strong_buy, buy, hold, sell, strong_sell],
        marker_color=["#1a7f37", "#2da44e", "#f0b429", "#e05252", "#cf2929"],
    ))
    fig_rec.update_layout(
        xaxis_title="Rating",
        yaxis_title="Number of Analysts",
        height=300,
        margin=dict(t=20),
    )
    st.plotly_chart(fig_rec, use_container_width=True)

# Earnings History
try:
    with st.spinner("Fetching earnings history..."):
        earnings = fetch_earnings(symbol)
except Exception as e:
    earnings = []
    st.warning(f"Could not fetch earnings history: {e}")

if earnings:
    st.subheader("Earnings History (EPS)")
    rows = []
    for e in earnings:
        actual = e.get("actual")
        estimate = e.get("estimate")
        surprise = e.get("surprisePercent")
        rows.append({
            "Period": e.get("period", ""),
            "Actual EPS": f"${actual:.2f}" if actual is not None else "N/A",
            "Estimated EPS": f"${estimate:.2f}" if estimate is not None else "N/A",
            "Surprise %": f"{surprise:+.2f}%" if surprise is not None else "N/A",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# Peer Companies
try:
    with st.spinner("Fetching peer companies..."):
        peers = fetch_peers(symbol)
except Exception as e:
    peers = []
    st.warning(f"Could not fetch peer companies: {e}")

if peers:
    st.subheader("Peer Companies")
    peer_list = [p for p in peers if p != symbol]
    if peer_list:
        st.write(" · ".join(peer_list))
    else:
        st.write("No peers found.")

scores = []   # FinBERT per-article scores (populated below if news available)
agg = None    # Aggregate sentiment dict

# Recent News + Sentiment
try:
    with st.spinner("Fetching recent news..."):
        news = fetch_news(symbol)
except Exception as e:
    news = []
    st.warning(f"Could not fetch news: {e}")

if news:
    st.subheader("News Sentiment Scan")
    displayed = news[:10]

    # --- Run FinBERT on all displayed headlines ---
    with st.spinner("Scoring sentiment with FinBERT..."):
        scores = score_articles(displayed)
    agg = aggregate_sentiment(scores)

    # --- Aggregate metrics row ---
    signal = agg["signal"]
    net = agg["net_score"]
    counts = agg["counts"]

    signal_color = (
        SENTIMENT_COLOR["positive"] if "Bullish" in signal
        else SENTIMENT_COLOR["negative"] if "Bearish" in signal
        else SENTIMENT_COLOR["neutral"]
    )
    agg_col1, agg_col2 = st.columns([1, 2])
    with agg_col1:
        st.metric("Overall Signal", signal, f"Net score: {net:+.2f}")

    with agg_col2:
        fig_donut = go.Figure(go.Pie(
            labels=["Positive", "Negative", "Neutral"],
            values=[counts["positive"], counts["negative"], counts["neutral"]],
            hole=0.6,
            marker_colors=[
                SENTIMENT_COLOR["positive"],
                SENTIMENT_COLOR["negative"],
                SENTIMENT_COLOR["neutral"],
            ],
            textinfo="label+percent",
            showlegend=False,
        ))
        fig_donut.update_layout(
            height=200,
            margin=dict(t=10, b=10, l=10, r=10),
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    # --- Per-article expanders with sentiment badge ---
    for article, score in zip(displayed, scores):
        headline = article.get("headline", "No title")
        url = article.get("url", "")
        source = article.get("source", "")
        ts = article.get("datetime", 0)
        date_str = datetime.fromtimestamp(ts).strftime("%b %d, %Y") if ts else ""
        summary = article.get("summary", "")
        label = score["label"]
        conf = score["score"]
        emoji = SENTIMENT_EMOJI[label]

        with st.expander(f"{emoji} {date_str}  |  {headline}"):
            st.markdown(
                f'<span style="color:{SENTIMENT_COLOR[label]};font-weight:bold;">'
                f"{label.upper()} {conf:.0%}</span>",
                unsafe_allow_html=True,
            )
            if summary:
                st.write(summary)
            col_src, col_link = st.columns([2, 1])
            col_src.caption(f"Source: {source}")
            if url:
                col_link.markdown(f"[Read article]({url})")

    # --- Claude themes button ---
    st.divider()
    run_themes = st.button(
        "Analyze Sentiment Themes with Claude",
        use_container_width=False,
    )
    if run_themes:
        themes_placeholder = st.empty()
        themes_text = ""
        try:
            with st.spinner("Claude is synthesizing news themes..."):
                for chunk in stream_sentiment_themes(symbol, displayed, scores, agg):
                    themes_text += chunk
                    themes_placeholder.markdown(themes_text)
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Theme analysis failed: {e}")

# --- Factor Score Engine ---

st.divider()
st.header("Factor Score Engine")
st.caption(
    "Eight quantitative factors — valuation, trend, momentum, MACD, sentiment, "
    "earnings quality, analyst consensus, and 52-week strength — combined into "
    "a single composite signal."
)

_close = df["Close"] if df is not None and len(df) > 0 else None
_recs_for_factors = recs
_earnings_for_factors = earnings

_factors = compute_factors(
    quote=quote,
    financials=financials,
    close=_close,
    earnings=_earnings_for_factors,
    recommendations=_recs_for_factors,
    sentiment_agg=agg,
)
_composite = composite_score(_factors)
_label, _color = composite_label_color(_composite)

# Row 1: composite gauge (left) + radar chart (right)
gauge_col, radar_col = st.columns([1, 1])

with gauge_col:
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=_composite,
        number={"suffix": " / 100", "font": {"size": 28}},
        title={"text": f"<b>{_label}</b>", "font": {"size": 20, "color": _color}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": _color, "thickness": 0.3},
            "bgcolor": "white",
            "steps": [
                {"range": [0,  30], "color": "#fde8e8"},
                {"range": [30, 45], "color": "#fef3cd"},
                {"range": [45, 55], "color": "#ebebeb"},
                {"range": [55, 70], "color": "#d4edda"},
                {"range": [70, 100], "color": "#c3e6cb"},
            ],
            "threshold": {
                "line": {"color": _color, "width": 4},
                "thickness": 0.75,
                "value": _composite,
            },
        },
    ))
    fig_gauge.update_layout(height=280, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

with radar_col:
    _names  = [f["name"] for f in _factors]
    _scores = [f["score"] for f in _factors]
    # Close the polygon
    _names_closed  = _names + [_names[0]]
    _scores_closed = _scores + [_scores[0]]

    fig_radar = go.Figure(go.Scatterpolar(
        r=_scores_closed,
        theta=_names_closed,
        fill="toself",
        fillcolor="rgba(45,164,78,0.15)",
        line=dict(color="#2da44e", width=2),
        name="Factor Scores",
    ))
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9)),
            angularaxis=dict(tickfont=dict(size=10)),
        ),
        showlegend=False,
        height=280,
        margin=dict(t=20, b=20, l=40, r=40),
    )
    st.plotly_chart(fig_radar, use_container_width=True)

# Row 2: factor breakdown table
_rows = []
for f in _factors:
    score = f["score"]
    if score >= 70:
        bar = "🟢🟢🟢🟢"
    elif score >= 55:
        bar = "🟢🟢🟢⚪"
    elif score >= 45:
        bar = "🟡🟡⚪⚪"
    elif score >= 30:
        bar = "🔴🔴⚪⚪"
    else:
        bar = "🔴🔴🔴🔴"
    _rows.append({
        "Factor":  f["name"],
        "Score":   score,
        "Signal":  bar,
        "Label":   f["label"],
        "Detail":  f["detail"],
        "Weight":  f"{f['weight']:.0%}",
    })

st.dataframe(
    pd.DataFrame(_rows),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Score":  st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        "Signal": st.column_config.TextColumn("Signal", width="small"),
    },
)

# --- Risk Guardrails ---

st.divider()
st.header("Risk Guardrails")
st.caption(
    "Four risk dimensions — volatility, drawdown, signal strength, and red-flag count — "
    "combined into a single risk score, with actionable alerts for specific danger conditions."
)

_risk = compute_risk(
    quote=quote,
    financials=financials,
    close=_close,
    earnings=_earnings_for_factors,
    recommendations=_recs_for_factors,
    sentiment_agg=agg,
    composite_factor_score=_composite,
)

# Summary row: risk score gauge + key metrics
risk_gauge_col, risk_meta_col = st.columns([1, 1])

with risk_gauge_col:
    _rlabel = _risk["risk_level"]
    _rcolor = _risk["risk_color"]
    _rscore = _risk["risk_score"]
    fig_risk_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=_rscore,
        number={"suffix": " / 100", "font": {"size": 28}},
        title={"text": f"<b>Risk: {_rlabel}</b>", "font": {"size": 18, "color": _rcolor}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": _rcolor, "thickness": 0.3},
            "bgcolor": "white",
            "steps": [
                {"range": [0,  25], "color": "#c3e6cb"},
                {"range": [25, 45], "color": "#d4edda"},
                {"range": [45, 65], "color": "#fef3cd"},
                {"range": [65, 80], "color": "#fde8e8"},
                {"range": [80, 100], "color": "#f5c6cb"},
            ],
            "threshold": {
                "line": {"color": _rcolor, "width": 4},
                "thickness": 0.75,
                "value": _rscore,
            },
        },
    ))
    fig_risk_gauge.update_layout(height=260, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(fig_risk_gauge, use_container_width=True)

with risk_meta_col:
    _hv = _risk.get("hv")
    _dd = _risk.get("drawdown_pct")
    m1, m2 = st.columns(2)
    m1.metric(
        "Annualised Volatility (20d)",
        f"{_hv:.1f}%" if _hv is not None else "N/A",
    )
    m2.metric(
        "Drawdown from 52-Wk High",
        f"{_dd:.1f}%" if _dd is not None else "N/A",
    )
    _flag_count = len(_risk["flags"])
    m1.metric("Active Risk Flags", _flag_count)
    m2.metric("Factor Score (context)", f"{_composite} / 100")

# Flag alerts
_flags = _risk["flags"]
if not _flags:
    st.success("No risk flags triggered. All monitored conditions are within normal ranges.")
else:
    for _f in _flags:
        _body = f"**{_f['icon']} {_f['title']}** — {_f['message']}"
        if _f["severity"] == "danger":
            st.error(_body)
        elif _f["severity"] == "warning":
            st.warning(_body)
        else:
            st.info(_body)

# --- Portfolio Construction ---

st.divider()
st.header("Portfolio Construction")
st.caption(
    "Rule-based position sizing, entry strategy, stop-loss, and price targets "
    "tailored to your risk tolerance and investment horizon. "
    "Optionally generate a full narrative memo with Claude."
)

_pt_col, _ph_col = st.columns(2)
_risk_tolerance = _pt_col.selectbox("Risk Tolerance", RISK_TOLERANCES, index=1)
_horizon        = _ph_col.selectbox("Investment Horizon", HORIZONS, index=1)

_suggestion = suggest_position(
    risk_tolerance=_risk_tolerance,
    horizon=_horizon,
    composite_factor=_composite,
    risk_score=_risk["risk_score"],
    quote=quote,
    close=_close,
)

# Action banner
st.markdown(
    f'<div style="background:{_suggestion["action_color"]}22;border-left:4px solid '
    f'{_suggestion["action_color"]};padding:10px 16px;border-radius:4px;margin:8px 0">'
    f'<span style="font-size:1.3rem;font-weight:700;color:{_suggestion["action_color"]}">'
    f'{_suggestion["action"]}</span>'
    f'<span style="margin-left:12px;color:#555">{_risk_tolerance} · {_horizon}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Key metrics row
_c1, _c2, _c3, _c4, _c5 = st.columns(5)
_c1.metric("Suggested Allocation", _suggestion["position_label"])
_c2.metric(
    "Stop-Loss",
    f"${_suggestion['stop_price']:,.2f}" if _suggestion["stop_price"] else "N/A",
    f"-{_suggestion['stop_pct']:.1f}%" if _suggestion["stop_pct"] else None,
)
_c3.metric(
    "Target 1",
    f"${_suggestion['target_1']:,.2f}" if _suggestion["target_1"] else "N/A",
    (f"+{(_suggestion['target_1'] / quote['c'] - 1) * 100:.1f}%"
     if _suggestion["target_1"] and quote.get("c") else None),
)
_c4.metric(
    "Target 2",
    f"${_suggestion['target_2']:,.2f}" if _suggestion["target_2"] else "N/A",
    (f"+{(_suggestion['target_2'] / quote['c'] - 1) * 100:.1f}%"
     if _suggestion["target_2"] and quote.get("c") else None),
)
_c5.metric(
    "Risk / Reward",
    f"{_suggestion['risk_reward']}×" if _suggestion["risk_reward"] else "N/A",
)

# Entry strategy
st.info(f"**Entry Strategy:** {_suggestion['entry_strategy']}")

# Rationale
with st.expander("Rule-engine rationale"):
    for _r in _suggestion["rationale"]:
        st.markdown(f"- {_r}")

# Claude portfolio memo
st.divider()
_run_memo = st.button("Generate Portfolio Memo with Claude", use_container_width=False)
if _run_memo:
    _memo_placeholder = st.empty()
    _memo_text = ""
    try:
        with st.spinner("Claude is writing your portfolio memo..."):
            for _chunk in stream_portfolio_memo(
                symbol=symbol,
                suggestion=_suggestion,
                factors=_factors,
                risk=_risk,
                profile=profile,
                risk_tolerance=_risk_tolerance,
                horizon=_horizon,
            ):
                _memo_text += _chunk
                _memo_placeholder.markdown(_memo_text)
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Portfolio memo failed: {e}")

# --- Fundamental Analyzer (Claude-powered) ---

st.divider()
st.header("Fundamental Analyzer")
st.caption(
    "Powered by Claude Opus 4.6 with adaptive thinking. "
    "Synthesizes all available data into a structured investment research report."
)

run_analysis = st.button(
    "Run Fundamental Analysis",
    type="primary",
    use_container_width=False,
)

if run_analysis:
    # Build technicals dict from already-computed values
    technicals: dict = {}
    if df is not None and len(df) > 0:
        close = df["Close"]
        sma50_v = calc_sma(close, 50)
        sma200_v = calc_sma(close, 200)
        rsi_v = calc_rsi(close)
        macd_r = calc_macd(close)

        technicals["sma50"] = f"${sma50_v:,.2f}" if sma50_v is not None else "N/A"
        technicals["sma200"] = f"${sma200_v:,.2f}" if sma200_v is not None else "N/A"
        technicals["rsi"] = f"{rsi_v:.2f}" if rsi_v is not None else "N/A"
        if macd_r is not None:
            technicals["macd"] = f"{macd_r[0]:.4f}"
            technicals["macd_signal"] = f"{macd_r[1]:.4f}"
            technicals["macd_hist"] = f"{macd_r[2]:+.4f}"

    data_prompt = build_data_prompt(
        symbol=symbol,
        quote=quote,
        profile=profile,
        financials=financials,
        technicals=technicals,
        recommendations=recs,
        earnings=earnings,
        peers=peers,
        news=news,
    )

    report_placeholder = st.empty()
    report_text = ""

    try:
        with st.spinner("Claude is analyzing the data..."):
            for chunk in stream_fundamental_analysis(data_prompt):
                report_text += chunk
                report_placeholder.markdown(report_text)
    except ValueError as e:
        st.error(str(e))
    except Exception as e:
        st.error(f"Analysis failed: {e}")

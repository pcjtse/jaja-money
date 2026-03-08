"""jaja-money — Stock Analysis Dashboard

Main analysis page.  Integrates all enhancements:
- Multi-page tab UI via Streamlit pages/
- Bollinger Bands, Volume, OBV in price chart (P1.4)
- Export to CSV / HTML (P1.3)
- Watchlist save/load (P1.2)
- Historical factor score tracking (P2.2)
- Price alerts (P2.5)
- Options market data (P2.6)
- Earnings call transcript analysis (P2.3)
- Interactive AI Chat Q&A (P3.4)
- Structured logging (P4.3)
- Disk cache (P1.5)
- Config-driven weights (P4.5)
"""

import json
import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

from api import FinnhubAPI
from analyzer import (
    build_data_prompt,
    stream_fundamental_analysis,
    stream_sentiment_themes,
    stream_portfolio_memo,
    stream_transcript_analysis,
    stream_forward_looking_analysis,
    build_chat_system_prompt,
    stream_chat_response,
)
from sentiment import score_articles, aggregate_sentiment, SENTIMENT_COLOR, SENTIMENT_EMOJI
from factors import (
    compute_factors, composite_score, composite_label_color,
    calc_bollinger_bands, calc_obv, calc_vwap, calc_fibonacci_levels,
)
from guardrails import compute_risk
from portfolio import suggest_position, RISK_TOLERANCES, HORIZONS
from watchlist import (
    get_watchlist, add_to_watchlist, remove_from_watchlist, is_in_watchlist,
)
from history import save_analysis, get_score_trend, get_latest_two_snapshots
from alerts import (
    get_alerts, add_alert, check_alerts, delete_alert,
    CONDITION_TYPES, start_alert_scheduler, stop_alert_scheduler, is_scheduler_running,
)
from export import factors_to_csv, price_history_to_csv, analysis_to_html, analysis_to_pdf
from cache import get_cache
from log_setup import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="jaja-money — Stock Analysis",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Local technical indicator helpers
# ---------------------------------------------------------------------------

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


def calc_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    if len(series) < slow + signal:
        return None
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]


# ---------------------------------------------------------------------------
# Cached data fetchers (Streamlit session cache + disk cache)
# ---------------------------------------------------------------------------

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

@st.cache_data(ttl=900)
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

@st.cache_data(ttl=600)
def fetch_option_metrics(symbol: str) -> dict:
    return FinnhubAPI().get_option_metrics(symbol)

@st.cache_data(ttl=86400)
def fetch_transcripts_list(symbol: str) -> list:
    return FinnhubAPI().get_transcripts_list(symbol)

@st.cache_data(ttl=86400 * 7)
def fetch_transcript(tid: str) -> dict:
    return FinnhubAPI().get_transcript(tid)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📈 jaja-money")

    symbol = st.text_input("Stock Symbol", placeholder="e.g. AAPL").strip().upper()
    analyze = st.button("Analyze", type="primary", use_container_width=True)

    st.caption(
        "Finnhub free tier: 60 req/min. "
        "Results cached 5 min (memory) + disk."
    )
    st.divider()

    # Watchlist quick view
    st.subheader("Watchlist")
    wl = get_watchlist()
    if wl:
        for entry in wl:
            col1, col2 = st.columns([3, 1])
            fs = entry.get("factor_score")
            col1.write(f"**{entry['symbol']}** {f'· {fs}/100' if fs else ''}")
            if col2.button("▶", key=f"wl_load_{entry['symbol']}",
                           help=f"Load {entry['symbol']}"):
                st.session_state["symbol_override"] = entry["symbol"]
                st.rerun()
    else:
        st.caption("No symbols saved yet.")

    st.divider()

    # Alerts status
    st.subheader("Active Alerts")
    all_alerts = get_alerts()
    active = [a for a in all_alerts if a["status"] == "active"]
    triggered = [a for a in all_alerts if a["status"] == "triggered"]
    if triggered:
        for a in triggered[:3]:
            st.warning(f"🔔 **{a['symbol']}** — {a['condition']} {a['threshold']}")
    elif active:
        st.caption(f"{len(active)} alert(s) active")
    else:
        st.caption("No alerts configured.")

    st.divider()

    # Cache controls
    with st.expander("Cache & Settings"):
        cache = get_cache()
        stats = cache.stats()
        st.caption(f"Disk cache: {stats['entries']} entries, {stats['size_mb']} MB")
        if st.button("Clear Cache"):
            n = cache.clear()
            st.success(f"Cleared {n} cached entries.")
            st.cache_data.clear()

    # P4.5: Factor weight settings
    with st.expander("⚙️ Factor Weights"):
        from config import cfg
        current_weights = dict(cfg.factor_weights)
        weight_keys = [
            ("valuation", "Valuation (P/E)", 0.15),
            ("trend", "Trend (SMA)", 0.20),
            ("rsi", "Momentum (RSI)", 0.10),
            ("macd", "MACD Signal", 0.10),
            ("sentiment", "News Sentiment", 0.15),
            ("earnings", "Earnings Quality", 0.15),
            ("analyst", "Analyst Consensus", 0.10),
            ("range", "52-Wk Strength", 0.05),
        ]
        new_weights = {}
        for key, label, default in weight_keys:
            val = current_weights.get(key, default)
            new_weights[key] = st.slider(
                label, 0.0, 0.50, float(val), 0.05,
                key=f"wt_{key}",
            )
        # Normalize weights to sum to 1.0 and update cfg for this run
        total_w = sum(new_weights.values()) or 1.0
        cfg.factor_weights = {k: v / total_w for k, v in new_weights.items()}
        st.caption(f"Total weight: {total_w:.2f} (auto-normalised)")
        if st.button("Reset Weights"):
            for key, _, default in weight_keys:
                st.session_state[f"wt_{key}"] = default
            st.rerun()

    # P2.5: Background alert scheduler toggle
    with st.expander("🔔 Background Alerts"):
        running = is_scheduler_running()
        st.caption(f"Scheduler: {'🟢 Running' if running else '⚪ Stopped'}")
        ac1, ac2 = st.columns(2)
        if ac1.button("Start", disabled=running, key="start_sched"):
            ok = start_alert_scheduler(interval_seconds=300)
            st.success("Scheduler started." if ok else "APScheduler not installed.")
            st.rerun()
        if ac2.button("Stop", disabled=not running, key="stop_sched"):
            stop_alert_scheduler()
            st.rerun()
        st.caption("Checks cached quotes every 5 min. Sends desktop notification via plyer.")

# Handle watchlist quick-load
if "symbol_override" in st.session_state:
    symbol = st.session_state.pop("symbol_override")

# ---------------------------------------------------------------------------
# Main area gate
# ---------------------------------------------------------------------------

if not analyze and not symbol:
    st.title("📈 Stock Analysis Dashboard")
    st.info(
        "Enter a stock symbol in the sidebar and click **Analyze** to get started.\n\n"
        "Navigate to other pages using the sidebar menu for:\n"
        "- **Compare** — side-by-side multi-stock comparison\n"
        "- **Screener** — filter stocks by factor/risk criteria\n"
        "- **Portfolio** — correlation & portfolio risk analysis\n"
        "- **Sectors** — sector rotation tracker\n"
        "- **Backtest** — historical signal backtesting"
    )
    st.stop()

if not symbol:
    st.error("Please enter a stock symbol.")
    st.stop()

st.title(f"Analysis: {symbol}")
log.info("Running analysis for %s", symbol)

# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

try:
    with st.spinner("Fetching quote..."):
        quote = fetch_quote(symbol)
except Exception as e:
    st.error(f"Failed to fetch quote: {e}")
    log.error("Quote fetch failed for %s: %s", symbol, e)
    st.stop()

# --- Stock Quote ---
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
        mc_str = (f"${mc / 1_000_000:,.2f}T" if mc >= 1_000_000 else
                  f"${mc / 1_000:,.2f}B" if mc >= 1_000 else
                  f"${mc:,.2f}M")
    else:
        mc_str = "N/A"
    col2.metric("Market Cap", mc_str)
    col3.metric("P/E Ratio", f"{pe:.2f}" if pe is not None else "N/A")
    col4.metric("EPS", f"${eps:.2f}" if eps is not None else "N/A")

    col1, col2 = st.columns(2)
    col1.metric("Dividend Yield", f"{div_yield:.2f}%" if div_yield is not None else "N/A")
    col2.metric(
        "52-Week Range",
        f"${low_52:,.2f} – ${high_52:,.2f}" if (high_52 and low_52) else "N/A",
    )

    # Watchlist button
    in_wl = is_in_watchlist(symbol)
    wl_label = "Remove from Watchlist" if in_wl else "Add to Watchlist"
    if st.button(wl_label, key="wl_toggle"):
        if in_wl:
            remove_from_watchlist(symbol)
            st.success(f"Removed {symbol} from watchlist.")
        else:
            add_to_watchlist(symbol, name=name, price=price)
            st.success(f"Added {symbol} to watchlist.")
        st.rerun()

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
    volume = df["Volume"]

    tech_cols = st.columns(6)

    sma50 = calc_sma(close, 50)
    tech_cols[0].metric("SMA(50)", f"${sma50:,.2f}" if sma50 else "N/A")

    sma200 = calc_sma(close, 200)
    tech_cols[1].metric("SMA(200)", f"${sma200:,.2f}" if sma200 else "N/A")

    rsi_val = calc_rsi(close)
    if rsi_val is not None:
        rsi_label = ("Overbought" if rsi_val >= 70 else
                     "Oversold" if rsi_val <= 30 else "Neutral")
        tech_cols[2].metric("RSI(14)", f"{rsi_val:.2f}", rsi_label)
    else:
        tech_cols[2].metric("RSI(14)", "N/A")

    macd_result = calc_macd(close)
    if macd_result:
        macd_val, signal_val, hist_val = macd_result
        tech_cols[3].metric("MACD", f"{macd_val:.4f}")
        tech_cols[4].metric("Signal / Hist", f"{signal_val:.4f}", f"{hist_val:+.4f}")
    else:
        tech_cols[3].metric("MACD", "N/A")
        tech_cols[4].metric("Signal / Hist", "N/A")

    # P1.4: Bollinger Bands
    bb = calc_bollinger_bands(close, window=20, num_std=2.0)
    if bb:
        bb_label = ("Above upper" if price > bb["upper"] else
                    "Below lower" if price < bb["lower"] else "Inside bands")
        tech_cols[5].metric("BB %B", f"{bb['pct_b']:.2f}", bb_label)
    else:
        tech_cols[5].metric("BB %B", "N/A")

    # P1.4: VWAP
    vwap = calc_vwap(df)
    if vwap:
        vwap_delta = f"{((price - vwap) / vwap * 100):+.1f}% vs VWAP"
        st.caption(f"VWAP (20d): ${vwap:,.2f}   |   {vwap_delta}")

# --- Price Chart (P1.4: enhanced with BB + Volume + Fibonacci) ---
_price_chart_fig = None  # stored for PDF export
if df is not None and len(df) > 0:
    chart_df = df.tail(100).copy()
    close_s = chart_df["Close"]

    st.header("Price Chart (Last 100 Days)")

    show_bb = st.checkbox("Show Bollinger Bands", value=True, key="show_bb")
    show_smas = st.checkbox("Show SMA(50)/SMA(200)", value=True, key="show_smas")
    show_vol = st.checkbox("Show Volume", value=True, key="show_vol")
    show_obv = st.checkbox("Show OBV", value=False, key="show_obv")
    show_fib = st.checkbox("Show Fibonacci Retracement", value=False, key="show_fib")

    # Build subplot grid
    row_heights = [0.6]
    n_subplots = 1
    if show_vol:
        row_heights.append(0.2)
        n_subplots += 1
    if show_obv:
        row_heights.append(0.2)
        n_subplots += 1

    fig = make_subplots(
        rows=n_subplots, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=chart_df["Date"],
        open=chart_df["Open"],
        high=chart_df["High"],
        low=chart_df["Low"],
        close=chart_df["Close"],
        name="Price",
    ), row=1, col=1)

    # SMAs
    if show_smas:
        full_close = df["Close"]
        sma50_s = full_close.rolling(50).mean()
        sma200_s = full_close.rolling(200).mean()
        # Align to chart_df
        sma50_chart = sma50_s.tail(100)
        sma200_chart = sma200_s.tail(100)
        if sma50_chart.notna().any():
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=sma50_chart.values,
                name="SMA(50)", line=dict(color="#f0b429", width=1.5, dash="dot"),
            ), row=1, col=1)
        if sma200_chart.notna().any():
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=sma200_chart.values,
                name="SMA(200)", line=dict(color="#e05252", width=1.5, dash="dash"),
            ), row=1, col=1)

    # Bollinger Bands
    if show_bb and bb:
        bb_full = calc_bollinger_bands(df["Close"], window=20, num_std=2.0)
        if bb_full:
            upper_s = bb_full["upper_series"].tail(100)
            lower_s = bb_full["lower_series"].tail(100)
            mid_s = bb_full["middle_series"].tail(100)
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=upper_s.values,
                name="BB Upper", line=dict(color="rgba(99,110,250,0.5)", width=1),
            ), row=1, col=1)
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=lower_s.values,
                name="BB Lower", line=dict(color="rgba(99,110,250,0.5)", width=1),
                fill="tonexty", fillcolor="rgba(99,110,250,0.05)",
            ), row=1, col=1)

    current_row = 2

    # Volume subplot
    if show_vol:
        colors = ["#2da44e" if chart_df["Close"].iloc[i] >= chart_df["Open"].iloc[i]
                  else "#e05252" for i in range(len(chart_df))]
        fig.add_trace(go.Bar(
            x=chart_df["Date"], y=chart_df["Volume"],
            name="Volume", marker_color=colors, showlegend=True,
        ), row=current_row, col=1)
        fig.update_yaxes(title_text="Volume", row=current_row, col=1)
        current_row += 1

    # OBV subplot
    if show_obv:
        obv_series = calc_obv(df["Close"], df["Volume"])
        if obv_series is not None:
            obv_chart = obv_series.tail(100)
            fig.add_trace(go.Scatter(
                x=chart_df["Date"], y=obv_chart.values,
                name="OBV", line=dict(color="#6c63ff", width=1.5),
            ), row=current_row, col=1)
            fig.update_yaxes(title_text="OBV", row=current_row, col=1)

    # P1.4: Fibonacci retracement levels overlay
    if show_fib:
        fib_data = calc_fibonacci_levels(chart_df, lookback=100)
        if fib_data:
            fib_colors = {
                "100.0%": "#888888",
                "78.6%":  "#e05252",
                "61.8%":  "#f0b429",
                "50.0%":  "#2da44e",
                "38.2%":  "#f0b429",
                "23.6%":  "#e05252",
                "0.0%":   "#888888",
            }
            for label, level_price in fib_data["levels"].items():
                fig.add_hline(
                    y=level_price,
                    line_dash="dot",
                    line_color=fib_colors.get(label, "#aaa"),
                    line_width=1,
                    annotation_text=f"Fib {label} ${level_price:,.2f}",
                    annotation_position="right",
                    annotation_font_size=9,
                    row=1, col=1,
                )

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(t=20, b=10),
    )
    fig.update_xaxes(title_text="Date", row=n_subplots, col=1)
    fig.update_yaxes(title_text="Price (USD)", row=1, col=1)
    _price_chart_fig = fig
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("Raw Price Data"):
        st.dataframe(
            chart_df.set_index("Date").sort_index(ascending=False),
            use_container_width=True,
        )

    # Export buttons (P1.3)
    st.subheader("Export")
    ec1, ec2 = st.columns(2)
    with ec1:
        csv_bytes = price_history_to_csv(symbol, chart_df.set_index("Date"))
        st.download_button(
            "Download Price CSV",
            data=csv_bytes,
            file_name=f"{symbol}_prices.csv",
            mime="text/csv",
        )

# --- Market Research ---
st.header("Market Research")

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

    fig_rec = go.Figure(go.Bar(
        x=["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"],
        y=[strong_buy, buy, hold, sell, strong_sell],
        marker_color=["#1a7f37", "#2da44e", "#f0b429", "#e05252", "#cf2929"],
    ))
    fig_rec.update_layout(
        xaxis_title="Rating", yaxis_title="Number of Analysts",
        height=300, margin=dict(t=20),
    )
    st.plotly_chart(fig_rec, use_container_width=True)

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

try:
    with st.spinner("Fetching peer companies..."):
        peers = fetch_peers(symbol)
except Exception as e:
    peers = []

if peers:
    st.subheader("Peer Companies")
    peer_list = [p for p in peers if p != symbol]
    if peer_list:
        st.write(" · ".join(peer_list))

# P2.6: Options Market Data
st.subheader("Options Market Data")
try:
    with st.spinner("Fetching options data..."):
        opts = fetch_option_metrics(symbol)
    if opts.get("available"):
        opt_cols = st.columns(5)
        opt_cols[0].metric("Exp. Date", opts.get("expiry", "N/A"))
        pc = opts.get("put_call_ratio")
        opt_cols[1].metric(
            "Put/Call Ratio",
            f"{pc:.2f}" if pc else "N/A",
            "Bearish >1" if pc and pc > 1 else ("Bullish <1" if pc else None),
        )
        iv = opts.get("avg_iv_pct")
        opt_cols[2].metric("Avg IV", f"{iv:.1f}%" if iv else "N/A")
        opt_cols[3].metric(
            "Call Vol / Put Vol",
            f"{opts.get('total_call_volume', 0):,} / {opts.get('total_put_volume', 0):,}",
        )
        # P2.6: IV-based expected move (30-day horizon)
        if iv and price:
            import math as _math
            expected_move = price * (iv / 100) * _math.sqrt(30 / 365)
            opt_cols[4].metric(
                "Expected Move (30d)",
                f"±${expected_move:,.2f}",
                f"±{expected_move / price * 100:.1f}% of price",
            )
            em_upper = price + expected_move
            em_lower = price - expected_move
            fig_em = go.Figure()
            fig_em.add_trace(go.Scatter(
                x=["Lower bound", "Current price", "Upper bound"],
                y=[em_lower, price, em_upper],
                mode="markers+lines",
                marker=dict(size=[12, 16, 12],
                            color=["#e05252", "#2da44e", "#2da44e"]),
                line=dict(color="#888", width=1, dash="dot"),
                showlegend=False,
            ))
            fig_em.update_layout(
                height=180, margin=dict(t=10, b=10, l=10, r=10),
                yaxis_title="Price (USD)",
                xaxis=dict(tickfont=dict(size=11)),
            )
            st.plotly_chart(fig_em, use_container_width=True)
    else:
        st.caption("Options data unavailable for this symbol (may require Finnhub premium tier).")
except Exception as e:
    st.caption(f"Options data could not be fetched: {e}")

# --- News Sentiment ---
scores = []
agg = None

try:
    with st.spinner("Fetching recent news..."):
        news = fetch_news(symbol)
except Exception as e:
    news = []
    st.warning(f"Could not fetch news: {e}")

if news:
    st.subheader("News Sentiment Scan")
    displayed = news[:10]

    with st.spinner("Scoring sentiment with FinBERT..."):
        scores = score_articles(displayed)
    agg = aggregate_sentiment(scores)

    signal = agg["signal"]
    net = agg["net_score"]
    counts = agg["counts"]

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
            textinfo="label+percent", showlegend=False,
        ))
        fig_donut.update_layout(height=200, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_donut, use_container_width=True)

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

    st.divider()
    run_themes = st.button("Analyze Sentiment Themes with Claude")
    if run_themes:
        themes_placeholder = st.empty()
        themes_text = ""
        try:
            with st.spinner("Claude is synthesizing news themes..."):
                for chunk in stream_sentiment_themes(symbol, displayed, scores, agg):
                    themes_text += chunk
                    themes_placeholder.markdown(themes_text)
        except Exception as e:
            st.error(f"Theme analysis failed: {e}")

# P2.3: Earnings Call Transcript Analysis
st.divider()
st.subheader("Earnings Call Transcript Analysis")
try:
    transcripts = fetch_transcripts_list(symbol)
    if transcripts:
        t_options = {
            f"{t.get('year', '')} Q{t.get('quarter', '')} — {t.get('id', '')}": t.get("id")
            for t in transcripts[:5]
        }
        selected_t = st.selectbox("Select Transcript", list(t_options.keys()))
        if st.button("Analyze Transcript with Claude"):
            tid = t_options[selected_t]
            with st.spinner("Fetching transcript..."):
                transcript_data = fetch_transcript(tid)
            content = transcript_data.get("transcript", "")
            if not content:
                # Try to extract from speech array
                speeches = transcript_data.get("participant", [])
                parts = []
                for p in speeches:
                    name = p.get("name", "Unknown")
                    for s in p.get("speech", []):
                        parts.append(f"**{name}:** {s}")
                content = "\n\n".join(parts)

            if content:
                t_placeholder = st.empty()
                t_text = ""
                for chunk in stream_transcript_analysis(symbol, content):
                    t_text += chunk
                    t_placeholder.markdown(t_text)

                # P2.3 extension: Forward-looking statements
                if st.button("Extract Forward-Looking Statements", key="fwd_btn"):
                    fl_placeholder = st.empty()
                    fl_text = ""
                    try:
                        with st.spinner("Extracting forward-looking statements..."):
                            for chunk in stream_forward_looking_analysis(symbol, content):
                                fl_text += chunk
                                fl_placeholder.markdown(fl_text)
                    except Exception as e:
                        st.error(f"Forward-looking analysis failed: {e}")
            else:
                st.warning("Transcript content not available.")
    else:
        st.caption("No earnings call transcripts available for this symbol.")
except Exception as e:
    st.caption(f"Transcript data unavailable: {e}")

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
    _names_closed  = _names + [_names[0]]
    _scores_closed = _scores + [_scores[0]]
    fig_radar = go.Figure(go.Scatterpolar(
        r=_scores_closed, theta=_names_closed,
        fill="toself", fillcolor="rgba(45,164,78,0.15)",
        line=dict(color="#2da44e", width=2), name="Factor Scores",
    ))
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9)),
            angularaxis=dict(tickfont=dict(size=10)),
        ),
        showlegend=False, height=280, margin=dict(t=20, b=20, l=40, r=40),
    )
    st.plotly_chart(fig_radar, use_container_width=True)

_rows = []
for f in _factors:
    score = f["score"]
    bar = ("🟢🟢🟢🟢" if score >= 70 else
           "🟢🟢🟢⚪" if score >= 55 else
           "🟡🟡⚪⚪" if score >= 45 else
           "🔴🔴⚪⚪" if score >= 30 else "🔴🔴🔴🔴")
    _rows.append({
        "Factor": f["name"], "Score": score,
        "Signal": bar, "Label": f["label"],
        "Detail": f["detail"], "Weight": f"{f['weight']:.0%}",
    })

st.dataframe(
    pd.DataFrame(_rows), use_container_width=True, hide_index=True,
    column_config={
        "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        "Signal": st.column_config.TextColumn("Signal", width="small"),
    },
)

# --- Risk Guardrails ---
st.divider()
st.header("Risk Guardrails")
st.caption(
    "Four risk dimensions — volatility, drawdown, signal strength, and red-flag count — "
    "combined into a single risk score."
)

_risk = compute_risk(
    quote=quote, financials=financials, close=_close,
    earnings=_earnings_for_factors, recommendations=_recs_for_factors,
    sentiment_agg=agg, composite_factor_score=_composite,
)

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
            "axis": {"range": [0, 100]},
            "bar": {"color": _rcolor, "thickness": 0.3},
            "bgcolor": "white",
            "steps": [
                {"range": [0,  25], "color": "#c3e6cb"},
                {"range": [25, 45], "color": "#d4edda"},
                {"range": [45, 65], "color": "#fef3cd"},
                {"range": [65, 80], "color": "#fde8e8"},
                {"range": [80, 100], "color": "#f5c6cb"},
            ],
            "threshold": {"line": {"color": _rcolor, "width": 4}, "thickness": 0.75, "value": _rscore},
        },
    ))
    fig_risk_gauge.update_layout(height=260, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(fig_risk_gauge, use_container_width=True)

with risk_meta_col:
    _hv = _risk.get("hv")
    _dd = _risk.get("drawdown_pct")
    m1, m2 = st.columns(2)
    m1.metric("Annualised Volatility (20d)", f"{_hv:.1f}%" if _hv is not None else "N/A")
    m2.metric("Drawdown from 52-Wk High", f"{_dd:.1f}%" if _dd is not None else "N/A")
    m1.metric("Active Risk Flags", len(_risk["flags"]))
    m2.metric("Factor Score (context)", f"{_composite} / 100")

_flags = _risk["flags"]
if not _flags:
    st.success("No risk flags triggered.")
else:
    for _f in _flags:
        _body = f"**{_f['icon']} {_f['title']}** — {_f['message']}"
        if _f["severity"] == "danger":
            st.error(_body)
        elif _f["severity"] == "warning":
            st.warning(_body)
        else:
            st.info(_body)

# P2.2: Historical Factor Score Tracking
st.subheader("Historical Factor Score Trend")
save_analysis(
    symbol=symbol,
    price=price,
    factor_score=_composite,
    risk_score=_rscore,
    composite_label=_label,
    risk_level=_rlabel,
    factors=_factors,
    flags=_flags,
)

trend = get_score_trend(symbol, limit=30)
if len(trend["dates"]) > 1:
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=trend["dates"], y=trend["factor_scores"],
        name="Factor Score", line=dict(color="#2da44e", width=2),
    ))
    fig_trend.add_trace(go.Scatter(
        x=trend["dates"], y=trend["risk_scores"],
        name="Risk Score", line=dict(color="#e05252", width=2, dash="dot"),
    ))
    fig_trend.update_layout(
        height=200, margin=dict(t=10, b=10, l=10, r=10),
        yaxis=dict(range=[0, 100]),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.caption("Run analysis on multiple days to see the score trend chart.")

# P2.2: Compare to previous analysis diff view
_snapshots = get_latest_two_snapshots(symbol)
if len(_snapshots) == 2:
    with st.expander("Compare to Previous Analysis"):
        _prev, _curr = _snapshots[0], _snapshots[1]
        dc1, dc2, dc3 = st.columns(3)
        _fs_delta = _curr["factor_score"] - _prev["factor_score"]
        _rs_delta = _curr["risk_score"] - _prev["risk_score"]
        dc1.metric("Factor Score",
                   f"{_curr['factor_score']}/100 ({_curr['composite_label']})",
                   f"{_fs_delta:+d} vs {_prev['date']}")
        dc2.metric("Risk Score",
                   f"{_curr['risk_score']}/100 ({_curr['risk_level']})",
                   f"{_rs_delta:+d} vs {_prev['date']}")
        dc3.metric("Price", f"${_curr['price']:,.2f}" if _curr.get("price") else "N/A")

        _prev_flags = {f["title"] for f in (json.loads(_prev.get("flags_json") or "[]"))}
        _curr_flags = {f["title"] for f in (json.loads(_curr.get("flags_json") or "[]"))}
        _new_flags = _curr_flags - _prev_flags
        _removed_flags = _prev_flags - _curr_flags
        if _new_flags:
            st.warning("**New flags since last analysis:** " + " · ".join(_new_flags))
        if _removed_flags:
            st.success("**Resolved flags:** " + " · ".join(_removed_flags))
        if not _new_flags and not _removed_flags:
            st.info("No flag changes since previous analysis.")

# P2.5: Price Alerts configuration
with st.expander("Configure Price Alert"):
    a_col1, a_col2, a_col3 = st.columns(3)
    a_cond = a_col1.selectbox("Condition", CONDITION_TYPES, key="alert_cond")
    a_thresh = a_col2.number_input("Threshold", value=float(price), key="alert_thresh")
    a_note = a_col3.text_input("Note (optional)", key="alert_note")
    if st.button("Add Alert", key="add_alert_btn"):
        add_alert(symbol, a_cond, a_thresh, a_note)
        st.success(f"Alert added: {symbol} {a_cond} {a_thresh}")

    # Show existing alerts for this symbol
    sym_alerts = get_alerts(symbol)
    if sym_alerts:
        st.caption("Existing alerts:")
        for a in sym_alerts:
            col_a, col_b = st.columns([4, 1])
            col_a.write(f"{'🟢' if a['status'] == 'active' else '🔔'} "
                        f"{a['condition']} {a['threshold']}  ·  {a['note']}")
            if col_b.button("Delete", key=f"del_alert_{a['id']}"):
                delete_alert(a["id"])
                st.rerun()

# Check alerts now
triggered_alerts = check_alerts(symbol, price, _composite, _rscore)
for ta in triggered_alerts:
    st.toast(f"Alert triggered: {ta['symbol']} {ta['condition']} {ta['threshold']}",
             icon="🔔")

# --- Portfolio Construction ---
st.divider()
st.header("Portfolio Construction")

_pt_col, _ph_col = st.columns(2)
_risk_tolerance = _pt_col.selectbox("Risk Tolerance", RISK_TOLERANCES, index=1)
_horizon = _ph_col.selectbox("Investment Horizon", HORIZONS, index=1)

_suggestion = suggest_position(
    risk_tolerance=_risk_tolerance,
    horizon=_horizon,
    composite_factor=_composite,
    risk_score=_risk["risk_score"],
    quote=quote,
    close=_close,
)

st.markdown(
    f'<div style="background:{_suggestion["action_color"]}22;border-left:4px solid '
    f'{_suggestion["action_color"]};padding:10px 16px;border-radius:4px;margin:8px 0">'
    f'<span style="font-size:1.3rem;font-weight:700;color:{_suggestion["action_color"]}">'
    f'{_suggestion["action"]}</span>'
    f'<span style="margin-left:12px;color:#555">{_risk_tolerance} · {_horizon}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

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

st.info(f"**Entry Strategy:** {_suggestion['entry_strategy']}")

with st.expander("Rule-engine rationale"):
    for _r in _suggestion["rationale"]:
        st.markdown(f"- {_r}")

st.divider()
_run_memo = st.button("Generate Portfolio Memo with Claude")
if _run_memo:
    _memo_placeholder = st.empty()
    _memo_text = ""
    try:
        with st.spinner("Claude is writing your portfolio memo..."):
            for _chunk in stream_portfolio_memo(
                symbol=symbol, suggestion=_suggestion, factors=_factors,
                risk=_risk, profile=profile, risk_tolerance=_risk_tolerance,
                horizon=_horizon,
            ):
                _memo_text += _chunk
                _memo_placeholder.markdown(_memo_text)
    except Exception as e:
        st.error(f"Portfolio memo failed: {e}")

# --- Fundamental Analyzer ---
st.divider()
st.header("Fundamental Analyzer")
st.caption("Powered by Claude Opus 4.6 with adaptive thinking.")

run_analysis = st.button("Run Fundamental Analysis", type="primary")

if run_analysis:
    technicals: dict = {}
    if df is not None and len(df) > 0:
        close = df["Close"]
        sma50_v = calc_sma(close, 50)
        sma200_v = calc_sma(close, 200)
        rsi_v = calc_rsi(close)
        macd_r = calc_macd(close)
        bb_v = calc_bollinger_bands(close)

        technicals["sma50"] = f"${sma50_v:,.2f}" if sma50_v else "N/A"
        technicals["sma200"] = f"${sma200_v:,.2f}" if sma200_v else "N/A"
        technicals["rsi"] = f"{rsi_v:.2f}" if rsi_v else "N/A"
        if macd_r:
            technicals["macd"] = f"{macd_r[0]:.4f}"
            technicals["macd_signal"] = f"{macd_r[1]:.4f}"
            technicals["macd_hist"] = f"{macd_r[2]:+.4f}"
        if bb_v:
            technicals["bb_upper"] = f"${bb_v['upper']:,.2f}"
            technicals["bb_lower"] = f"${bb_v['lower']:,.2f}"
            technicals["bb_pct_b"] = f"{bb_v['pct_b']:.3f}"

    data_prompt = build_data_prompt(
        symbol=symbol, quote=quote, profile=profile,
        financials=financials, technicals=technicals,
        recommendations=recs, earnings=earnings,
        peers=peers, news=news,
    )

    report_placeholder = st.empty()
    report_text = ""
    try:
        with st.spinner("Claude is analyzing..."):
            for chunk in stream_fundamental_analysis(data_prompt):
                report_text += chunk
                report_placeholder.markdown(report_text)
    except Exception as e:
        st.error(f"Analysis failed: {e}")

# Export full report (P1.3)
st.divider()
st.subheader("Download Full Report")
exp_col1, exp_col2, exp_col3 = st.columns(3)
with exp_col1:
    csv_data = factors_to_csv(symbol, _factors, _risk, quote, financials)
    st.download_button(
        "Download Analysis CSV",
        data=csv_data,
        file_name=f"{symbol}_analysis.csv",
        mime="text/csv",
    )
with exp_col2:
    html_data = analysis_to_html(
        symbol=symbol, quote=quote, profile=profile,
        financials=financials, factors=_factors, risk=_risk,
        composite_score=_composite, composite_label=_label,
    )
    st.download_button(
        "Download HTML Report",
        data=html_data,
        file_name=f"{symbol}_report.html",
        mime="text/html",
    )
with exp_col3:
    # P1.3: PDF export (requires reportlab; chart image requires kaleido)
    _chart_bytes = None
    try:
        if _price_chart_fig is not None:
            import plotly.io as _pio
            _chart_bytes = _pio.to_image(
                _price_chart_fig, format="png", width=1200, height=500, engine="kaleido"
            )
    except Exception:
        pass  # kaleido not installed or export failed
    try:
        pdf_data = analysis_to_pdf(
            symbol=symbol, quote=quote, profile=profile,
            financials=financials, factors=_factors, risk=_risk,
            composite_score=_composite, composite_label=_label,
            chart_image_bytes=_chart_bytes,
        )
        st.download_button(
            "Download PDF Report",
            data=pdf_data,
            file_name=f"{symbol}_report.pdf",
            mime="application/pdf",
        )
    except RuntimeError as _pdf_err:
        st.caption(f"PDF unavailable: {_pdf_err}")

# --- P3.4: Interactive AI Chat ---
st.divider()
st.header("AI Chat — Ask About This Stock")
st.caption("Ask questions about this stock based on the analysis data above.")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "chat_symbol" not in st.session_state:
    st.session_state.chat_symbol = ""

# Reset chat history when symbol changes
if st.session_state.chat_symbol != symbol:
    st.session_state.chat_history = []
    st.session_state.chat_symbol = symbol

# Build system prompt with current analysis context
_chat_system = build_chat_system_prompt(
    symbol=symbol, profile=profile, quote=quote,
    financials=financials, factors=_factors, risk=_risk,
    composite_score=_composite, composite_label=_label,
)

# Display history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if user_q := st.chat_input(f"Ask about {symbol}..."):
    st.session_state.chat_history.append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant"):
        resp_placeholder = st.empty()
        resp_text = ""
        try:
            for chunk in stream_chat_response(
                _chat_system,
                st.session_state.chat_history[:-1],  # exclude current user msg
                user_q,
            ):
                resp_text += chunk
                resp_placeholder.markdown(resp_text)
            st.session_state.chat_history.append(
                {"role": "assistant", "content": resp_text}
            )
        except Exception as e:
            st.error(f"Chat failed: {e}")

if st.button("Clear Chat History"):
    st.session_state.chat_history = []
    st.rerun()

# Store analysis in session state for other pages
st.session_state["last_analysis"] = {
    "symbol": symbol,
    "quote": quote,
    "profile": profile,
    "financials": financials,
    "factors": _factors,
    "risk": _risk,
    "composite": _composite,
    "label": _label,
    "color": _color,
}
log.info("Analysis complete for %s: factor=%d risk=%d", symbol, _composite, _rscore)

# P4.3: Developer debug panel (hidden behind DEBUG env flag)
if os.getenv("DEBUG", "").lower() in ("1", "true", "yes"):
    st.divider()
    with st.expander("🔧 Developer Debug Panel"):
        import pathlib as _pathlib
        _log_file = _pathlib.Path.home() / ".jaja-money" / "jaja_money.log"
        if _log_file.exists():
            _log_lines = _log_file.read_text(errors="replace").splitlines()
            st.code("\n".join(_log_lines[-60:]), language="text")
        else:
            st.caption("Log file not found.")
        with st.expander("Session State"):
            st.json({k: str(v)[:200] for k, v in st.session_state.items()})

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
from api import FinnhubAPI


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
    return rsi.iloc[-1]


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

# Recent News
try:
    with st.spinner("Fetching recent news..."):
        news = fetch_news(symbol)
except Exception as e:
    news = []
    st.warning(f"Could not fetch news: {e}")

if news:
    st.subheader("Recent News")
    displayed = news[:10]
    for article in displayed:
        headline = article.get("headline", "No title")
        url = article.get("url", "")
        source = article.get("source", "")
        ts = article.get("datetime", 0)
        date_str = datetime.fromtimestamp(ts).strftime("%b %d, %Y") if ts else ""
        summary = article.get("summary", "")

        with st.expander(f"{date_str}  |  {headline}"):
            if summary:
                st.write(summary)
            col_src, col_link = st.columns([2, 1])
            col_src.caption(f"Source: {source}")
            if url:
                col_link.markdown(f"[Read article]({url})")

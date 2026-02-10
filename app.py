import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from api import AlphaVantageAPI

st.set_page_config(page_title="Stock Analysis", page_icon="📈", layout="wide")

# --- Cached data fetchers ---

@st.cache_data(ttl=300)
def fetch_quote(symbol: str) -> dict:
    return AlphaVantageAPI().get_quote(symbol)

@st.cache_data(ttl=300)
def fetch_overview(symbol: str) -> dict:
    return AlphaVantageAPI().get_overview(symbol)

@st.cache_data(ttl=300)
def fetch_sma(symbol: str, period: int) -> dict:
    return AlphaVantageAPI().get_sma(symbol, period)

@st.cache_data(ttl=300)
def fetch_rsi(symbol: str) -> dict:
    return AlphaVantageAPI().get_rsi(symbol)

@st.cache_data(ttl=300)
def fetch_macd(symbol: str) -> dict:
    return AlphaVantageAPI().get_macd(symbol)

@st.cache_data(ttl=300)
def fetch_daily(symbol: str) -> dict:
    return AlphaVantageAPI().get_daily(symbol)


# --- Sidebar ---

with st.sidebar:
    st.header("Stock Analysis")
    symbol = st.text_input("Stock Symbol", placeholder="e.g. AAPL").strip().upper()
    analyze = st.button("Analyze", type="primary", use_container_width=True)
    st.caption(
        "Free Alpha Vantage tier: 25 requests/day, 5/min. "
        "Each analysis uses ~7 API calls. Results are cached for 5 minutes."
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

price = float(quote.get("05. price", 0))
change = float(quote.get("09. change", 0))
change_pct = quote.get("10. change percent", "0%").rstrip("%")
volume = int(quote.get("06. volume", 0))
prev_close = float(quote.get("08. previous close", 0))
high = float(quote.get("03. high", 0))
low = float(quote.get("04. low", 0))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Price", f"${price:,.2f}", f"{change:+.2f} ({change_pct}%)")
col2.metric("Volume", f"{volume:,}")
col3.metric("Day Range", f"${low:,.2f} – ${high:,.2f}")
col4.metric("Previous Close", f"${prev_close:,.2f}")

# --- Company Overview ---

try:
    with st.spinner("Fetching company overview..."):
        overview = fetch_overview(symbol)
except Exception as e:
    st.warning(f"Could not fetch company overview: {e}")
    overview = None

if overview:
    st.header("Company Overview")

    name = overview.get("Name", symbol)
    sector = overview.get("Sector", "N/A")
    industry = overview.get("Industry", "N/A")
    market_cap = overview.get("MarketCapitalization", "N/A")
    pe = overview.get("PERatio", "N/A")
    eps = overview.get("EPS", "N/A")
    div_yield = overview.get("DividendYield", "N/A")
    high_52 = overview.get("52WeekHigh", "N/A")
    low_52 = overview.get("52WeekLow", "N/A")
    description = overview.get("Description", "")

    st.subheader(name)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Sector", sector)
    col2.metric("Industry", industry)

    if market_cap not in ("N/A", "None", None):
        mc = int(market_cap)
        if mc >= 1_000_000_000_000:
            mc_str = f"${mc / 1_000_000_000_000:,.2f}T"
        elif mc >= 1_000_000_000:
            mc_str = f"${mc / 1_000_000_000:,.2f}B"
        elif mc >= 1_000_000:
            mc_str = f"${mc / 1_000_000:,.2f}M"
        else:
            mc_str = f"${mc:,}"
    else:
        mc_str = "N/A"
    col3.metric("Market Cap", mc_str)

    if div_yield not in ("N/A", "None", "0", None):
        div_str = f"{float(div_yield) * 100:.2f}%"
    else:
        div_str = "N/A"
    col4.metric("Dividend Yield", div_str)

    col1, col2, col3 = st.columns(3)
    col1.metric("P/E Ratio", pe)
    col2.metric("EPS", f"${eps}" if eps not in ("N/A", "None", None) else "N/A")
    col3.metric("52-Week Range", f"${low_52} – ${high_52}")

    if description and description != "None":
        with st.expander("Company Description"):
            st.write(description)

# --- Technical Indicators ---

st.header("Technical Indicators")

tech_cols = st.columns(5)
indicators = {}

try:
    with st.spinner("Fetching SMA(50)..."):
        sma50 = fetch_sma(symbol, 50)
    indicators["SMA(50)"] = sma50["value"]
    tech_cols[0].metric("SMA(50)", f"${sma50['value']:,.2f}")
except Exception as e:
    tech_cols[0].metric("SMA(50)", "N/A")
    st.caption(f"SMA(50) error: {e}")

try:
    with st.spinner("Fetching SMA(200)..."):
        sma200 = fetch_sma(symbol, 200)
    indicators["SMA(200)"] = sma200["value"]
    tech_cols[1].metric("SMA(200)", f"${sma200['value']:,.2f}")
except Exception as e:
    tech_cols[1].metric("SMA(200)", "N/A")
    st.caption(f"SMA(200) error: {e}")

try:
    with st.spinner("Fetching RSI(14)..."):
        rsi = fetch_rsi(symbol)
    indicators["RSI(14)"] = rsi["value"]
    rsi_val = rsi["value"]
    if rsi_val >= 70:
        rsi_label = "Overbought"
    elif rsi_val <= 30:
        rsi_label = "Oversold"
    else:
        rsi_label = "Neutral"
    tech_cols[2].metric("RSI(14)", f"{rsi_val:.2f}", rsi_label)
except Exception as e:
    tech_cols[2].metric("RSI(14)", "N/A")
    st.caption(f"RSI error: {e}")

try:
    with st.spinner("Fetching MACD..."):
        macd = fetch_macd(symbol)
    tech_cols[3].metric("MACD", f"{macd['macd']:.4f}")
    tech_cols[4].metric("Signal / Histogram", f"{macd['signal']:.4f}", f"{macd['histogram']:+.4f}")
except Exception as e:
    tech_cols[3].metric("MACD", "N/A")
    tech_cols[4].metric("Signal / Histogram", "N/A")
    st.caption(f"MACD error: {e}")

# --- Price Chart ---

st.header("Price Chart (Last 100 Days)")

try:
    with st.spinner("Fetching daily prices..."):
        daily = fetch_daily(symbol)

    dates = sorted(daily.keys())[-100:]
    df = pd.DataFrame([
        {
            "Date": d,
            "Open": float(daily[d]["1. open"]),
            "High": float(daily[d]["2. high"]),
            "Low": float(daily[d]["3. low"]),
            "Close": float(daily[d]["4. close"]),
            "Volume": int(daily[d]["5. volume"]),
        }
        for d in dates
    ])
    df["Date"] = pd.to_datetime(df["Date"])

    fig = go.Figure(data=[
        go.Candlestick(
            x=df["Date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
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
        st.dataframe(df.set_index("Date").sort_index(ascending=False), use_container_width=True)

except Exception as e:
    st.error(f"Could not load price chart: {e}")

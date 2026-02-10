# Stock Analysis Dashboard

A Streamlit-based stock analysis app powered by the Finnhub API. Enter a stock symbol to view real-time quotes, company fundamentals, technical indicators, and an interactive price chart.

![Screenshot](screenshot.png)

## Features

- **Stock Quote** — Current price, change, day high/low, previous close
- **Company Overview** — Name, sector, market cap, P/E, EPS, dividend yield, 52-week range
- **Technical Indicators** — SMA(50), SMA(200), RSI(14), MACD with signal and histogram (computed locally from price data)
- **Price Chart** — Interactive candlestick chart of the last 100 trading days (Plotly)
- **Caching** — API responses cached for 5 minutes to reduce API usage

## Prerequisites

- Python 3.8+
- A free Finnhub API key

## Setup

1. Clone the repository and navigate to the project directory:

   ```bash
   cd jaja-money
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate        # macOS / Linux
   # venv\Scripts\activate          # Windows
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Get a free API key from [Finnhub](https://finnhub.io).

5. Create a `.env` file from the example and add your key:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and replace `your_api_key_here` with your actual API key.

## Usage

```bash
streamlit run app.py
```

Open the URL shown in the terminal (typically `http://localhost:8501`). Enter a stock symbol (e.g. `AAPL`) in the sidebar and click **Analyze**.

## Rate Limits

The free Finnhub plan allows **60 requests per minute** with no daily cap. Each full analysis uses approximately 4 API calls (quote, profile, financials, daily candles). Technical indicators are computed locally from the daily price data using `pandas-ta`, so they require no additional API calls. Results are cached for 5 minutes, so repeated lookups of the same symbol within that window cost 0 additional calls.

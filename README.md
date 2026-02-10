# Stock Analysis Dashboard

A Streamlit-based stock analysis app powered by the Alpha Vantage API. Enter a stock symbol to view real-time quotes, company fundamentals, technical indicators, and an interactive price chart.

![Screenshot](screenshot.PNG)

## Features

- **Stock Quote** — Current price, change, volume, day range, previous close
- **Company Overview** — Name, sector, industry, market cap, P/E, EPS, dividend yield, 52-week range, description
- **Technical Indicators** — SMA(50), SMA(200), RSI(14), MACD with signal and histogram
- **Price Chart** — Interactive candlestick chart of the last 100 trading days (Plotly)
- **Caching** — API responses cached for 5 minutes to reduce API usage

## Prerequisites

- Python 3.8+
- A free Alpha Vantage API key

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

4. Get a free API key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key).

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

## Free Tier Limitations

The free Alpha Vantage plan allows:

- **25 requests per day**
- **5 requests per minute**

Each full analysis uses approximately 7 API calls (quote, overview, SMA x2, RSI, MACD, daily prices). Results are cached for 5 minutes, so repeated lookups of the same symbol within that window cost 0 additional calls.

import os
import time
import finnhub
from dotenv import load_dotenv

load_dotenv()


class FinnhubAPI:
    def __init__(self):
        api_key = os.getenv("FINNHUB_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise ValueError(
                "FINNHUB_API_KEY not set. "
                "Copy .env.example to .env and add your API key."
            )
        self.client = finnhub.Client(api_key=api_key)

    def get_quote(self, symbol: str) -> dict:
        """Return real-time quote with keys: c, d, dp, h, l, o, pc, t."""
        data = self.client.quote(symbol)
        if not data or data.get("c") is None or data.get("c") == 0:
            raise ValueError(f"No quote data found for symbol '{symbol}'.")
        return data

    def get_profile(self, symbol: str) -> dict:
        """Return company profile: name, finnhubIndustry, logo, etc."""
        data = self.client.company_profile2(symbol=symbol)
        if not data or not data.get("name"):
            raise ValueError(f"No profile data found for symbol '{symbol}'.")
        return data

    def get_financials(self, symbol: str) -> dict:
        """Return basic financials (metric key has P/E, EPS, market cap, etc.)."""
        data = self.client.company_basic_financials(symbol, "all")
        if not data or not data.get("metric"):
            raise ValueError(f"No financial data found for symbol '{symbol}'.")
        return data["metric"]

    def get_daily(self, symbol: str, years: int = 2) -> dict:
        """Return daily candles for the last `years` years.

        Returns dict with keys: c, h, l, o, s, t, v (arrays).
        """
        to_ts = int(time.time())
        from_ts = to_ts - (years * 365 * 24 * 60 * 60)
        data = self.client.stock_candles(symbol, "D", from_ts, to_ts)
        if not data or data.get("s") != "ok":
            raise ValueError(f"No daily price data found for symbol '{symbol}'.")
        return data

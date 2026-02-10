import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageAPI:
    def __init__(self):
        self.api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError(
                "ALPHA_VANTAGE_API_KEY not set. "
                "Copy .env.example to .env and add your API key."
            )

    def _request(self, params: dict) -> dict:
        params["apikey"] = self.api_key
        resp = requests.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "Error Message" in data:
            raise ValueError(data["Error Message"])
        if "Note" in data:
            raise RuntimeError(
                "API rate limit reached. "
                "Free tier allows 25 requests/day and 5 requests/minute."
            )
        if "Information" in data:
            raise RuntimeError(data["Information"])

        return data

    def get_quote(self, symbol: str) -> dict:
        data = self._request({
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
        })
        quote = data.get("Global Quote", {})
        if not quote:
            raise ValueError(f"No quote data found for symbol '{symbol}'.")
        return quote

    def get_overview(self, symbol: str) -> dict:
        data = self._request({
            "function": "OVERVIEW",
            "symbol": symbol,
        })
        if not data or data.get("Symbol") is None:
            raise ValueError(f"No overview data found for symbol '{symbol}'.")
        return data

    def get_sma(self, symbol: str, period: int = 50) -> dict:
        data = self._request({
            "function": "SMA",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
            "series_type": "close",
        })
        analysis = data.get("Technical Analysis: SMA", {})
        if not analysis:
            raise ValueError(f"No SMA data found for symbol '{symbol}'.")
        latest_date = next(iter(analysis))
        return {"date": latest_date, "value": float(analysis[latest_date]["SMA"])}

    def get_rsi(self, symbol: str, period: int = 14) -> dict:
        data = self._request({
            "function": "RSI",
            "symbol": symbol,
            "interval": "daily",
            "time_period": str(period),
            "series_type": "close",
        })
        analysis = data.get("Technical Analysis: RSI", {})
        if not analysis:
            raise ValueError(f"No RSI data found for symbol '{symbol}'.")
        latest_date = next(iter(analysis))
        return {"date": latest_date, "value": float(analysis[latest_date]["RSI"])}

    def get_macd(self, symbol: str) -> dict:
        data = self._request({
            "function": "MACD",
            "symbol": symbol,
            "interval": "daily",
            "series_type": "close",
        })
        analysis = data.get("Technical Analysis: MACD", {})
        if not analysis:
            raise ValueError(f"No MACD data found for symbol '{symbol}'.")
        latest_date = next(iter(analysis))
        entry = analysis[latest_date]
        return {
            "date": latest_date,
            "macd": float(entry["MACD"]),
            "signal": float(entry["MACD_Signal"]),
            "histogram": float(entry["MACD_Hist"]),
        }

    def get_daily(self, symbol: str) -> dict:
        data = self._request({
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "outputsize": "compact",
        })
        series = data.get("Time Series (Daily)", {})
        if not series:
            raise ValueError(f"No daily price data found for symbol '{symbol}'.")
        return series

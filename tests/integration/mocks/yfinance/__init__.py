"""Fake yfinance module for integration tests."""

from __future__ import annotations


class _MockTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.info = {
            "shortPercentOfFloat": 0.025,
            "sharesShort": 80_000_000,
            "averageVolume": 50_000_000,
            "longName": f"{symbol} Corporation",
        }

    def history(self, period: str = "1y", interval: str = "1d"):
        import pandas as pd
        import numpy as np

        n = 252
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="B")
        np.random.seed(hash(self.symbol) % 2**32)
        prices = 150 + np.cumsum(np.random.randn(n) * 2)
        prices = np.maximum(prices, 10)
        return pd.DataFrame(
            {
                "Open": prices * 0.99,
                "High": prices * 1.02,
                "Low": prices * 0.98,
                "Close": prices,
                "Volume": np.random.randint(10_000_000, 50_000_000, n),
            },
            index=dates,
        )


class _MockDownloadResult:
    """Mock result from yf.download."""

    def __init__(self):
        import pandas as pd

        n = 5
        dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="B")
        self.empty = False
        self._df = pd.DataFrame(
            {
                ("Close", "^VIX"): [18.5] * n,
                ("Close", "^IRX"): [52.0] * n,
                ("Close", "^TNX"): [43.0] * n,
                ("Close", "^TYX"): [48.0] * n,
            },
            index=dates,
        )
        self._df.columns = pd.MultiIndex.from_tuples(self._df.columns)

    def __getitem__(self, key):
        return self._df[key]

    def __contains__(self, key):
        return key in self._df


def Ticker(symbol: str) -> _MockTicker:
    return _MockTicker(symbol)


def download(
    tickers, period: str = "5d", progress: bool = True, auto_adjust: bool = True
):
    return _MockDownloadResult()

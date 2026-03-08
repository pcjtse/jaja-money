"""Portfolio-Level Risk & Correlation Analysis (P2.4).

Computes portfolio metrics for a multi-stock portfolio including:
- Correlation matrix from daily returns
- Portfolio-level beta, volatility, and weighted factor score
- Expected portfolio return based on factor scores

Usage:
    from portfolio_analysis import analyze_portfolio
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from log_setup import get_logger

log = get_logger(__name__)


def _fetch_closes(tickers: list[str], api) -> dict[str, pd.Series]:
    """Fetch daily close series for a list of tickers."""
    closes = {}
    for ticker in tickers:
        try:
            daily = api.get_daily(ticker, years=1)
            s = pd.Series(
                daily["c"],
                index=pd.to_datetime(daily["t"], unit="s"),
                name=ticker,
            )
            closes[ticker] = s
            log.debug("Fetched closes for %s (%d days)", ticker, len(s))
        except Exception as exc:
            log.warning("Portfolio: could not fetch %s — %s", ticker, exc)
    return closes


def build_returns_matrix(closes: dict[str, pd.Series]) -> pd.DataFrame:
    """Align close series and compute daily log returns."""
    if not closes:
        return pd.DataFrame()
    df = pd.DataFrame(closes)
    df = df.dropna(how="all").sort_index()
    # Fill forward any gaps (holidays differ between assets)
    df = df.ffill()
    returns = df.pct_change().dropna(how="all")
    return returns


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Compute Pearson correlation matrix of daily returns."""
    if returns.empty:
        return pd.DataFrame()
    return returns.corr(method="pearson").round(3)


def portfolio_stats(
    returns: pd.DataFrame,
    weights: dict[str, float],
    annualize: bool = True,
) -> dict:
    """Compute portfolio-level statistics.

    Parameters
    ----------
    returns : DataFrame of daily returns (tickers as columns)
    weights : dict mapping ticker -> weight (0-1, should sum to 1)
    annualize : multiply volatility by sqrt(252)

    Returns
    -------
    dict with portfolio_return_pct, portfolio_vol_pct, sharpe,
    diversification_ratio, effective_n
    """
    if returns.empty:
        return {}

    tickers = [t for t in weights if t in returns.columns]
    if not tickers:
        return {}

    w = pd.Series({t: weights[t] for t in tickers})
    w = w / w.sum()  # normalize

    sub = returns[tickers].dropna()
    if len(sub) < 20:
        return {}

    # Mean daily return → annualized
    mean_daily = sub.mean()
    port_mean = float(w.dot(mean_daily))
    port_return_ann = port_mean * 252 * 100

    # Covariance
    cov = sub.cov()
    port_var = float(w @ cov @ w)
    port_std_daily = math.sqrt(port_var)
    port_vol_ann = port_std_daily * math.sqrt(252) * 100

    # Sharpe (risk-free rate ~= 5% annual for current rate environment)
    rf_daily = 0.05 / 252
    sharpe = ((port_mean - rf_daily) / port_std_daily * math.sqrt(252)) if port_std_daily > 0 else None

    # Diversification ratio = weighted avg individual vol / portfolio vol
    individual_vols = sub.std() * math.sqrt(252)
    weighted_avg_vol = float(w.dot(individual_vols)) * 100
    div_ratio = weighted_avg_vol / port_vol_ann if port_vol_ann > 0 else 1.0

    # Effective N (Herfindahl-style)
    effective_n = round(1 / float((w**2).sum()), 2)

    return {
        "tickers": tickers,
        "weights": {t: round(float(w[t]), 4) for t in tickers},
        "portfolio_return_pct": round(port_return_ann, 2),
        "portfolio_vol_pct": round(port_vol_ann, 2),
        "sharpe": round(sharpe, 2) if sharpe else None,
        "diversification_ratio": round(div_ratio, 2),
        "effective_n": effective_n,
        "individual_vols": {t: round(float(individual_vols[t]) * 100, 1)
                            for t in tickers},
    }


def portfolio_beta(
    returns: pd.DataFrame,
    weights: dict[str, float],
    market_returns: pd.Series,
) -> float | None:
    """Compute portfolio beta vs. a market return series (e.g., SPY)."""
    tickers = [t for t in weights if t in returns.columns]
    if not tickers or market_returns is None:
        return None

    w = pd.Series({t: weights[t] for t in tickers})
    w = w / w.sum()

    # Align
    sub = returns[tickers].copy()
    mkt = market_returns.rename("market")
    aligned = pd.concat([sub, mkt], axis=1).dropna()
    if len(aligned) < 20:
        return None

    port_ret = (aligned[tickers] * w.values).sum(axis=1)
    mkt_ret = aligned["market"]

    cov_pm = float(port_ret.cov(mkt_ret))
    var_m = float(mkt_ret.var())
    if var_m == 0:
        return None

    return round(cov_pm / var_m, 2)


def analyze_portfolio(
    tickers: list[str],
    weights: list[float],
    api,
    include_spy_beta: bool = True,
) -> dict:
    """Full portfolio analysis.

    Parameters
    ----------
    tickers : list of ticker symbols
    weights : list of portfolio weights (parallel to tickers, sum to 1)
    api     : FinnhubAPI or DataProvider instance

    Returns
    -------
    dict with correlation matrix, stats, beta, closes, returns
    """
    if len(tickers) != len(weights):
        raise ValueError("tickers and weights must have the same length")

    w_dict = {t: w for t, w in zip(tickers, weights)}

    # Fetch closes for portfolio tickers + SPY for beta
    all_tickers = list(tickers)
    if include_spy_beta and "SPY" not in all_tickers:
        all_tickers = all_tickers + ["SPY"]

    log.info("Portfolio analysis: fetching data for %s", all_tickers)
    closes = _fetch_closes(all_tickers, api)
    returns = build_returns_matrix(closes)

    corr = correlation_matrix(returns.drop(columns=["SPY"], errors="ignore"))
    stats = portfolio_stats(returns.drop(columns=["SPY"], errors="ignore"), w_dict)

    beta = None
    if include_spy_beta and "SPY" in returns.columns:
        beta = portfolio_beta(
            returns.drop(columns=["SPY"], errors="ignore"),
            w_dict,
            returns["SPY"],
        )

    return {
        "tickers": tickers,
        "weights": w_dict,
        "correlation": corr,
        "stats": stats,
        "portfolio_beta": beta,
        "closes": {t: closes[t] for t in tickers if t in closes},
        "returns": returns.drop(columns=["SPY"], errors="ignore"),
    }

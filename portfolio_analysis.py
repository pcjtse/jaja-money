"""Portfolio-Level Risk & Correlation Analysis (P2.4 / P11.x).

Computes portfolio metrics for a multi-stock portfolio including:
- Correlation matrix from daily returns
- Portfolio-level beta, volatility, and weighted factor score
- Expected portfolio return based on factor scores
- Monte Carlo simulation (P11.1)
- Kelly Criterion & optimal position sizing (P11.2)
- Factor Attribution Analysis (P11.3)

Usage:
    from portfolio_analysis import analyze_portfolio, monte_carlo_simulation, kelly_sizing, factor_attribution
"""
from __future__ import annotations

import math
import random

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


# ---------------------------------------------------------------------------
# P11.1: Monte Carlo Portfolio Simulation
# ---------------------------------------------------------------------------


def monte_carlo_simulation(
    returns: pd.DataFrame,
    weights: dict[str, float],
    n_simulations: int = 10_000,
    horizon_days: int = 252,
    seed: int | None = 42,
) -> dict:
    """Run Monte Carlo simulation of portfolio returns.

    Uses bootstrapped daily returns (sampling with replacement).

    Parameters
    ----------
    returns : DataFrame of daily returns (tickers as columns)
    weights : dict mapping ticker -> weight (should sum to 1)
    n_simulations : number of simulation paths
    horizon_days : number of trading days to simulate (252 = 1 year)
    seed : random seed for reproducibility

    Returns
    -------
    dict with: simulated_final_returns (list), percentiles (dict),
    prob_target (dict), prob_ruin (float), median_return_pct
    """
    if returns.empty:
        return {}

    tickers = [t for t in weights if t in returns.columns]
    if not tickers:
        return {}

    w = pd.Series({t: weights[t] for t in tickers})
    w = w / w.sum()

    sub = returns[tickers].dropna()
    if len(sub) < 20:
        return {}

    if seed is not None:
        random.seed(seed)

    # Compute weighted daily returns as a single series
    port_daily = (sub * w.values).sum(axis=1)
    daily_values = port_daily.values

    # Bootstrap simulation
    n_days = len(daily_values)
    final_returns = []

    for _ in range(n_simulations):
        # Sample with replacement
        indices = [int(random.random() * n_days) for _ in range(horizon_days)]
        sampled = [daily_values[i] for i in indices]
        # Compound returns: (1+r1)(1+r2)...(1+rN) - 1
        compounded = 1.0
        for r in sampled:
            compounded *= (1 + r)
        final_returns.append((compounded - 1) * 100)  # as percentage

    final_returns.sort()
    n = len(final_returns)

    def _pct(p: float) -> float:
        idx = int(p / 100 * n)
        idx = max(0, min(idx, n - 1))
        return round(final_returns[idx], 2)

    percentiles = {
        "p5": _pct(5),
        "p10": _pct(10),
        "p25": _pct(25),
        "p50": _pct(50),
        "p75": _pct(75),
        "p90": _pct(90),
        "p95": _pct(95),
    }

    # Probability of achieving target returns
    prob_target = {}
    for target in [0, 5, 10, 15, 20, 25]:
        count = sum(1 for r in final_returns if r >= target)
        prob_target[f"{target}%"] = round(count / n * 100, 1)

    # Probability of ruin (drawdown > 20%)
    ruin_threshold = -20.0
    prob_ruin = round(
        sum(1 for r in final_returns if r <= ruin_threshold) / n * 100, 1
    )

    log.info(
        "Monte Carlo: %d sims, median=%.1f%%, ruin_prob=%.1f%%",
        n_simulations,
        percentiles["p50"],
        prob_ruin,
    )

    return {
        "n_simulations": n_simulations,
        "horizon_days": horizon_days,
        "simulated_final_returns": final_returns,
        "percentiles": percentiles,
        "prob_target": prob_target,
        "prob_ruin": prob_ruin,
        "median_return_pct": percentiles["p50"],
        "mean_return_pct": round(sum(final_returns) / n, 2),
    }


# ---------------------------------------------------------------------------
# P11.2: Kelly Criterion & Optimal Position Sizing
# ---------------------------------------------------------------------------


def kelly_sizing(
    factor_scores: dict[str, float],
    returns: pd.DataFrame,
    account_size: float = 100_000,
    max_position_pct: float = 20.0,
    kelly_fractions: list[float] | None = None,
) -> dict:
    """Compute Kelly Criterion position sizing for portfolio positions.

    Uses factor score as a proxy for edge (win probability).

    Parameters
    ----------
    factor_scores : dict mapping ticker -> factor score (0-100)
    returns : DataFrame of daily returns
    account_size : total account size in dollars
    max_position_pct : hard cap on any single position (%)
    kelly_fractions : fractions to compute (default: [1.0, 0.5, 0.25])

    Returns
    -------
    dict mapping ticker -> sizing dict with full/half/quarter kelly %
    """
    if kelly_fractions is None:
        kelly_fractions = [1.0, 0.5, 0.25]

    results = {}
    tickers = [t for t in factor_scores if t in returns.columns]

    for ticker in tickers:
        ticker_returns = returns[ticker].dropna()
        if len(ticker_returns) < 20:
            continue

        # Win rate from historical returns
        pos = ticker_returns[ticker_returns > 0]
        neg = ticker_returns[ticker_returns < 0]
        win_rate = len(pos) / len(ticker_returns) if len(ticker_returns) > 0 else 0.5

        # Average win/loss ratio
        avg_win = float(pos.mean()) if len(pos) > 0 else 0.001
        avg_loss = abs(float(neg.mean())) if len(neg) > 0 else 0.001
        win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1.0

        # Kelly fraction: f* = (b*p - q) / b
        # where b = win/loss ratio, p = win_rate, q = 1 - p
        p = win_rate
        q = 1 - p
        b = win_loss_ratio
        full_kelly = (b * p - q) / b if b > 0 else 0.0

        # Factor score boost: higher score → slight upward adjustment
        score = factor_scores.get(ticker, 50) / 100
        adjusted_kelly = full_kelly * (0.8 + 0.4 * score)  # 0.8 to 1.2 multiplier
        adjusted_kelly = max(0.0, min(adjusted_kelly, max_position_pct / 100))

        sizing = {
            "full_kelly_pct": round(adjusted_kelly * 100, 1),
            "win_rate": round(win_rate * 100, 1),
            "win_loss_ratio": round(win_loss_ratio, 2),
        }

        for frac in kelly_fractions:
            frac_pct = min(adjusted_kelly * frac * 100, max_position_pct)
            dollar_amount = account_size * frac_pct / 100
            label = f"{int(frac * 100)}%_kelly"
            sizing[label] = {
                "pct": round(frac_pct, 1),
                "dollars": round(dollar_amount, 0),
            }

        # Equal weight comparison
        n = len(tickers)
        equal_pct = 100 / n if n > 0 else 0
        sizing["equal_weight"] = {
            "pct": round(equal_pct, 1),
            "dollars": round(account_size * equal_pct / 100, 0),
        }

        results[ticker] = sizing

    return results


# ---------------------------------------------------------------------------
# P11.3: Factor Attribution Analysis
# ---------------------------------------------------------------------------


FACTOR_DIMENSIONS = [
    "valuation", "trend", "rsi", "macd",
    "sentiment", "earnings", "analyst", "range",
]


def factor_attribution(
    factor_details: dict[str, dict],
    weights: dict[str, float],
) -> dict:
    """Decompose portfolio composite score by factor dimension.

    Parameters
    ----------
    factor_details : dict mapping ticker -> dict of factor scores per dimension
                     e.g., {"AAPL": {"valuation": 60, "trend": 80, ...}, ...}
    weights : dict mapping ticker -> portfolio weight (should sum to 1)

    Returns
    -------
    dict with:
      - factor_contributions: dict mapping factor -> weighted contribution
      - concentration_risk: highest-contributing factor and its share
      - ticker_contributions: per-ticker breakdown
    """
    tickers = [t for t in weights if t in factor_details]
    if not tickers:
        return {}

    w = {t: weights[t] for t in tickers}
    total_w = sum(w.values())
    if total_w <= 0:
        return {}
    # Normalize weights
    w = {t: wt / total_w for t, wt in w.items()}

    factor_contributions: dict[str, float] = {f: 0.0 for f in FACTOR_DIMENSIONS}
    ticker_contributions: dict[str, dict] = {}

    for ticker in tickers:
        scores = factor_details[ticker]
        weight = w[ticker]
        ticker_contribs = {}
        for factor in FACTOR_DIMENSIONS:
            score = scores.get(factor, 0)
            contrib = score * weight
            factor_contributions[factor] = factor_contributions[factor] + contrib
            ticker_contribs[factor] = round(contrib, 2)
        ticker_contributions[ticker] = ticker_contribs

    # Total weighted score
    total_score = sum(factor_contributions.values())

    # Factor share of total
    factor_shares = {}
    for f, contrib in factor_contributions.items():
        share = contrib / total_score * 100 if total_score > 0 else 0
        factor_shares[f] = round(share, 1)

    # Concentration risk: top factor by share
    top_factor = max(factor_shares, key=lambda f: factor_shares[f]) if factor_shares else None
    top_share = factor_shares.get(top_factor, 0) if top_factor else 0

    concentration_warning = None
    if top_share > 30:
        concentration_warning = (
            f"Portfolio is {top_share:.0f}% driven by '{top_factor}' factor — "
            "consider diversifying factor exposure."
        )

    return {
        "factor_contributions": {
            f: round(v, 2) for f, v in factor_contributions.items()
        },
        "factor_shares": factor_shares,
        "total_weighted_score": round(total_score, 1),
        "ticker_contributions": ticker_contributions,
        "top_factor": top_factor,
        "top_factor_share": top_share,
        "concentration_warning": concentration_warning,
    }

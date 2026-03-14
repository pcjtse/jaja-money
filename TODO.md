# TODO — Investment Strategy Suggestions

## High Value / Low Complexity

- [ ] **Pairs Trading / Statistical Arbitrage**
  Track the price spread between two correlated stocks (e.g. MSFT/GOOGL). Signal when the z-score diverges beyond ±2σ.
  _Files to touch: `backtest.py`, `screener.py`, new `pairs.py`_

- [ ] **Post-Earnings Announcement Drift (PEAD)**
  Buy after large positive earnings surprises, short after large misses. Earnings data already fetched via `get_earnings()`.
  _Files to touch: `factors.py` or new `pead.py`, `backtest.py`_

- [ ] **Dividend Growth Screen**
  Filter for stocks with: yield >2%, 5yr dividend CAGR >7%, payout ratio <60%, consecutive years of growth.
  _Files to touch: `screener.py`, `factors.py`_

- [ ] **Graham Number / Deep Value Screen**
  Compute `√(22.5 × EPS × BVPS)` and flag stocks trading below it. Zero new API calls needed.
  _Files to touch: `screener.py`, `factors.py`_

---

## Medium Complexity

- [ ] **Cross-Sectional Momentum (Relative Strength)**
  Rank a universe of stocks by 6-month / 12-month returns, long top decile, avoid bottom decile. Rotate monthly.
  _Files to touch: `sectors.py`, `screener.py`_

- [ ] **Quality Factor (Piotroski F-Score)**
  9-point binary scoring of profitability, leverage, and operating efficiency. High F-Score (≥7) = strong buy candidate.
  _Files to touch: `factors.py`_

- [ ] **Macro Regime Detection**
  Classify market into Bull / Bear / Stagflation / Recovery based on SPY trend + VIX + 10Y yield. Adjust factor weights per regime.
  _Files to touch: `factors.py`, `config.py`_

- [ ] **Seasonal / Calendar Patterns**
  January Effect, "Sell in May", year-end tax-loss harvesting reversal. Overlay seasonal bias on existing factor scores.
  _Files to touch: `factors.py`_

---

## Requires More Work

- [ ] **Multi-Asset / Risk Parity Rotation**
  Rotate across asset classes (SPY, TLT, GLD, DBC, VNQ) using equal risk contribution weighting.
  _Files to touch: `portfolio_analysis.py`, `sectors.py`_

- [ ] **Short Selling Screen**
  Combine high short interest, insider selling signals, declining earnings quality, and weak factor score into a dedicated bearish screener.
  _Files to touch: `screener.py`, `ownership.py`_

# AutoResearch — jaja-money Strategy Optimizer

## Objective

Maximize the **average Sharpe ratio** across a diversified backtest set
(AAPL, MSFT, GOOGL — 3 years, 0.1% commission, 0.05% slippage per side).

The primary metric is printed as `SHARPE: X.XX` by `autoresearch/evaluate.py`.
Secondary metrics: `RETURN`, `DRAWDOWN`, `WIN_RATE`, `TRADES`.

Maximize Sharpe first. If Sharpe is equal (within 0.05), prefer lower drawdown.

---

## Editable File

**`autoresearch/strategy_runner.py`** — you may modify ONLY this file.

Entry point: `compute_signal(close: pd.Series, index: int) -> int`
- `close` is a `pandas.Series` of daily closing prices (full history up to `index`)
- `index` is the current bar (0-based); use `close.iloc[:index+1]` for the window
- Return an integer 0-100 (higher = more bullish)
- Return 50 if there is insufficient history (< 35 bars)

You may add helper functions and import from `math`, `pandas`, `numpy`.
**Do not import from** `src/` modules or external libraries beyond `math`, `pandas`, `numpy`.

---

## Evaluation

```bash
python autoresearch/evaluate.py
```

Parses stdout for `SHARPE: X.XX`. A run that exits non-zero is considered a failure.

A run that completes in under 60 seconds is preferred.

---

## Constraints (non-negotiable)

1. **No look-ahead bias** — only use `close.iloc[:index+1]` (data up to the current bar).
2. **Return 50 when history < 35 bars** — the backtest engine skips signals early on.
3. **Return value must be in 0-100** — clamp with `max(0, min(100, score))`.
4. **Function signature must remain** `compute_signal(close: pd.Series, index: int) -> int`.
5. Do not modify `evaluate.py`, `backtest.py`, or any `src/` file.

---

## Baseline

The starting `strategy_runner.py` uses **Price Technical v2**:
- SMA trend (35%) — directional price vs SMA-50/SMA-200
- RSI directional (25%) — bullish when RSI 60-75, bearish when 30-45
- MACD histogram (25%) — direction and momentum of histogram bars
- Bollinger Band position (15%) — price position within ±2σ bands

Baseline Sharpe: see `autoresearch/results.tsv`.

---

## Ideas to Explore

The agent is encouraged to experiment with, but not limited to:

### Indicator modifications
- Replace fixed SMA windows (50, 200) with adaptive EMAs
- Try SMA-20/SMA-50 crossover instead of SMA-50/SMA-200 (faster signals)
- Replace MACD (12/26/9) with a faster variant (8/21/5)
- Add Average True Range (ATR) as a volatility filter — widen effective thresholds in high-ATR regimes
- Add On-Balance Volume (OBV) slope as a volume confirmation factor
- Add Rate of Change (ROC-10) as an additional momentum factor

### Weight adjustments
- Re-balance the 35/25/25/15 weights
- Experiment with non-linear combinations (e.g., geometric mean instead of weighted average)

### Regime filters
- When SMA-50 < SMA-200 (bear regime), tighten buy threshold (require score ≥ 72 instead of ≥ 65)
- When VIX-proxy (30-day rolling std of daily returns > 2.5%) is elevated, reduce position size signal

### Threshold-adaptive logic
- Dynamically raise the buy threshold during high-volatility periods
- Add a trend-strength multiplier (ADX-proxy) to boost/reduce score by ±10

### New composite patterns
- Combine SMA trend direction + RSI direction + MACD direction as a 3-of-3 confirmation
  (all three bullish = 90, 2-of-3 = 70, 1-of-3 = 40, 0-of-3 = 10)

---

## Loop Instructions (for Claude Code agent)

1. Read `autoresearch/results.tsv` to understand what has been tried.
2. Read `autoresearch/strategy_runner.py` to see the current state.
3. Propose ONE targeted modification based on your read of results history.
4. Modify `strategy_runner.py`.
5. Run `python autoresearch/evaluate.py`.
6. If `SHARPE: X.XX` is higher than the current best in `results.tsv`:
   - Run `git add autoresearch/strategy_runner.py && git commit -m "autoresearch: <brief description> SHARPE=X.XX"`
   - Append result to `autoresearch/results.tsv`
7. If not improved:
   - Run `git checkout autoresearch/strategy_runner.py` to revert
   - Append the failed result to `autoresearch/results.tsv` (mark as REVERT)
8. Loop.

Target: run 50+ experiments. Stop when Sharpe > 2.0 or after 8 hours.

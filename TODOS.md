# TODOS

Tracked work deferred from engineering reviews. Each item has context so it's
actionable months from now.

---

## TODO-001: Fix ml_weights.py stale name_to_key mapping

**What:** `ml_weights.py:_parse_factors_json()` maps factor display names to keys
using a hardcoded dict that was never updated after factors.py was refactored.
It uses "Price Trend", "RSI", "MACD", "Sentiment", "Earnings Surprise",
"Analyst Recommendations", "52-Week Range" — none of which match current
factors.py output ("Trend (SMA)", "Momentum (RSI)", "MACD Signal", "News Sentiment",
"Earnings Quality", "Analyst Consensus", "52-Wk Strength").

**Why:** `get_adaptive_weights()` is silently training on 0-2 matched rows instead
of the full analysis_history. Every quarterly reweight is falling back to static
weights without logging a visible error.

**How to apply:** Replace `name_to_key` in `ml_weights._parse_factors_json()` with
the exact strings from `factor_attribution.CORE_FACTOR_NAMES` (once that module exists).
Add a test that feeds a real factors_json fixture and asserts all 8 keys are parsed.

**Depends on:** factor_attribution.py must ship first — it proves which 8 names are
correct and provides `CORE_FACTOR_NAMES` as the authoritative source.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

---

## TODO-002: Fix ml_weights.py 50.0 neutral fill bug

**What:** `ml_weights.py:build_training_dataset()` line 127 fills absent factor
scores with 50.0: `row[key] = factor_scores.get(key, 50.0)`. For sparse alpha
signals (e.g., congressional, dark_pool), 98%+ of rows become 50.0. The logistic
regression correctly concludes the feature is uninformative — but it's not
uninformative, it's sparse.

**Why:** Destroys sparse signal quality in the ML weights pipeline. A congressional
trading signal with IC=0.31 at n=18 (real observations) collapses toward zero
because 1482/1500 rows are filled noise.

**How to apply:** For each sparse factor, train only on non-null rows (filter to
rows where that factor key was parsed). Restructure `build_training_dataset()` to
return per-factor datasets, not a single filled dataset. This is a significant
restructure — do after IC attribution validates which sparse factors have real IC.

**Depends on:** TODO-001 (stale names fix must come first). factor_attribution.py
results should guide which sparse factors are worth including.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

---

## TODO-003: Enforce ABSENT_LABEL convention across all factor functions

**What:** `factor_attribution.py` uses `label == "No data"` to detect absent sparse
factors. This string is a literal repeated across ~20 `_factor_*` functions in
`factors.py`. It's a convention, not a contract. A new factor using "N/A" or
"Unavailable" would silently be treated as score=50, corrupting IC computation.

**Why:** Attribution module's correctness depends entirely on this convention.
One missed label string silently poisons the sparse factor dataset.

**How to apply:**
1. Add `FACTOR_ABSENT_LABEL = "No data"` to `src/core/constants.py` (or `factors.py`).
2. Replace `label="No data"` in every `_factor_*` function with `label=FACTOR_ABSENT_LABEL`.
3. Import `FACTOR_ABSENT_LABEL` in `factor_attribution.py` instead of hardcoding "No data".
Scope: ~20 one-line changes in factors.py.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

---

## TODO-004: Document T+21/T+63/T+126 vs T+5/T+10/T+30 horizon separation

**What:** `signal_returns` table stores T+21/T+63/T+126 trading-day forward returns
for factor research. The prior Signal Ledger design (main branch) planned
T+5/T+10/T+30 calendar-day returns for paper trade performance tracking.
These serve different purposes and must NOT share a table.

**Why:** When the paper ledger is eventually built, the developer will be tempted
to reuse `signal_returns` for short-horizon trade performance. T+5 and T+21 are
not the same horizon. The join would produce incorrect results silently.

**How to apply:**
- Add a docstring to `_ensure_signal_returns_table()` in `history.py` stating
  the intended use: "factor research, T+21/T+63/T+126 trading-day horizons only".
- Add a section to README/ARCHITECTURE clarifying the two data stores and why
  they're separate.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

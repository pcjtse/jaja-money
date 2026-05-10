# TODOS

Tracked work deferred from engineering reviews. Each item has context so it's
actionable months from now.

---

## TODO-001: Fix ml_weights.py stale name_to_key mapping ✅ RESOLVED

**What:** `ml_weights.py:_parse_factors_json()` maps factor display names to keys
using a hardcoded dict that was never updated after factors.py was refactored.

**Resolution (2026-05-09):** `_parse_factors_json()` now imports `CORE_FACTOR_NAMES`
directly from `factor_attribution.py` (line 67 of `ml_weights.py`). No hardcoded dict
exists. The stale "KNOWN BUG" comment in `factor_attribution.py` has been removed.
Test `test_parse_factors_json_all_8_core_keys` in `tests/test_ml_weights.py` guards
against future regression.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

---

## TODO-002: Fix ml_weights.py 50.0 neutral fill bug ✅ RESOLVED

**What:** `build_training_dataset()` was filling absent factor scores with 50.0,
destroying sparse signal quality by making the model treat noise as neutral observations.

**Resolution (2026-05-09):** `build_training_dataset()` now stores `float("nan")` for
absent factor keys (not 50.0). `walk_forward_train()` calls `df.dropna(subset=FACTOR_KEYS)`
before fitting, so rows with missing core factors are excluded rather than corrupted.
Sparse alpha factors are not in `FACTOR_KEYS` and are not included in training at all.
Test `test_build_training_dataset_uses_nan_not_50_for_missing_factors` guards this.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

---

## TODO-003: Enforce ABSENT_LABEL convention across all factor functions ✅ RESOLVED

**What:** `factor_attribution.py` uses `label == "No data"` to detect absent sparse
factors. This string needed to be a constant, not a repeated literal.

**Resolution (2026-05-09):** `FACTOR_ABSENT_LABEL = "No data"` is defined at line 29
of `factors.py` and used by all ~24 `_factor_*` functions. `factor_attribution.py`
imports it as `ABSENT_LABEL` at module top. No hardcoded `"No data"` strings exist
in the codebase.

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

---

## TODO-004: Document T+21/T+63/T+126 vs T+5/T+10/T+30 horizon separation ✅ RESOLVED

**What:** `signal_returns` stores trading-day forward returns for IC research; the
paper ledger stores calendar-day returns for P&L tracking. These must never be joined.

**Resolution (2026-05-09):**
- `_ensure_signal_returns_table()` in `src/data/history.py` has a full docstring
  explaining the separation and explicitly warning against joining the two stores.
- `README.md` now includes a "Data Architecture — Storage Separation" section with
  a comparison table (store, file, horizon units, purpose).

**Captured:** 2026-03-31, from /plan-eng-review of Per-Factor IC Attribution module.

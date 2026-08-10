# jaja-money — Rework Plan

**Date:** 2026-08-10
**Status:** Proposal, pending decisions in [§9](#9-decisions-needed-from-you)
**Scope:** Full rework, same goal, radically smaller surface

---

## 1. The goal (unchanged)

> Give an individual investor institutional-grade, AI-assisted equity research —
> a signal they can act on, with evidence it actually works.

Nothing in this plan changes that. What changes is the strategy for getting there.

---

## 2. Why the current build has low value

The codebase is not slop. `ruff check .` is clean, 1,265 unit tests pass, the caching,
rate-limiting and retry infrastructure is genuinely production-shaped. The problem is
strategic, not craftsmanship.

**In two months (147 commits, 2026-03-10 → 2026-05-10) the project produced 54,866
lines of Python and zero evidence.** Every claimed moat is empty as of today:

| Claimed moat (README) | Actual state |
|---|---|
| "Signal validation data accumulates and becomes proprietary" | No `history.db` exists. No signal has ever been recorded. |
| "Autoresearch loop — ~12 experiments/hour, 100+ overnight" | `autoresearch/results.tsv` contains one row: `baseline … PENDING`. It has never run. |
| "24-factor signal depth took years to build" | Built in 8 weeks; ~10 of the 24 factors cannot source real data (see 2.2). |
| "ML adaptive weighting layer" | Inert. `get_weights_metadata()` returns `source: "static"` and always will until 30+ labelled rows exist. |
| Daily signal cron (`.github/workflows/signal_check.yml`) | Commits `data/ledger.json` — a file that does not exist in the repo. |

The README describes a system that would be valuable if it had been running. It has not
been running. **Surface area was built where evidence should have been.**

### 2.1 The score is not comparable across tickers — this is the critical defect

`composite_score()` (`src/analysis/factors.py:1126`) divides by the weight of whichever
factors happened to return data:

```python
total_weight = sum(f["weight"] for f in factors)
weighted_sum = sum(f["score"] * f["weight"] for f in factors)
return _clamp(weighted_sum / total_weight)
```

Declared weights total **≈1.76** across 24 factors (1.63 in `config.yaml`, plus
`dividend` 0.05 and `estimate_revision` 0.08 which are hardcoded defaults not present in
config at all). Factors with no data are dropped, not neutralised.

Consequences:

- AAPL scored on 20 present factors and a mid-cap scored on 8 are **different metrics
  wearing the same 0–100 label**.
- The same ticker's score changes when an upstream API is merely *slow*, with no
  indication in the output.
- Therefore the Screener, Rankings, Backtest, Signal Quality (IC) and Factor Attribution
  pages are all ranking and correlating incommensurable numbers. **One defect
  invalidates five features and the entire validation thesis simultaneously.**

Nothing else in this plan matters until this is fixed.

### 2.2 Factors named after data the system does not have

A recurring pattern: a module is named for a premium/institutional dataset, the real
fetch fails in normal operation, and a heuristic fills in silently.

- **`src/data/dark_pool.py`** — `_FINRA_ATS_URL` points at
  `otctransparency.finra.org/otctransparency/AtsIssueData`, an HTML portal, not a JSON
  API. `_fetch_finra_ats()` returns `[]` unless `Content-Type` contains `json`, so in
  practice it always returns `[]`. Control falls to `_estimate_from_yfinance()`, which
  computes `ats_volume = avg_vol * 0.38` — **a hardcoded constant**
  (`src/data/dark_pool.py:158`). The "dark pool FINRA ATS detection" factor is a volume
  trend multiplied by 0.38.
- **`src/data/geographic_revenue.py:85`** — "Weights are rough heuristics based on
  keyword frequency"; falls back to yfinance country of incorporation as "a crude proxy".
- **`src/data/borrow_rates.py:109`** — CTB from hardcoded short-float tiers, `source:
  "heuristic"`.
- **`src/analysis/supply_chain_graph.py`** — regex pattern matching over 10-K text,
  `_estimate_supplier_count()`.
- **Finnhub premium endpoints called with a free-tier key**: `stock_candles`,
  `stock_transcripts_list`, `stock_transcript`, `stock_price_target`,
  `stock_insider_transactions`, `stock_options`. Executive Tone (factor #24, the most
  recent addition, weight 0.07) needs transcripts — a free key returns nothing, forever.

So a real user following the Quick Start gets ~8 textbook technical factors, a
renormalised score that looks authoritative, and a UI that never says which of the 24
factors were dark.

### 2.3 The AI layer is unfalsifiable

`src/analysis/analyzer.py` is 2,031 lines producing narrative and 12-month price targets.
No target is ever compared to the outcome. There is no record of what was predicted, so
the AI layer cannot be improved, defended, or priced. It is a cost centre with no
measurable output.

Model IDs are also a generation stale: `claude-opus-4-6` (12 references),
`claude-sonnet-4-6` (8), `claude-haiku-4-5-20251001` (4). The Claude 5 family is current.

### 2.4 Architecture debt that blocks the fix

- **15 modules create SQLite tables at import time** — `_ensure_congress_table()`,
  `_ensure_dark_pool_table()`, `_ensure_signal_returns_table()`, and 12 more, all firing
  on `import` and all writing to `~/.jaja-money/history.db`. No migrations, no schema
  version, no single owner. `import src.data.congress` creates a database in the user's
  home directory. This makes parallel testing unsafe, multi-user deployment impossible,
  and schema evolution a guessing game.
- **Five implementations of RSI/SMA** — `factors.py`, `guardrails.py`, `portfolio.py`,
  `sectors.py`, and `app.py` (`calc_rsi`/`calc_sma`/`calc_macd`). They can and will drift.
- **`app.py` is 2,605 lines** with 360 `st.` calls and ~25 `@st.cache_data` fetch
  wrappers duplicating the provider layer's caching.
- **20,492 lines of tests defending the wrong thing.** Coverage protects UI plumbing and
  textbook indicator maths. Nothing tests the property that actually matters: *is the
  score comparable between two tickers with different data coverage?*
- **Two failing tests on `main`** (`tests/test_ml_weights.py`) — a time bomb: the tests
  hardcode `trained_date: "2026-03-20"` and `RETRAIN_EVERY_DAYS = 90`, so they began
  failing on 2026-06-18 and no one noticed.

### 2.5 Distribution mismatch

`git clone` + venv + two API keys (one of them paid) + `streamlit run` + local SQLite in
`$HOME`. That is a notebook's distribution model attached to a product's ambition. The
FastAPI server (`src/services/server.py`) and the `jaja_money_skill/` package are the
only pieces shaped like something another system can consume.

---

## 3. The thesis for the rework

**Value comes from evidence, not surface area.**

One signal that is (a) computable for *every* ticker from *free* data, (b) recorded
before the outcome is known, and (c) published against reality — is worth more than 24
factors nobody can verify. The proprietary asset is the *track record*, and the track
record can only start accumulating once, so it should start now, at the smallest
possible scope.

Everything else is deleted or frozen until that record exists.

### Design principles

1. **Nothing ships without a coverage flag.** Every score carries the fraction of its
   weight basis that was actually observed. A score with 40% coverage is displayed as
   such or not displayed.
2. **Fixed denominator.** The composite weight basis is constant. Absent factors are
   explicitly neutral, never dropped.
3. **A factor may only be named after its actual source.** If it is a volume heuristic it
   is called a volume heuristic. No proxy is promoted to the name of the thing it proxies.
4. **Every prediction is recorded before its outcome is knowable, and scored after.**
   Prose that makes no recorded claim is not a feature.
5. **One store, one schema, one owner, migrations, no import-time side effects.**
6. **Free tier must be fully functional.** Premium data may enhance; it may never be load-
   bearing.

---

## 4. Target architecture

```
jaja/
  store/          ← the only module that touches persistence
    schema.sql        versioned DDL
    migrations/       numbered, forward-only
    signals.py        append-only signal records (immutable)
    outcomes.py       forward returns, joined by signal id
    predictions.py    AI claims + resolution
  market/         ← data acquisition
    providers/        yfinance (free, required) | finnhub (optional)
    capability.py     each provider declares what it can serve
    indicators.py     THE rsi/sma/macd/bbands — one implementation
  signal/
    factors/          one module per factor, each declares weight + data requirement
    composite.py      fixed-denominator scoring + coverage
  evidence/
    ic.py             Spearman IC, per-horizon
    attribution.py    per-factor IC, BH correction
    scorecard.py      the public record
  ai/
    research.py       claim-first, every claim recorded as a prediction
  api/              FastAPI — the real distribution surface
  web/              3 pages, thin, no business logic
```

**Storage:** SQLite stays for local, but behind `store/` with migrations and an
explicit path (`JAJA_DATA_DIR`), never a home-directory side effect at import.
Postgres becomes a config swap later if hosted mode happens.

---

## 5. Phased plan

Each phase has an exit criterion. **A phase does not end because time ran out; it ends
when its criterion is met.** Estimates assume one engineer plus Claude.

### Phase 0 — Truth reset (2–3 days)

Stop advertising things that do not exist. This is cheap and it unblocks honest thinking.

- Fix the 2 failing `test_ml_weights.py` tests — replace hardcoded `trained_date` with a
  date computed relative to `utcnow()` so it cannot rot again.
- Rewrite `README.md` to describe what runs today. Move the aspirational content to
  `VISION.md`, clearly labelled as unbuilt.
- Update all Claude model IDs to the Claude 5 family; centralise them in one constant so
  there is one place to change next time.
- Add `docs/DIAGNOSIS.md` = §2 of this document, so the reasoning survives.
- Freeze all feature work.

**Exit:** `main` is green, and no document claims a capability the code does not have.

### Phase 1 — Evidence spine (2–3 weeks) ← *the whole point*

Build the thing that should have been built first. It records signals so that in 90 days
there is something to analyse.

- `store/` package: schema v1, forward-only migrations, `JAJA_DATA_DIR`, zero import-time
  side effects. Delete all 15 `_ensure_*_table()` module-level calls.
- Immutable `signals` table: `(id, symbol, asof_date, composite, coverage_pct,
  factor_scores_json, inputs_hash, code_version)`. Append-only — a signal is never updated
  after write. `inputs_hash` makes retroactive tampering detectable.
- `outcomes` table filled by a separate job at T+21 / T+63 / T+126 trading days, joined by
  signal id. Trading-day and calendar-day stores stay separate (this is already documented
  correctly in TODO-004 — preserve that discipline).
- A daily GitHub Action that **actually runs** against a fixed 100-ticker universe using
  yfinance only, and fails loudly if it records nothing.
- A `scorecard` command + endpoint: n signals, IC by horizon, coverage distribution.
  Publishes "insufficient data (n=14, need 30)" honestly rather than hiding.

**Exit:** the daily job has run for 10 consecutive trading days and the store contains
1,000+ signal rows with coverage recorded. *Everything downstream waits on this.*

### Phase 2 — Cut to a defensible core (2 weeks, parallel with Phase 1's soak)

- **Fixed-denominator composite.** Absent factor → explicit neutral (50) *and* a coverage
  deduction. `coverage_pct` is a first-class output. Below a configured floor
  (start: 60%) the signal is emitted as `INSUFFICIENT`, not a number.
- **Delete or quarantine factors that cannot source real data on a free key.** Candidates
  for deletion: `dark_pool`, `geo_revenue`, `supply_chain`, `borrow_rates`,
  `executive_tone`, `congress`, `institutional_flow`, `options_flow`,
  `special_situation`, `crowding`. Quarantine = moved to `experimental/`, weight 0,
  excluded from composite, kept only if it has a real source path.
- Keep ~8 factors computable from free OHLCV + free fundamentals: trend, RSI, MACD,
  range position, sector-relative valuation, earnings quality, analyst consensus,
  estimate revisions. **Every one of them is textbook — that is fine.** The claim is no
  longer "novel factors", it is "an honestly scored composite with a published track
  record", which nobody else offers retail.
- One `market/indicators.py`. Delete the other four RSI/SMA implementations.
- Property test: *two tickers with identical factor scores but different coverage must
  produce the same composite and different coverage_pct.* This is the test that should
  have existed from day one.

**Exit:** composite is provably coverage-invariant; factor count is honest; a single
indicator module.

### Phase 3 — Data layer with declared capability (1–2 weeks)

- yfinance becomes the **required** provider (free, covers OHLCV + basic fundamentals).
  Finnhub becomes optional enhancement.
- `capability.py`: each provider declares which fields it can serve at which tier. The UI
  and API report *why* a factor is dark ("needs Finnhub paid tier") instead of silently
  dropping it.
- Delete `mock_data.py` as a production code path; mock data becomes a test fixture only,
  imported by tests, never reachable from `src`.
- Errors surface. The `try/except → return {}` pattern in optional fetchers becomes
  `Result[data, reason]` so absence has a recorded cause.

**Exit:** a user with zero API keys gets a fully functional, honestly-labelled product.

### Phase 4 — Make the AI falsifiable (2 weeks)

- Restructure the analyzer output: **claim first, prose second.** Every report emits
  structured claims — `{claim, direction, horizon, confidence, resolution_date}` — written
  to `store/predictions`.
- A resolution job scores each claim at its horizon. Brier score / hit rate published on
  the scorecard alongside factor IC.
- Cut `analyzer.py` from 2,031 lines to a prompt + a schema + a scorer. Most of that file
  is prompt-assembly variation that no evidence supports.
- The AI layer's value proposition becomes *measurable*: "our AI research calls resolve
  correct X% of the time" — which is a sentence no competitor is currently able to say.

**Exit:** every AI-generated claim in the last 30 days has a resolution date and a score
or a pending status.

### Phase 5 — Narrow the product surface (1–2 weeks)

- **11 pages → 3:**
  1. **Today** — ranked signals with coverage badges, and the live scorecard directly
     above them. The evidence and the recommendation on one screen.
  2. **Ticker** — one symbol: factors, coverage, the AI claim, the historical accuracy of
     past claims on this symbol.
  3. **Evidence** — IC by horizon, per-factor attribution with BH correction, prediction
     accuracy, coverage distribution.
- Delete: Compare, Screener, Portfolio, Sectors, Backtest, ForwardTest, Rankings,
  SignalQuality, FactorAttribution, Ledger as separate pages. Their genuinely-used logic
  folds into the three above; the rest goes. (`git` remembers them.)
- `app.py` 2,605 → target < 300 lines. Pages contain no business logic and no
  `@st.cache_data` data fetching — caching belongs in `market/`.
- The **API and the skill package are the primary product**, the web UI is the demo. That
  matches how this is actually consumable.

**Exit:** ≤ 3 pages, no business logic in `web/`, API parity with UI.

### Phase 6 — Let it compound (ongoing, starts at Phase 1 exit)

- The daily job runs. Every day. Alerting if it does not.
- Autoresearch actually runs against the Phase 1 store — and `results.tsv` gets rows.
  Until Phase 1 has 30+ labelled samples, autoresearch has nothing to optimise against
  and should stay off rather than optimise noise.
- Quarterly: retrain ML weights only when `n_samples ≥ MIN_SAMPLES` is genuinely met;
  otherwise keep static weights and say so.

**Exit:** none. This is the product.

---

## 6. What gets deleted

Deletion is the main deliverable of this plan. Rough magnitude:

| Area | Now | After | Note |
|---|---|---|---|
| `src/analysis/` | 13,322 | ~4,000 | factor cull, analyzer rewrite |
| `src/data/` | 6,640 | ~2,000 | providers + capability, drop dead sources |
| `pages/` + `app.py` | 6,137 | ~1,200 | 11 pages → 3 |
| `src/trading/` | 1,693 | ~400 | broker is read-only and disabled; keep watchlist |
| `tests/` | 20,492 | ~6,000 | tests follow the code they defend |
| **Total Python** | **54,866** | **~15,000** | |

Test count will drop and that is correct — the remaining suite tests properties
(coverage invariance, append-only integrity, no look-ahead) rather than restating
implementations.

`src/core/` (cache, rate limiter, config, logging) survives essentially intact. It is the
best code in the repo.

---

## 7. What this buys

- **A defensible claim in 90 days.** "Here is our signal's information coefficient at
  T+63 over N recorded, timestamped, tamper-evident signals" — with the record public.
  That is a sentence that separates this from every retail dashboard, and it costs
  nothing but discipline and time.
- **A product a free user can actually run**, so usage can start before revenue.
- **A codebase a single person can hold in their head**, so shipping stays cheap.
- **An AI layer with a measurable hit rate**, which is the only way the AI story is worth
  anything to a buyer.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Deleting 24 → 8 factors reads as a downgrade | Ship the scorecard first. "8 factors we can prove" beats "24 we can't" — but only if the proof is visible. Frame externally as *the same signal, now measured*. |
| 90 days before any evidence exists | Phase 0/2/3 deliver a better product immediately regardless; Phase 1 runs in the background from week 1. Retroactive backfill (`retroactive.py` already exists) can seed history — but it must be **stored and labelled separately** from live forward records, never mixed into the IC dataset. |
| The signal turns out to have no alpha | This is the *point*. Finding out in 90 days for near-zero cost is the good outcome. A system that cannot report failure cannot report success either. |
| Free-tier data quality (yfinance) is weaker | Accept it and record coverage. A weaker signal honestly measured beats a stronger one nobody can verify. Finnhub stays available as opt-in enhancement. |
| Sunk-cost pull toward the deleted code | It is in git history, and this plan names the recovery path (quarantine, not delete, for anything with a real source). |

---

## 9. Decisions needed from you

1. **Delete vs. quarantine** the ~10 unsourceable factors. Plan assumes: quarantine those
   with a plausible paid-data path, delete the rest.
2. **Universe size** for the daily job. Plan assumes 100 liquid US tickers — small enough
   to run free and fast, large enough for IC to mean something.
3. **Is the web UI still the product, or is the API?** Plan assumes API/skill is the
   product and the 3-page UI is the demo. This is the biggest strategic assumption here.
4. **Public scorecard or private?** Plan assumes public — that is where the defensibility
   comes from, and it is also the commitment device that keeps the discipline honest.
5. **Free-tier-only, or keep Finnhub paid as a first-class path?** Plan assumes
   free-tier-must-work, premium-enhances.

Phase 0 requires none of these answers and can start immediately.

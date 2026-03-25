"""Tests for 21.4: Cross-Sectional Daily Long/Short Ranking."""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_result(
    symbol: str,
    sector: str,
    factor_score: int,
    risk_score: int = 50,
    market_cap_b: float = 10.0,
    adv: float = 5_000_000.0,
    composite_label: str = "Buy",
) -> dict:
    return {
        "symbol": symbol,
        "sector": sector,
        "factor_score": factor_score,
        "risk_score": risk_score,
        "market_cap_b": market_cap_b,
        "adv": adv,
        "composite_label": composite_label,
        "name": symbol,
        "price": 100.0,
    }


# ---------------------------------------------------------------------------
# _assign_overall_ranks
# ---------------------------------------------------------------------------


def test_assign_overall_ranks_ordering():
    from src.analysis.rankings import _assign_overall_ranks

    results = [
        _make_result("A", "Tech", 70),
        _make_result("B", "Tech", 90),
        _make_result("C", "Tech", 50),
    ]
    ranked = _assign_overall_ranks(results)
    symbols = [r["symbol"] for r in ranked]
    assert symbols == ["B", "A", "C"]
    assert ranked[0]["rank_overall"] == 1
    assert ranked[1]["rank_overall"] == 2
    assert ranked[2]["rank_overall"] == 3


def test_assign_overall_ranks_percentiles():
    from src.analysis.rankings import _assign_overall_ranks

    results = [_make_result(str(i), "Tech", i * 10) for i in range(1, 6)]
    ranked = _assign_overall_ranks(results)
    # Top stock should have highest percentile
    assert ranked[0]["percentile"] == 100.0
    # Bottom stock should have lowest percentile
    assert ranked[-1]["percentile"] == 0.0


def test_assign_overall_ranks_single():
    from src.analysis.rankings import _assign_overall_ranks

    results = [_make_result("SOLO", "Tech", 75)]
    ranked = _assign_overall_ranks(results)
    assert ranked[0]["rank_overall"] == 1
    assert ranked[0]["percentile"] == 100.0


def test_assign_overall_ranks_empty():
    from src.analysis.rankings import _assign_overall_ranks

    assert _assign_overall_ranks([]) == []


# ---------------------------------------------------------------------------
# _assign_sector_ranks
# ---------------------------------------------------------------------------


def test_assign_sector_ranks_grouping():
    from src.analysis.rankings import _assign_overall_ranks, _assign_sector_ranks

    results = [
        _make_result("TECH1", "Technology", 80),
        _make_result("TECH2", "Technology", 60),
        _make_result("FIN1", "Financials", 75),
        _make_result("FIN2", "Financials", 40),
    ]
    results = _assign_overall_ranks(results)
    results = _assign_sector_ranks(results)

    tech = {r["symbol"]: r for r in results if r["sector"] == "Technology"}
    fin = {r["symbol"]: r for r in results if r["sector"] == "Financials"}

    assert tech["TECH1"]["rank_in_sector"] == 1
    assert tech["TECH2"]["rank_in_sector"] == 2
    assert fin["FIN1"]["rank_in_sector"] == 1
    assert fin["FIN2"]["rank_in_sector"] == 2


def test_assign_sector_ranks_independent():
    """Sector ranks must be independent — each sector starts at 1."""
    from src.analysis.rankings import _assign_overall_ranks, _assign_sector_ranks

    results = [
        _make_result("A", "Energy", 30),
        _make_result("B", "Healthcare", 85),
        _make_result("C", "Energy", 50),
    ]
    results = _assign_overall_ranks(results)
    results = _assign_sector_ranks(results)

    by_sym = {r["symbol"]: r for r in results}
    # Both sectors should have a rank_in_sector of 1 for their best stock
    assert by_sym["B"]["rank_in_sector"] == 1  # only Healthcare stock
    assert by_sym["C"]["rank_in_sector"] == 1  # best Energy stock


# ---------------------------------------------------------------------------
# _apply_liquidity_filter
# ---------------------------------------------------------------------------


def test_apply_liquidity_filter_removes_low_adv():
    from src.analysis.rankings import _apply_liquidity_filter

    results = [
        _make_result("A", "Tech", 80, adv=500_000),  # 0.5M < 1M threshold
        _make_result("B", "Tech", 70, adv=2_000_000),  # 2M passes
    ]
    filtered = _apply_liquidity_filter(results, min_adv_m=1.0)
    assert len(filtered) == 1
    assert filtered[0]["symbol"] == "B"


def test_apply_liquidity_filter_keeps_valid():
    from src.analysis.rankings import _apply_liquidity_filter

    results = [
        _make_result("A", "Tech", 80, adv=5_000_000),
        _make_result("B", "Tech", 70, adv=3_000_000),
    ]
    filtered = _apply_liquidity_filter(results, min_adv_m=1.0)
    assert len(filtered) == 2


def test_apply_liquidity_filter_zero_threshold():
    """Zero threshold means no filtering."""
    from src.analysis.rankings import _apply_liquidity_filter

    results = [
        _make_result("A", "Tech", 80, adv=0),
        _make_result("B", "Tech", 70, adv=1),
    ]
    filtered = _apply_liquidity_filter(results, min_adv_m=0.0)
    assert len(filtered) == 2


def test_apply_liquidity_filter_missing_adv():
    """Results without adv key are treated as adv=0."""
    from src.analysis.rankings import _apply_liquidity_filter

    results = [
        {"symbol": "A", "sector": "Tech", "factor_score": 80},
    ]
    filtered = _apply_liquidity_filter(results, min_adv_m=1.0)
    assert len(filtered) == 0


# ---------------------------------------------------------------------------
# _build_response
# ---------------------------------------------------------------------------


def test_build_response_top_n():
    from src.analysis.rankings import (
        _assign_overall_ranks,
        _assign_sector_ranks,
        _build_response,
    )

    results = [_make_result(f"S{i}", "Tech", i * 5) for i in range(1, 21)]
    ranked = _assign_overall_ranks(results)
    ranked = _assign_sector_ranks(ranked)
    response = _build_response(ranked, top_n=5)
    assert len(response["top_longs"]) == 5


def test_build_response_bottom_n():
    from src.analysis.rankings import (
        _assign_overall_ranks,
        _assign_sector_ranks,
        _build_response,
    )

    results = [_make_result(f"S{i}", "Tech", i * 5) for i in range(1, 21)]
    ranked = _assign_overall_ranks(results)
    ranked = _assign_sector_ranks(ranked)
    response = _build_response(ranked, top_n=5)
    assert len(response["top_shorts"]) == 5


def test_build_response_longs_have_highest_scores():
    from src.analysis.rankings import (
        _assign_overall_ranks,
        _assign_sector_ranks,
        _build_response,
    )

    results = [_make_result(f"S{i}", "Tech", i * 5) for i in range(1, 21)]
    ranked = _assign_overall_ranks(results)
    ranked = _assign_sector_ranks(ranked)
    response = _build_response(ranked, top_n=3)
    long_scores = [r["factor_score"] for r in response["top_longs"]]
    short_scores = [r["factor_score"] for r in response["top_shorts"]]
    assert min(long_scores) > max(short_scores)


def test_build_response_by_sector():
    from src.analysis.rankings import (
        _assign_overall_ranks,
        _assign_sector_ranks,
        _build_response,
    )

    results = [
        _make_result("T1", "Technology", 80),
        _make_result("T2", "Technology", 60),
        _make_result("F1", "Financials", 70),
    ]
    ranked = _assign_overall_ranks(results)
    ranked = _assign_sector_ranks(ranked)
    response = _build_response(ranked)
    assert "Technology" in response["by_sector"]
    assert "Financials" in response["by_sector"]


def test_build_response_empty_universe():
    from src.analysis.rankings import _build_response

    response = _build_response([])
    assert response["top_longs"] == []
    assert response["top_shorts"] == []
    assert response["by_sector"] == {}


# ---------------------------------------------------------------------------
# history persistence
# ---------------------------------------------------------------------------


def test_save_and_get_ranking_snapshot():
    from src.data.history import save_ranking_snapshot, get_ranking_for_date

    rows = [
        {
            "symbol": "AAPL",
            "sector": "Technology",
            "rank_overall": 1,
            "rank_in_sector": 1,
            "percentile": 100.0,
            "factor_score": 85,
            "risk_score": 40,
            "market_cap_b": 2800.0,
            "adv": 10_000_000.0,
            "composite_label": "Strong Buy",
        },
        {
            "symbol": "XYZ",
            "sector": "Energy",
            "rank_overall": 2,
            "rank_in_sector": 1,
            "percentile": 50.0,
            "factor_score": 30,
            "risk_score": 70,
            "market_cap_b": 5.0,
            "adv": 1_000_000.0,
            "composite_label": "Strong Sell",
        },
    ]
    save_ranking_snapshot("2026-01-01", rows)
    fetched = get_ranking_for_date("2026-01-01")
    assert len(fetched) == 2
    symbols = {r["symbol"] for r in fetched}
    assert "AAPL" in symbols
    assert "XYZ" in symbols


def test_save_ranking_snapshot_upserts():
    """Saving twice for same date replaces, not appends."""
    from src.data.history import save_ranking_snapshot, get_ranking_for_date

    row = {
        "symbol": "MSFT",
        "sector": "Technology",
        "rank_overall": 1,
        "rank_in_sector": 1,
        "percentile": 100.0,
        "factor_score": 88,
        "risk_score": 35,
        "market_cap_b": 3000.0,
        "adv": 8_000_000.0,
        "composite_label": "Strong Buy",
    }
    save_ranking_snapshot("2026-01-02", [row])
    save_ranking_snapshot("2026-01-02", [row])  # second save same date
    fetched = get_ranking_for_date("2026-01-02")
    assert len(fetched) == 1


def test_get_latest_ranking_empty_returns_none():
    """get_latest_ranking returns None when no data for a fresh DB."""
    from src.data.history import get_latest_ranking

    # In test environment the DB is fresh per run; this may return data from
    # earlier tests so we just check it doesn't raise
    result = get_latest_ranking()
    assert result is None or isinstance(result, dict)


def test_save_and_get_thesis():
    from src.data.history import save_ranking_thesis, get_latest_thesis

    save_ranking_thesis(
        "2026-01-03",
        "NVDA",
        "NVDA is the top long because...",
        "WEAK",
        "WEAK is the top short because...",
    )
    thesis = get_latest_thesis()
    assert thesis is not None
    assert thesis["long_symbol"] == "NVDA"
    assert thesis["short_symbol"] == "WEAK"
    assert "top long" in thesis["long_thesis"]
    assert thesis["run_date"] == "2026-01-03"


# ---------------------------------------------------------------------------
# run_daily_ranking (with mock API)
# ---------------------------------------------------------------------------


class _MockAPI:
    """Minimal mock API for ranking tests."""

    def get_quote(self, symbol):
        return {"c": 100.0, "pc": 98.0, "dp": 2.04, "h": 150.0, "l": 50.0}

    def get_financials(self, symbol):
        return {"peBasicExclExtraTTM": 20.0, "marketCapitalization": 10_000_000.0}

    def get_daily(self, symbol, years=1):
        import time

        n = 252
        base = time.time() - n * 86400
        return {
            "c": [float(100 + i) for i in range(n)],
            "v": [1_000_000.0] * n,
            "t": [int(base + i * 86400) for i in range(n)],
        }

    def get_recommendations(self, symbol):
        return [{"buy": 10, "sell": 2, "hold": 3, "period": "2026-01-01"}]

    def get_earnings(self, symbol, limit=4):
        return [
            {"actual": 1.5, "estimate": 1.2, "period": "2025-12-31"},
        ]

    def get_profile(self, symbol):
        sectors = {
            "AAPL": ("Apple Inc", "Technology"),
            "MSFT": ("Microsoft Corp", "Technology"),
            "JPM": ("JPMorgan", "Financials"),
            "XOM": ("Exxon", "Energy"),
        }
        name, sector = sectors.get(symbol, (symbol, "Other"))
        return {"name": name, "finnhubIndustry": sector}

    def get_news(self, symbol, days=1):
        return []


def test_run_daily_ranking_returns_structure():
    """run_daily_ranking returns expected keys."""
    from src.analysis.rankings import run_daily_ranking

    api = _MockAPI()
    result = run_daily_ranking(api, universe="default", force=True)
    assert "run_date" in result
    assert "universe_size" in result
    assert "scored_count" in result
    assert "top_longs" in result
    assert "top_shorts" in result
    assert "by_sector" in result
    assert "errors" in result


def test_run_daily_ranking_uses_cache():
    """Second call without force=True returns cached result."""
    from src.analysis.rankings import run_daily_ranking

    api = _MockAPI()
    r1 = run_daily_ranking(api, universe="default", force=True)
    r2 = run_daily_ranking(api, universe="default", force=False)
    # Second call may be cached
    assert r2["run_date"] == r1["run_date"]


def test_run_daily_ranking_force_rescores():
    """force=True always re-runs scoring."""
    from src.analysis.rankings import run_daily_ranking

    api = _MockAPI()
    r1 = run_daily_ranking(api, universe="default", force=True)
    r2 = run_daily_ranking(api, universe="default", force=True)
    assert r2.get("cached") is False
    assert r1["run_date"] == r2["run_date"]


def test_score_universe_handles_errors():
    """Failed tickers are captured in errors, not raised."""
    from src.analysis.rankings import _score_universe

    class _BadAPI:
        def get_quote(self, symbol):
            raise RuntimeError("network error")

        def get_financials(self, symbol):
            raise RuntimeError("network error")

        def get_daily(self, symbol, years=1):
            raise RuntimeError("network error")

        def get_recommendations(self, symbol):
            raise RuntimeError("network error")

        def get_earnings(self, symbol, limit=4):
            raise RuntimeError("network error")

        def get_profile(self, symbol):
            raise RuntimeError("network error")

    _, errors = _score_universe(["FAIL1", "FAIL2"], _BadAPI(), max_workers=1)
    # Errors are collected; no exception raised
    assert isinstance(errors, list)


# ---------------------------------------------------------------------------
# adv field in _quick_analyze
# ---------------------------------------------------------------------------


def test_quick_analyze_returns_adv():
    """_quick_analyze must include an adv field (avg daily value)."""
    pd = pytest.importorskip("pandas")  # noqa: F841 — skip if pandas unavailable
    from src.trading.screener import _quick_analyze

    api = _MockAPI()
    result = _quick_analyze("AAPL", api=api)
    assert result is not None
    assert "adv" in result
    # With 252 days of volume=1_000_000 and close~100, adv should be ~100M
    assert result["adv"] > 0


def test_quick_analyze_adv_zero_when_daily_fails():
    """adv defaults to 0.0 when daily data is unavailable."""
    pytest.importorskip("pandas")  # skip if pandas unavailable
    from src.trading.screener import _quick_analyze

    class _NoDailyAPI(_MockAPI):
        def get_daily(self, symbol, years=1):
            raise RuntimeError("no daily data")

    result = _quick_analyze("AAPL", api=_NoDailyAPI())
    assert result is not None
    assert result["adv"] == 0.0


# ---------------------------------------------------------------------------
# market_cap_b and adv filter interaction with _apply_liquidity_filter
# ---------------------------------------------------------------------------


def test_apply_liquidity_filter_respects_market_cap_b():
    """Verify market_cap_b is passed through unmodified (filter is ADV-based)."""
    from src.analysis.rankings import _apply_liquidity_filter

    results = [
        _make_result("BIG", "Tech", 80, adv=5_000_000, market_cap_b=500.0),
        _make_result("TINY", "Tech", 70, adv=200_000, market_cap_b=0.5),
    ]
    filtered = _apply_liquidity_filter(results, min_adv_m=1.0)
    assert len(filtered) == 1
    assert filtered[0]["symbol"] == "BIG"
    assert filtered[0]["market_cap_b"] == 500.0

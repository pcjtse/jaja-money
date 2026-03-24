"""Tests for signal_validity.py (21.3)."""

from __future__ import annotations

from datetime import datetime, timedelta
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_history(tmp_path, monkeypatch):
    """Redirect history DB to a temp directory for isolation."""
    import src.data.history as h

    monkeypatch.setattr(h, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(h, "_DB_FILE", tmp_path / "history.db")
    h._ensure_table()
    h._ensure_signal_returns_table()
    yield


def _make_prices(start_date: str, n_days: int = 200, start_price: float = 100.0) -> dict:
    """Generate a synthetic {date: price} dict starting from start_date."""
    prices = {}
    base = datetime.strptime(start_date, "%Y-%m-%d")
    price = start_price
    for i in range(n_days):
        day = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        # Gently trending up 0.05% per day
        price *= 1.0005
        prices[day] = round(price, 2)
    return prices


# ---------------------------------------------------------------------------
# compute_forward_return
# ---------------------------------------------------------------------------


def test_compute_forward_return_basic():
    from src.analysis.signal_validity import compute_forward_return

    prices = _make_prices("2024-01-01", n_days=200)
    result = compute_forward_return(
        symbol="AAPL",
        signal_date="2024-01-01",
        price_at_signal=prices["2024-01-01"],
        prices=prices,
    )
    # All three periods should have a return
    assert result["return_21d"] is not None
    assert result["return_63d"] is not None
    assert result["return_126d"] is not None
    # With a gentle uptrend, all returns should be positive
    assert result["return_21d"] > 0
    assert result["return_63d"] > 0
    assert result["return_126d"] > 0


def test_compute_forward_return_missing_future():
    """If price data ends before the horizon, returns should be None."""
    from src.analysis.signal_validity import compute_forward_return

    # Only 10 days of prices — not enough for any horizon
    prices = _make_prices("2024-01-01", n_days=10)
    result = compute_forward_return(
        symbol="AAPL",
        signal_date="2024-01-01",
        price_at_signal=100.0,
        prices=prices,
    )
    assert result["return_21d"] is None
    assert result["return_63d"] is None
    assert result["return_126d"] is None


def test_compute_forward_return_zero_price():
    """Zero or None price_at_signal should return all None."""
    from src.analysis.signal_validity import compute_forward_return

    prices = _make_prices("2024-01-01", n_days=200)
    result = compute_forward_return(
        symbol="AAPL",
        signal_date="2024-01-01",
        price_at_signal=0.0,
        prices=prices,
    )
    assert all(v is None for v in result.values())


def test_compute_forward_return_negative_return():
    """Verify negative returns are computed correctly."""
    from src.analysis.signal_validity import compute_forward_return

    # Flat prices then drop
    prices: dict[str, float] = {}
    base = datetime.strptime("2024-01-01", "%Y-%m-%d")
    for i in range(200):
        day = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        prices[day] = 100.0 if i < 30 else 80.0  # 20% drop after day 30

    result = compute_forward_return(
        symbol="TEST",
        signal_date="2024-01-01",
        price_at_signal=100.0,
        prices=prices,
    )
    assert result["return_63d"] is not None
    assert result["return_63d"] < 0


# ---------------------------------------------------------------------------
# upsert / get_signal_returns
# ---------------------------------------------------------------------------


def test_upsert_and_get_signal_returns():
    from src.data.history import upsert_signal_return, get_signal_returns

    upsert_signal_return(
        symbol="AAPL",
        signal_date="2024-01-01",
        signal_score=75,
        price_at_signal=150.0,
        return_21d=2.5,
        return_63d=5.0,
        return_126d=8.0,
    )
    rows = get_signal_returns()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["return_21d"] == pytest.approx(2.5)


def test_upsert_overwrites_existing():
    from src.data.history import upsert_signal_return, get_signal_returns

    upsert_signal_return("AAPL", "2024-01-01", 70, 150.0, return_21d=1.0)
    upsert_signal_return("AAPL", "2024-01-01", 70, 150.0, return_21d=3.0)
    rows = get_signal_returns()
    assert len(rows) == 1
    assert rows[0]["return_21d"] == pytest.approx(3.0)


def test_get_signal_returns_filter_by_symbol():
    from src.data.history import upsert_signal_return, get_signal_returns

    upsert_signal_return("AAPL", "2024-01-01", 70, 150.0)
    upsert_signal_return("MSFT", "2024-01-01", 65, 300.0)
    aapl_rows = get_signal_returns("AAPL")
    assert len(aapl_rows) == 1
    assert aapl_rows[0]["symbol"] == "AAPL"


# ---------------------------------------------------------------------------
# compute_quartile_analysis
# ---------------------------------------------------------------------------


def _seed_signal_returns(n: int = 40) -> None:
    """Insert n synthetic signal return rows covering a range of scores."""
    from src.data.history import upsert_signal_return

    base = datetime.strptime("2023-01-01", "%Y-%m-%d")
    for i in range(n):
        score = 20 + i * 2  # scores 20..98
        # Higher score → higher return (monotonic relationship)
        ret_21 = (score - 50) * 0.1  # -3% to +4.8%
        ret_63 = (score - 50) * 0.2
        ret_126 = (score - 50) * 0.3
        date = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        upsert_signal_return(
            symbol="SYM",
            signal_date=date,
            signal_score=score,
            price_at_signal=100.0,
            return_21d=ret_21,
            return_63d=ret_63,
            return_126d=ret_126,
        )


def test_quartile_analysis_returns_four_buckets():
    from src.analysis.signal_validity import compute_quartile_analysis

    _seed_signal_returns(40)
    result = compute_quartile_analysis(horizon_days=63)
    assert result["sample_size"] == 40
    assert len(result["quartiles"]) == 4


def test_quartile_analysis_monotonic_with_score():
    """With a perfectly monotonic score→return relationship, Q4 > Q1."""
    from src.analysis.signal_validity import compute_quartile_analysis

    _seed_signal_returns(40)
    result = compute_quartile_analysis(horizon_days=63)
    quartiles = result["quartiles"]
    q1_median = quartiles[0]["median_return"]
    q4_median = quartiles[3]["median_return"]
    assert q4_median > q1_median


def test_quartile_analysis_insufficient_data():
    """Fewer than 4 rows should return empty quartiles."""
    from src.analysis.signal_validity import compute_quartile_analysis
    from src.data.history import upsert_signal_return

    upsert_signal_return("X", "2024-01-01", 50, 100.0, return_63d=1.0)
    result = compute_quartile_analysis(horizon_days=63)
    assert result["quartiles"] == []


# ---------------------------------------------------------------------------
# compute_spearman_correlations
# ---------------------------------------------------------------------------


def test_spearman_detects_positive_correlation():
    from src.analysis.signal_validity import compute_spearman_correlations

    _seed_signal_returns(30)
    corrs = compute_spearman_correlations()
    corr_63 = next(c for c in corrs if c["horizon_days"] == 63)
    # Perfectly monotonic data → ρ close to 1.0
    assert corr_63["correlation"] is not None
    assert corr_63["correlation"] > 0.9


def test_spearman_insufficient_data():
    from src.analysis.signal_validity import compute_spearman_correlations
    from src.data.history import upsert_signal_return

    # Fewer than 5 rows
    upsert_signal_return("X", "2024-01-01", 50, 100.0, return_21d=1.0, return_63d=1.0)
    corrs = compute_spearman_correlations()
    for c in corrs:
        assert c["correlation"] is None or c["sample_size"] < 5


# ---------------------------------------------------------------------------
# compute_ic_trend
# ---------------------------------------------------------------------------


def _seed_monthly_returns(months: int = 15) -> None:
    """Seed rows across multiple months for IC trend tests."""
    from src.data.history import upsert_signal_return

    base = datetime.strptime("2023-01-01", "%Y-%m-%d")
    idx = 0
    for m in range(months):
        # 5 signals per month
        for d in range(5):
            date = (base + timedelta(days=m * 30 + d)).strftime("%Y-%m-%d")
            score = 20 + idx % 80
            ret = (score - 50) * 0.1
            upsert_signal_return(
                "SYM2",
                date,
                score,
                100.0,
                return_63d=ret,
            )
            idx += 1


def test_ic_trend_returns_months_list():
    from src.analysis.signal_validity import compute_ic_trend

    _seed_monthly_returns(15)
    result = compute_ic_trend(horizon_days=63)
    assert len(result["months"]) > 0


def test_ic_trend_insufficient_data():
    from src.analysis.signal_validity import compute_ic_trend

    result = compute_ic_trend(horizon_days=63)
    assert result["trend"] == "Insufficient data"
    assert result["latest_ic"] is None


# ---------------------------------------------------------------------------
# get_signal_quality_summary
# ---------------------------------------------------------------------------


def test_signal_quality_summary_no_data():
    from src.analysis.signal_validity import get_signal_quality_summary

    result = get_signal_quality_summary()
    assert result["has_data"] is False


def test_signal_quality_summary_with_data():
    from src.analysis.signal_validity import get_signal_quality_summary

    _seed_signal_returns(20)
    result = get_signal_quality_summary()
    assert result["has_data"] is True
    assert result["sample_size"] == 20


# ---------------------------------------------------------------------------
# backfill_all_forward_returns — mock yfinance
# ---------------------------------------------------------------------------


def test_backfill_uses_cached_prices(monkeypatch):
    """backfill should not re-process rows already in signal_returns."""
    from src.data.history import upsert_signal_return

    # Pre-seed analysis_history with an old signal
    old_date = (datetime.utcnow() - timedelta(days=200)).strftime("%Y-%m-%d")
    import src.data.history as h

    with h._connect() as conn:
        conn.execute(
            """INSERT INTO analysis_history
               (symbol, date, timestamp, price, factor_score, risk_score)
               VALUES (?,?,?,?,?,?)""",
            ("TST", old_date, 0, 100.0, 60, 40),
        )

    # Pre-cache the return so backfill should skip it
    upsert_signal_return("TST", old_date, 60, 100.0, return_21d=1.0, return_63d=2.0, return_126d=3.0)

    # Mock yfinance so it's not actually called
    mock_called = []

    def _mock_fetch(symbol: str, years: int = 2) -> dict:
        mock_called.append(symbol)
        return {}

    import src.analysis.signal_validity as sv

    monkeypatch.setattr(sv, "_fetch_close_prices", _mock_fetch)

    from src.analysis.signal_validity import backfill_all_forward_returns

    result = backfill_all_forward_returns()
    # Should be skipped since it's already cached
    assert result["skipped"] >= 1
    assert "TST" not in mock_called

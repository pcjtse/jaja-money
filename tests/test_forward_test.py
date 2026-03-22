"""Tests for forward_test.py (P22.1) — paper portfolio management."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures — redirect the DB to a temp directory so tests are isolated
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_db(tmp_path, monkeypatch):
    """Redirect both history and forward_test to a fresh temp DB."""
    import src.data.history as h

    monkeypatch.setattr(h, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(h, "_DB_FILE", tmp_path / "history.db")
    h._ensure_table()
    h._ensure_paper_tables()
    yield


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------


def test_create_portfolio_returns_id():
    from src.analysis.forward_test import create_portfolio

    pid = create_portfolio("My Portfolio")
    assert isinstance(pid, int)
    assert pid > 0


def test_list_portfolios_empty():
    from src.analysis.forward_test import list_portfolios

    assert list_portfolios() == []


def test_list_portfolios_after_create():
    from src.analysis.forward_test import create_portfolio, list_portfolios

    create_portfolio("Alpha")
    create_portfolio("Beta")
    pfs = list_portfolios()
    names = [p["name"] for p in pfs]
    assert "Alpha" in names
    assert "Beta" in names
    assert len(pfs) == 2


def test_rename_portfolio():
    from src.analysis.forward_test import (
        create_portfolio,
        rename_portfolio,
        list_portfolios,
    )

    pid = create_portfolio("Old Name")
    result = rename_portfolio(pid, "New Name")
    assert result is True
    pfs = list_portfolios()
    assert pfs[0]["name"] == "New Name"


def test_delete_portfolio():
    from src.analysis.forward_test import (
        create_portfolio,
        delete_portfolio,
        list_portfolios,
    )

    pid = create_portfolio("To Delete")
    assert len(list_portfolios()) == 1
    result = delete_portfolio(pid)
    assert result is True
    assert list_portfolios() == []


def test_delete_portfolio_cascades_trades():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        delete_portfolio,
        get_open_positions,
    )

    pid = create_portfolio("Cascade Test")
    add_position(pid, "AAPL", 150.0)
    delete_portfolio(pid)
    # After deletion, querying positions should return empty list (no error)
    assert get_open_positions(pid) == []


# ---------------------------------------------------------------------------
# Position management
# ---------------------------------------------------------------------------


def test_add_position_returns_trade_id():
    from src.analysis.forward_test import create_portfolio, add_position

    pid = create_portfolio("P1")
    tid = add_position(pid, "AAPL", 150.0)
    assert isinstance(tid, int)
    assert tid > 0


def test_add_position_symbol_normalised():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        get_open_positions,
    )

    pid = create_portfolio("P2")
    add_position(pid, "aapl", 150.0)
    positions = get_open_positions(pid)
    assert positions[0]["symbol"] == "AAPL"


def test_add_position_stores_scores():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        get_open_positions,
    )

    pid = create_portfolio("P3")
    add_position(pid, "MSFT", 300.0, factor_score=75, risk_score=25)
    pos = get_open_positions(pid)[0]
    assert pos["factor_score_entry"] == 75
    assert pos["risk_score_entry"] == 25


def test_get_open_positions_empty():
    from src.analysis.forward_test import create_portfolio, get_open_positions

    pid = create_portfolio("Empty")
    assert get_open_positions(pid) == []


def test_close_position():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        close_position,
        get_open_positions,
        get_closed_trades,
    )

    pid = create_portfolio("Close Test")
    tid = add_position(pid, "TSLA", 200.0, shares=2.0)
    assert len(get_open_positions(pid)) == 1

    result = close_position(tid, 250.0)
    assert result is True
    assert get_open_positions(pid) == []

    closed = get_closed_trades(pid)
    assert len(closed) == 1
    assert closed[0]["exit_price"] == 250.0
    assert abs(closed[0]["pnl_pct"] - 25.0) < 0.01  # (250-200)/200*100 = 25%


def test_close_position_negative_pnl():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        close_position,
        get_closed_trades,
    )

    pid = create_portfolio("Loss Test")
    tid = add_position(pid, "NVDA", 100.0)
    close_position(tid, 80.0)
    closed = get_closed_trades(pid)
    assert closed[0]["pnl_pct"] == pytest.approx(-20.0)


def test_multiple_positions():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        get_open_positions,
    )

    pid = create_portfolio("Multi")
    add_position(pid, "AAPL", 150.0)
    add_position(pid, "MSFT", 300.0)
    add_position(pid, "GOOGL", 2800.0)
    positions = get_open_positions(pid)
    assert len(positions) == 3
    symbols = {p["symbol"] for p in positions}
    assert symbols == {"AAPL", "MSFT", "GOOGL"}


# ---------------------------------------------------------------------------
# Equity curve / snapshots
# ---------------------------------------------------------------------------


def test_snapshot_portfolio_writes_history():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        snapshot_portfolio,
        get_equity_curve,
    )

    pid = create_portfolio("Snapshot Test")
    add_position(pid, "AAPL", 150.0, shares=2.0)
    snapshot_portfolio(pid, {"AAPL": 160.0})

    curve = get_equity_curve(pid)
    assert len(curve) == 1
    assert curve[0]["total_value"] == pytest.approx(320.0)  # 160 * 2


def test_snapshot_fallback_to_entry_price():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        snapshot_portfolio,
        get_equity_curve,
    )

    pid = create_portfolio("Fallback Test")
    add_position(pid, "MSFT", 300.0, shares=1.0)
    # No price for MSFT — should fall back to entry price
    snapshot_portfolio(pid, {})

    curve = get_equity_curve(pid)
    assert curve[0]["total_value"] == pytest.approx(300.0)


def test_snapshot_upsert_same_day():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        snapshot_portfolio,
        get_equity_curve,
    )

    pid = create_portfolio("Upsert Test")
    add_position(pid, "AAPL", 150.0, shares=1.0)
    snapshot_portfolio(pid, {"AAPL": 160.0})
    snapshot_portfolio(pid, {"AAPL": 170.0})  # second snapshot same day

    curve = get_equity_curve(pid)
    assert len(curve) == 1  # upserted, not duplicated
    assert curve[0]["total_value"] == pytest.approx(170.0)


def test_equity_curve_empty_no_snapshots():
    from src.analysis.forward_test import create_portfolio, get_equity_curve

    pid = create_portfolio("No Snapshots")
    assert get_equity_curve(pid) == []


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_calc_stats_empty_curve():
    from src.analysis.forward_test import _calc_stats

    stats = _calc_stats([], [])
    assert stats["total_return_pct"] == 0.0
    assert stats["sharpe_ratio"] is None
    assert stats["win_rate_pct"] is None


def test_calc_stats_single_point():
    from src.analysis.forward_test import _calc_stats

    stats = _calc_stats([{"date": "2026-01-01", "total_value": 1000.0}], [])
    assert stats["total_return_pct"] == 0.0


def test_calc_stats_positive_return():
    from src.analysis.forward_test import _calc_stats

    curve = [
        {"date": "2026-01-01", "total_value": 1000.0},
        {"date": "2026-04-01", "total_value": 1100.0},
    ]
    stats = _calc_stats(curve, [])
    assert stats["total_return_pct"] == pytest.approx(10.0)


def test_calc_stats_win_rate():
    from src.analysis.forward_test import _calc_stats

    closed = [
        {"pnl_pct": 10.0},
        {"pnl_pct": -5.0},
        {"pnl_pct": 20.0},
        {"pnl_pct": 3.0},
    ]
    curve = [
        {"date": "2026-01-01", "total_value": 1000.0},
        {"date": "2026-04-01", "total_value": 1100.0},
    ]
    stats = _calc_stats(curve, closed)
    assert stats["win_rate_pct"] == pytest.approx(75.0)
    assert stats["trade_count"] == 4


def test_calc_stats_max_drawdown():
    from src.analysis.forward_test import _calc_stats

    curve = [
        {"date": "2026-01-01", "total_value": 1000.0},
        {"date": "2026-01-02", "total_value": 1200.0},
        {"date": "2026-01-03", "total_value": 900.0},  # 25% drawdown from peak
        {"date": "2026-01-04", "total_value": 1100.0},
    ]
    stats = _calc_stats(curve, [])
    assert stats["max_drawdown_pct"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------


def test_get_portfolio_summary_structure():
    from src.analysis.forward_test import (
        create_portfolio,
        add_position,
        get_portfolio_summary,
    )

    pid = create_portfolio("Summary Test")
    add_position(pid, "AAPL", 150.0, factor_score=70, risk_score=30)

    summary = get_portfolio_summary(pid)
    assert summary["portfolio_id"] == pid
    assert summary["name"] == "Summary Test"
    assert len(summary["open_positions"]) == 1
    assert summary["closed_trades"] == []
    assert "stats" in summary
    assert "equity_curve" in summary


def test_get_portfolio_summary_unknown_id():
    from src.analysis.forward_test import get_portfolio_summary

    summary = get_portfolio_summary(99999)
    assert summary["name"] == "Unknown"
    assert summary["open_positions"] == []


# ---------------------------------------------------------------------------
# history.py paper table creation
# ---------------------------------------------------------------------------


def test_ensure_paper_tables_idempotent():
    """Calling _ensure_paper_tables multiple times should not raise."""
    import src.data.history as h

    h._ensure_paper_tables()
    h._ensure_paper_tables()  # second call is a no-op


def test_paper_portfolio_table_exists():
    """Verify the paper_portfolio table was created."""
    import src.data.history as h

    with h._connect() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    names = {t["name"] for t in tables}
    assert "paper_portfolio" in names
    assert "paper_trades" in names
    assert "paper_portfolio_history" in names

"""Tests for P6 backtest enhancements.

Covers:
- P6.3 Transaction costs (gross vs net return, cost fields)
- P6.1 Walk-forward validation (run_walk_forward)
- P6.2 Parameter sensitivity sweep (run_parameter_sweep)
- BacktestResult new fields (gross_return_pct, total_cost_pct, is_insample)
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def _make_df(n=300, trend="up", seed=42):
    rng = np.random.default_rng(seed)
    dates = [datetime(2021, 1, 1) + timedelta(days=i) for i in range(n)]
    if trend == "up":
        prices = [100 + i * 0.3 + rng.normal(0, 0.5) for i in range(n)]
    elif trend == "down":
        prices = [200 - i * 0.3 + rng.normal(0, 0.5) for i in range(n)]
    else:
        prices = [100 + rng.normal(0, 2) for _ in range(n)]
    prices = [max(p, 0.01) for p in prices]
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": prices,
            "High": [p * 1.01 for p in prices],
            "Low": [p * 0.99 for p in prices],
            "Close": prices,
            "Volume": [1_000_000] * n,
        }
    )


# ---------------------------------------------------------------------------
# P6.3: Transaction costs
# ---------------------------------------------------------------------------


def test_backtest_result_has_gross_return_field():
    from backtest import run_backtest

    result = run_backtest(_make_df(300), "TEST", lookback_years=1)
    assert hasattr(result, "gross_return_pct")
    assert isinstance(result.gross_return_pct, float)


def test_backtest_result_has_total_cost_field():
    from backtest import run_backtest

    result = run_backtest(_make_df(300), "TEST", lookback_years=1)
    assert hasattr(result, "total_cost_pct")
    assert result.total_cost_pct >= 0


def test_backtest_result_has_is_insample_field():
    from backtest import run_backtest

    result = run_backtest(_make_df(300), "TEST", lookback_years=1, is_insample=True)
    assert result.is_insample is True


def test_backtest_is_insample_false():
    from backtest import run_backtest

    result = run_backtest(_make_df(300), "TEST", lookback_years=1, is_insample=False)
    assert result.is_insample is False


def test_gross_return_at_least_net_return():
    """Gross return should be >= net return (costs are never negative)."""
    from backtest import run_backtest

    result = run_backtest(
        _make_df(400, "up"),
        "TEST",
        entry_threshold=55,
        exit_threshold=40,
        lookback_years=1,
        commission_pct=0.002,
        slippage_pct=0.001,
    )
    assert result.gross_return_pct >= result.total_return_pct - 0.01  # float tolerance


def test_zero_cost_gross_equals_net():
    """With zero commission and slippage, gross ≈ net return."""
    from backtest import run_backtest

    result = run_backtest(
        _make_df(400, "up"),
        "TEST",
        entry_threshold=55,
        exit_threshold=40,
        lookback_years=1,
        commission_pct=0.0,
        slippage_pct=0.0,
    )
    assert abs(result.gross_return_pct - result.total_return_pct) < 0.01


def test_higher_costs_reduce_net_return():
    """Higher transaction costs should reduce net return."""
    from backtest import run_backtest

    df = _make_df(400, "up", seed=7)
    result_low = run_backtest(
        df,
        "TEST",
        entry_threshold=55,
        exit_threshold=40,
        lookback_years=1,
        commission_pct=0.0,
        slippage_pct=0.0,
    )
    result_high = run_backtest(
        df,
        "TEST",
        entry_threshold=55,
        exit_threshold=40,
        lookback_years=1,
        commission_pct=0.01,
        slippage_pct=0.005,
    )
    # With more trades, higher costs must reduce net return
    if result_low.total_trades > 0:
        assert result_low.total_return_pct >= result_high.total_return_pct


def test_total_cost_grows_with_trades():
    """More trades → more total transaction cost."""
    from backtest import run_backtest

    df = _make_df(400, "up", seed=10)
    # Aggressive thresholds → more trades
    result_aggressive = run_backtest(
        df,
        "TEST",
        entry_threshold=51,
        exit_threshold=49,
        lookback_years=1,
        commission_pct=0.001,
    )
    result_conservative = run_backtest(
        df,
        "TEST",
        entry_threshold=75,
        exit_threshold=20,
        lookback_years=1,
        commission_pct=0.001,
    )
    if result_aggressive.total_trades > result_conservative.total_trades:
        assert result_aggressive.total_cost_pct >= result_conservative.total_cost_pct


# ---------------------------------------------------------------------------
# P6.1: Walk-forward validation
# ---------------------------------------------------------------------------


def test_walk_forward_returns_tuple():
    from backtest import run_walk_forward

    df = _make_df(400)
    result = run_walk_forward(df, "TEST")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_walk_forward_both_results_are_backtest_results():
    from backtest import run_walk_forward, BacktestResult

    df = _make_df(400)
    in_r, out_r = run_walk_forward(df, "TEST")
    assert isinstance(in_r, BacktestResult)
    assert isinstance(out_r, BacktestResult)


def test_walk_forward_insample_flag():
    from backtest import run_walk_forward

    df = _make_df(400)
    in_r, out_r = run_walk_forward(df, "TEST")
    assert in_r.is_insample is True
    assert out_r.is_insample is False


def test_walk_forward_requires_min_data():
    from backtest import run_walk_forward

    df = _make_df(30)  # too few rows
    with pytest.raises(ValueError, match="Insufficient"):
        run_walk_forward(df, "TEST")


def test_walk_forward_in_out_both_have_valid_dates():
    """Both in-sample and out-of-sample results should have non-empty date fields."""
    from backtest import run_walk_forward

    df = _make_df(400)
    in_r, out_r = run_walk_forward(df, "TEST")
    assert in_r.start_date and in_r.end_date
    assert out_r.start_date and out_r.end_date


def test_walk_forward_custom_split():
    from backtest import run_walk_forward

    df = _make_df(400)
    in_r, out_r = run_walk_forward(df, "TEST", insample_pct=0.60)
    assert isinstance(in_r.total_return_pct, float)
    assert isinstance(out_r.total_return_pct, float)


# ---------------------------------------------------------------------------
# P6.2: Parameter sensitivity sweep
# ---------------------------------------------------------------------------


def test_parameter_sweep_returns_expected_keys():
    from backtest import run_parameter_sweep

    df = _make_df(300)
    result = run_parameter_sweep(df, "TEST", lookback_years=1)
    assert "grid_sharpe" in result
    assert "grid_return" in result
    assert "best_params" in result
    assert "boundary_warning" in result


def test_parameter_sweep_best_params_structure():
    from backtest import run_parameter_sweep

    df = _make_df(300)
    result = run_parameter_sweep(df, "TEST", lookback_years=1)
    bp = result["best_params"]
    assert "entry" in bp
    assert "exit" in bp
    assert "sharpe" in bp
    assert "total_return" in bp


def test_parameter_sweep_best_entry_exit_valid():
    from backtest import run_parameter_sweep

    df = _make_df(300)
    result = run_parameter_sweep(df, "TEST", lookback_years=1)
    bp = result["best_params"]
    assert bp["entry"] in [55, 60, 65, 70]
    assert bp["exit"] in [30, 35, 40, 45]


def test_parameter_sweep_grid_is_dataframe():
    from backtest import run_parameter_sweep
    import pandas as pd

    df = _make_df(300)
    result = run_parameter_sweep(df, "TEST", lookback_years=1)
    assert isinstance(result["grid_sharpe"], pd.DataFrame)
    assert isinstance(result["grid_return"], pd.DataFrame)


def test_parameter_sweep_boundary_warning_is_bool():
    from backtest import run_parameter_sweep

    df = _make_df(300)
    result = run_parameter_sweep(df, "TEST", lookback_years=1)
    assert isinstance(result["boundary_warning"], bool)


def test_parameter_sweep_custom_ranges():
    from backtest import run_parameter_sweep

    df = _make_df(300)
    result = run_parameter_sweep(
        df, "TEST", entry_values=[60, 65], exit_values=[30, 35], lookback_years=1
    )
    assert result["best_params"]["entry"] in [60, 65]
    assert result["best_params"]["exit"] in [30, 35]


def test_parameter_sweep_invalid_combos_skipped():
    """Entry ≤ exit combos should be skipped (return None in grid)."""
    from backtest import run_parameter_sweep

    df = _make_df(300)
    # Use entry=40, exit=45 → exit > entry → should be skipped (None)
    result = run_parameter_sweep(
        df, "TEST", entry_values=[40], exit_values=[45], lookback_years=1
    )
    sharpe_val = result["grid_sharpe"].iloc[0, 0]
    assert sharpe_val is None or (
        isinstance(sharpe_val, float) and str(sharpe_val) == "nan"
    )

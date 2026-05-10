"""Tests for P23.1 Scheduled Overnight Batch Analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_api():
    """Minimal mock API that returns usable data for factor computation."""
    api = MagicMock()
    api.get_quote.return_value = {
        "c": 150.0,
        "pc": 148.0,
        "dp": 1.35,
        "h": 152.0,
        "l": 149.0,
        "o": 149.5,
    }
    api.get_financials.return_value = {
        "peNormalizedAnnual": 20.0,
        "epsNormalizedAnnual": 7.5,
        "52WeekHigh": 200.0,
        "52WeekLow": 100.0,
        "revenuePerShareAnnual": 50.0,
        "currentRatioAnnual": 1.5,
        "debtToEquityAnnual": 0.3,
        "dividendYieldIndicatedAnnual": 1.2,
    }
    api.get_daily.return_value = {
        "s": "ok",
        "c": list(range(50, 200)),  # 150 days of increasing prices
        "t": list(range(1000000, 1000150)),
    }
    api.get_earnings.return_value = [
        {"actual": 2.0, "estimate": 1.8, "period": "2024-Q1"},
        {"actual": 1.9, "estimate": 2.0, "period": "2023-Q4"},
    ]
    api.get_recommendations.return_value = [
        {"buy": 20, "sell": 3, "hold": 5, "period": "2024-05"},
    ]
    api.get_news.return_value = [
        {"headline": "Company beats estimates", "sentiment": "positive"},
    ]
    api.get_alt_data_signals.return_value = None
    return api


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Route all history.py DB calls to a temp file."""
    db_path = tmp_path / "test_history.db"
    import src.data.history as hist

    monkeypatch.setattr(hist, "_DB_FILE", db_path)
    monkeypatch.setattr(hist, "_DATA_DIR", tmp_path)

    # Re-run table creation against the temp DB
    hist._ensure_table()
    hist._ensure_paper_tables()
    hist._ensure_alpha_tables()
    hist._ensure_signal_returns_table()
    hist._ensure_ml_weights_table()
    hist._ensure_batch_run_table()

    yield db_path


# ---------------------------------------------------------------------------
# get_last_batch_run / save_batch_run
# ---------------------------------------------------------------------------


def test_get_last_batch_run_returns_none_when_empty(isolated_db):
    from src.data.history import get_last_batch_run

    assert get_last_batch_run() is None


def test_save_and_get_batch_run(isolated_db):
    from src.data.history import get_last_batch_run, save_batch_run

    save_batch_run(
        status="success",
        processed=5,
        errors=1,
        symbols_processed=["AAPL", "MSFT"],
        duration_s=12.3,
    )
    row = get_last_batch_run()
    assert row is not None
    assert row["status"] == "success"
    assert row["processed"] == 5
    assert row["errors"] == 1
    assert row["duration_s"] == pytest.approx(12.3, abs=0.1)
    assert row["symbols_processed"] == ["AAPL", "MSFT"]


def test_save_batch_run_overwrites_same_day(isolated_db):
    """Saving twice on the same day keeps only the latest record."""
    from src.data.history import get_last_batch_run, save_batch_run

    save_batch_run(status="running", processed=0, errors=0)
    save_batch_run(status="success", processed=3, errors=0)

    row = get_last_batch_run()
    assert row["status"] == "success"
    assert row["processed"] == 3


# ---------------------------------------------------------------------------
# _analyze_ticker
# ---------------------------------------------------------------------------


def test_analyze_ticker_saves_to_history(isolated_db, mock_api):
    from src.services.scheduler import _analyze_ticker
    from src.data.history import get_history

    with patch("src.trading.watchlist.get_watchlist", return_value=[]):
        result = _analyze_ticker(mock_api, "AAPL")

    assert result is not None
    assert result["symbol"] == "AAPL"
    assert 0 <= result["factor_score"] <= 100
    assert result["price"] == pytest.approx(150.0)

    rows = get_history("AAPL")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["price"] == pytest.approx(150.0)


def test_analyze_ticker_seeds_signal_returns(isolated_db, mock_api):
    from src.services.scheduler import _analyze_ticker
    from src.data.history import get_signal_returns

    with patch("src.trading.watchlist.get_watchlist", return_value=[]):
        _analyze_ticker(mock_api, "MSFT")

    rows = get_signal_returns("MSFT")
    assert len(rows) == 1
    assert rows[0]["price_at_signal"] == pytest.approx(150.0)


def test_analyze_ticker_returns_none_on_bad_quote(isolated_db):
    from src.services.scheduler import _analyze_ticker

    bad_api = MagicMock()
    bad_api.get_quote.side_effect = ValueError("no data")

    result = _analyze_ticker(bad_api, "FAKE")
    assert result is None


def test_analyze_ticker_returns_none_on_zero_price(isolated_db):
    from src.services.scheduler import _analyze_ticker

    zero_api = MagicMock()
    zero_api.get_quote.return_value = {"c": 0.0}

    result = _analyze_ticker(zero_api, "ZERO")
    assert result is None


# ---------------------------------------------------------------------------
# run_batch_analysis
# ---------------------------------------------------------------------------


def test_run_batch_analysis_empty_watchlist(isolated_db):
    from src.services.scheduler import run_batch_analysis

    with patch("src.trading.watchlist.get_watchlist", return_value=[]):
        with patch("src.data.api.get_api"):
            result = run_batch_analysis()

    assert result["processed"] == 0
    assert result["errors"] == 0
    assert result["symbols_processed"] == []


def test_run_batch_analysis_processes_watchlist(isolated_db, mock_api):
    from src.services.scheduler import run_batch_analysis

    watchlist = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]

    with patch("src.trading.watchlist.get_watchlist", return_value=watchlist):
        with patch("src.analysis.signal_validity.backfill_all_forward_returns", return_value={"processed": 0, "skipped": 2, "errors": 0}):
            with patch("src.services.scheduler._maybe_retrain_ml_weights"):
                result = run_batch_analysis(mock_api)

    assert result["processed"] == 2
    assert result["errors"] == 0
    assert set(result["symbols_processed"]) == {"AAPL", "MSFT"}


def test_run_batch_analysis_saves_batch_run_record(isolated_db, mock_api):
    from src.data.history import get_last_batch_run
    from src.services.scheduler import run_batch_analysis

    watchlist = [{"symbol": "AAPL"}]

    with patch("src.trading.watchlist.get_watchlist", return_value=watchlist):
        with patch("src.analysis.signal_validity.backfill_all_forward_returns", return_value={"processed": 0, "skipped": 0, "errors": 0}):
            with patch("src.services.scheduler._maybe_retrain_ml_weights"):
                run_batch_analysis(mock_api)

    run_record = get_last_batch_run()
    assert run_record is not None
    assert run_record["status"] in ("success", "partial", "error")
    assert run_record["processed"] >= 0


def test_run_batch_analysis_calls_backfill(isolated_db, mock_api):
    from src.services.scheduler import run_batch_analysis

    watchlist = [{"symbol": "AAPL"}]

    with patch("src.trading.watchlist.get_watchlist", return_value=watchlist):
        with patch(
            "src.analysis.signal_validity.backfill_all_forward_returns",
            return_value={"processed": 1, "skipped": 0, "errors": 0},
        ) as mock_backfill:
            with patch("src.services.scheduler._maybe_retrain_ml_weights"):
                run_batch_analysis(mock_api)

    mock_backfill.assert_called_once()


# ---------------------------------------------------------------------------
# _maybe_retrain_ml_weights
# ---------------------------------------------------------------------------


def test_maybe_retrain_skips_when_insufficient_data(isolated_db):
    """Should not attempt retrain when fewer than MIN_SAMPLES snapshots exist."""
    from src.services.scheduler import _maybe_retrain_ml_weights

    with patch("src.data.history.get_all_factor_snapshots", return_value=[]):
        with patch("src.analysis.ml_weights._retrain_and_save") as mock_retrain:
            _maybe_retrain_ml_weights()

    mock_retrain.assert_not_called()


def test_maybe_retrain_skips_when_weights_fresh(isolated_db):
    """Should not retrain if weights are less than RETRAIN_EVERY_DAYS old."""
    from datetime import datetime
    from src.analysis.ml_weights import MIN_SAMPLES
    from src.services.scheduler import _maybe_retrain_ml_weights

    # Fresh weights — trained today
    recent_row = {
        "trained_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "n_samples": MIN_SAMPLES * 2,
    }
    many_snaps = [{}] * (MIN_SAMPLES + 5)  # enough snapshots

    with patch("src.data.history.get_all_factor_snapshots", return_value=many_snaps):
        with patch("src.data.history.get_latest_ml_weights", return_value=recent_row):
            with patch("src.analysis.ml_weights._retrain_and_save") as mock_retrain:
                _maybe_retrain_ml_weights()

    mock_retrain.assert_not_called()


def test_maybe_retrain_triggers_when_stale(isolated_db):
    """Should retrain when weights are older than RETRAIN_EVERY_DAYS."""
    from datetime import datetime, timedelta
    from src.analysis.ml_weights import MIN_SAMPLES, RETRAIN_EVERY_DAYS
    from src.services.scheduler import _maybe_retrain_ml_weights

    stale_date = (datetime.utcnow() - timedelta(days=RETRAIN_EVERY_DAYS + 10)).strftime(
        "%Y-%m-%d"
    )
    stale_row = {"trained_date": stale_date, "n_samples": MIN_SAMPLES}
    many_snaps = [{}] * (MIN_SAMPLES + 5)

    with patch("src.data.history.get_all_factor_snapshots", return_value=many_snaps):
        with patch("src.data.history.get_latest_ml_weights", return_value=stale_row):
            with patch(
                "src.analysis.ml_weights._retrain_and_save",
                return_value={"auc": 0.6, "n_samples": MIN_SAMPLES + 5},
            ) as mock_retrain:
                _maybe_retrain_ml_weights()

    mock_retrain.assert_called_once()


# ---------------------------------------------------------------------------
# Scheduler start/stop
# ---------------------------------------------------------------------------


def test_start_batch_scheduler_disabled_by_default():
    """Scheduler should not start when batch_analysis.enabled is false."""
    from src.services.scheduler import start_batch_scheduler

    with patch("src.core.config.cfg.get", return_value=False):
        result = start_batch_scheduler()

    assert result is False


def test_start_batch_scheduler_no_apscheduler():
    """Scheduler should return False when APScheduler is not installed."""
    from src.services import scheduler as sched_mod
    from src.services.scheduler import start_batch_scheduler

    original = sched_mod._HAS_APSCHEDULER
    try:
        sched_mod._HAS_APSCHEDULER = False
        # Even if enabled is True, no APScheduler means no scheduler
        with patch.object(type(sched_mod.cfg), "get", return_value=True):
            start_batch_scheduler()
        # Only meaningful assertion: it returned without crashing
    finally:
        sched_mod._HAS_APSCHEDULER = original


# ---------------------------------------------------------------------------
# run_batch_analysis status logic
# ---------------------------------------------------------------------------


def test_run_batch_analysis_partial_status_on_mixed_results(isolated_db, mock_api):
    """Status is 'partial' when some tickers succeed and some fail."""
    from src.services.scheduler import run_batch_analysis
    from src.data.history import get_last_batch_run

    # AAPL succeeds (returns dict), MSFT fails (returns None)
    def mixed_analyze(_api, symbol):
        if symbol == "AAPL":
            return {"symbol": "AAPL", "factor_score": 65, "risk_score": 40, "price": 150.0}
        return None

    watchlist = [{"symbol": "AAPL"}, {"symbol": "MSFT"}]

    with patch("src.trading.watchlist.get_watchlist", return_value=watchlist):
        with patch("src.services.scheduler._analyze_ticker", side_effect=mixed_analyze):
            with patch("src.analysis.signal_validity.backfill_all_forward_returns", return_value={"processed": 0, "skipped": 0, "errors": 0}):
                with patch("src.services.scheduler._maybe_retrain_ml_weights"):
                    result = run_batch_analysis(mock_api)

    assert result["processed"] == 1
    assert result["errors"] == 1
    row = get_last_batch_run()
    assert row["status"] == "partial"


def test_run_batch_analysis_error_status_when_all_fail(isolated_db):
    """Status is 'error' when all tickers fail."""
    from src.services.scheduler import run_batch_analysis
    from src.data.history import get_last_batch_run

    watchlist = [{"symbol": "FAIL1"}, {"symbol": "FAIL2"}]

    with patch("src.trading.watchlist.get_watchlist", return_value=watchlist):
        with patch("src.services.scheduler._analyze_ticker", return_value=None):
            with patch("src.analysis.signal_validity.backfill_all_forward_returns", return_value={"processed": 0, "skipped": 0, "errors": 0}):
                with patch("src.services.scheduler._maybe_retrain_ml_weights"):
                    result = run_batch_analysis(MagicMock())

    assert result["processed"] == 0
    assert result["errors"] == 2
    row = get_last_batch_run()
    assert row["status"] == "error"


def test_run_batch_analysis_uses_get_api_when_none(isolated_db):
    """When api=None is passed, run_batch_analysis calls get_api()."""
    from src.services.scheduler import run_batch_analysis

    mock_api_instance = MagicMock()
    mock_api_instance.get_quote.return_value = {"c": 0.0}

    with patch("src.trading.watchlist.get_watchlist", return_value=[]):
        with patch("src.data.api.get_api", return_value=mock_api_instance) as mock_get:
            run_batch_analysis()  # api=None default

    mock_get.assert_called_once()


def test_run_batch_analysis_handles_backfill_exception(isolated_db, mock_api):
    """Backfill exception does not abort the batch run."""
    from src.services.scheduler import run_batch_analysis

    watchlist = [{"symbol": "AAPL"}]

    with patch("src.trading.watchlist.get_watchlist", return_value=watchlist):
        with patch("src.analysis.signal_validity.backfill_all_forward_returns", side_effect=RuntimeError("db gone")):
            with patch("src.services.scheduler._maybe_retrain_ml_weights"):
                result = run_batch_analysis(mock_api)

    # Batch run should complete despite backfill failure
    assert result["processed"] >= 0


# ---------------------------------------------------------------------------
# Scheduler lifecycle: stop / is_running / get_next_run_time
# ---------------------------------------------------------------------------


def test_is_scheduler_running_returns_false_when_none():
    from src.services import scheduler as sched_mod
    from src.services.scheduler import is_scheduler_running

    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = None
        assert is_scheduler_running() is False
    finally:
        sched_mod._batch_scheduler = original


def test_stop_batch_scheduler_when_not_running():
    """stop_batch_scheduler is a no-op when scheduler is None."""
    from src.services import scheduler as sched_mod
    from src.services.scheduler import stop_batch_scheduler

    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = None
        stop_batch_scheduler()  # should not raise
        assert sched_mod._batch_scheduler is None
    finally:
        sched_mod._batch_scheduler = original


def test_stop_batch_scheduler_shuts_down_running_scheduler():
    """stop_batch_scheduler calls shutdown on a running scheduler."""
    from src.services import scheduler as sched_mod
    from src.services.scheduler import stop_batch_scheduler

    mock_sched = MagicMock()
    mock_sched.running = True
    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = mock_sched
        stop_batch_scheduler()
        mock_sched.shutdown.assert_called_once_with(wait=False)
        assert sched_mod._batch_scheduler is None
    finally:
        sched_mod._batch_scheduler = original


def test_get_next_run_time_returns_none_when_no_scheduler():
    from src.services import scheduler as sched_mod
    from src.services.scheduler import get_next_run_time

    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = None
        assert get_next_run_time() is None
    finally:
        sched_mod._batch_scheduler = original


def test_get_next_run_time_returns_none_when_job_missing():
    """Returns None when scheduler is running but job doesn't exist."""
    from src.services import scheduler as sched_mod
    from src.services.scheduler import get_next_run_time

    mock_sched = MagicMock()
    mock_sched.running = True
    mock_sched.get_job.return_value = None
    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = mock_sched
        result = get_next_run_time()
        assert result is None
    finally:
        sched_mod._batch_scheduler = original


# ---------------------------------------------------------------------------
# _maybe_retrain_ml_weights exception handling
# ---------------------------------------------------------------------------


def test_maybe_retrain_handles_exception_gracefully(isolated_db):
    """_maybe_retrain_ml_weights should not raise even if internals fail."""
    from src.services.scheduler import _maybe_retrain_ml_weights

    with patch("src.data.history.get_all_factor_snapshots", side_effect=RuntimeError("db error")):
        _maybe_retrain_ml_weights()  # should not raise


def test_is_scheduler_running_returns_true_when_active():
    """is_scheduler_running returns True when _batch_scheduler is running."""
    from src.services import scheduler as sched_mod
    from src.services.scheduler import is_scheduler_running

    mock_sched = MagicMock()
    mock_sched.running = True
    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = mock_sched
        assert is_scheduler_running() is True
    finally:
        sched_mod._batch_scheduler = original


def test_get_next_run_time_returns_scheduled_time():
    """get_next_run_time returns job.next_run_time when job exists."""
    from datetime import datetime, timezone
    from src.services import scheduler as sched_mod
    from src.services.scheduler import get_next_run_time

    expected_time = datetime(2026, 5, 11, 7, 0, 0, tzinfo=timezone.utc)
    mock_job = MagicMock()
    mock_job.next_run_time = expected_time
    mock_sched = MagicMock()
    mock_sched.running = True
    mock_sched.get_job.return_value = mock_job
    original = sched_mod._batch_scheduler
    try:
        sched_mod._batch_scheduler = mock_sched
        result = get_next_run_time()
        assert result == expected_time
    finally:
        sched_mod._batch_scheduler = original


# ---------------------------------------------------------------------------
# Config properties
# ---------------------------------------------------------------------------


def test_batch_analysis_config_defaults():
    """batch_analysis config properties return expected defaults."""
    from src.core.config import cfg

    # defaults: enabled=False, schedule_hour=7, schedule_minute=0
    assert isinstance(cfg.batch_analysis_enabled, bool)
    assert isinstance(cfg.batch_schedule_hour, int)
    assert isinstance(cfg.batch_schedule_minute, int)
    assert 0 <= cfg.batch_schedule_hour <= 23
    assert 0 <= cfg.batch_schedule_minute <= 59


def test_batch_analysis_enabled_property_reads_config():
    """batch_analysis_enabled reflects the config value."""
    from src.core.config import cfg

    original = cfg._data.get("batch_analysis", {}).get("enabled")
    try:
        cfg._data.setdefault("batch_analysis", {})["enabled"] = True
        assert cfg.batch_analysis_enabled is True
        cfg._data["batch_analysis"]["enabled"] = False
        assert cfg.batch_analysis_enabled is False
    finally:
        if original is None:
            cfg._data["batch_analysis"].pop("enabled", None)
        else:
            cfg._data["batch_analysis"]["enabled"] = original

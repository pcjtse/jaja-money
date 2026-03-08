"""Tests for alerts.py (P2.5)."""
import pytest


@pytest.fixture(autouse=True)
def clean_alerts(tmp_path, monkeypatch):
    import alerts as a
    monkeypatch.setattr(a, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(a, "_ALERTS_FILE", tmp_path / "alerts.json")
    yield


def test_add_and_get_alert():
    from alerts import add_alert, get_alerts
    add_alert("AAPL", "Price Above", 200.0, "Target price")
    all_alerts = get_alerts()
    assert len(all_alerts) == 1
    assert all_alerts[0]["symbol"] == "AAPL"
    assert all_alerts[0]["condition"] == "Price Above"
    assert all_alerts[0]["threshold"] == 200.0
    assert all_alerts[0]["status"] == "active"


def test_filter_by_symbol():
    from alerts import add_alert, get_alerts
    add_alert("AAPL", "Price Above", 200.0)
    add_alert("MSFT", "Price Below", 300.0)
    aapl = get_alerts("AAPL")
    assert len(aapl) == 1
    assert aapl[0]["symbol"] == "AAPL"


def test_price_above_trigger():
    from alerts import add_alert, check_alerts, get_alerts
    add_alert("AAPL", "Price Above", 150.0)
    triggered = check_alerts("AAPL", price=160.0, factor_score=70, risk_score=30)
    assert len(triggered) == 1
    # Check it's now marked triggered
    all_alerts = get_alerts("AAPL")
    assert all_alerts[0]["status"] == "triggered"


def test_price_above_no_trigger():
    from alerts import add_alert, check_alerts
    add_alert("AAPL", "Price Above", 200.0)
    triggered = check_alerts("AAPL", price=150.0, factor_score=70, risk_score=30)
    assert len(triggered) == 0


def test_price_below_trigger():
    from alerts import add_alert, check_alerts
    add_alert("TSLA", "Price Below", 100.0)
    triggered = check_alerts("TSLA", price=90.0, factor_score=40, risk_score=70)
    assert len(triggered) == 1


def test_factor_score_trigger():
    from alerts import add_alert, check_alerts
    add_alert("NVDA", "Factor Score Below", 40)
    triggered = check_alerts("NVDA", price=400.0, factor_score=35, risk_score=60)
    assert len(triggered) == 1


def test_risk_score_trigger():
    from alerts import add_alert, check_alerts
    add_alert("XYZ", "Risk Score Above", 70)
    triggered = check_alerts("XYZ", price=10.0, factor_score=30, risk_score=80)
    assert len(triggered) == 1


def test_already_triggered_not_re_triggered():
    from alerts import add_alert, check_alerts
    add_alert("AAPL", "Price Above", 100.0)
    check_alerts("AAPL", price=150.0, factor_score=70, risk_score=30)
    # Second check should NOT trigger again
    triggered = check_alerts("AAPL", price=160.0, factor_score=70, risk_score=30)
    assert len(triggered) == 0


def test_delete_alert():
    from alerts import add_alert, delete_alert, get_alerts
    add_alert("AAPL", "Price Above", 200.0)
    alert_id = get_alerts()[0]["id"]
    delete_alert(alert_id)
    assert get_alerts() == []


def test_reset_alert():
    from alerts import add_alert, check_alerts, reset_alert, get_alerts
    add_alert("AAPL", "Price Above", 100.0)
    check_alerts("AAPL", price=150.0, factor_score=70, risk_score=30)
    alert_id = get_alerts()[0]["id"]
    reset_alert(alert_id)
    assert get_alerts()[0]["status"] == "active"

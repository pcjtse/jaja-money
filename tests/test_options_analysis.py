"""Tests for options_analysis.py — IV surface, options metrics, hedge suggestions."""

from __future__ import annotations

import pytest

from options_analysis import (
    build_iv_surface,
    compute_options_metrics,
    compute_hedge_suggestions,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_chain(
    strikes=(95, 100, 105),
    iv=0.25,
    oi=500,
    volume=100,
    ask=3.0,
    bid=2.8,
    expirations=("2025-01-17", "2025-02-21"),
):
    """Build a minimal options chain dict."""
    data = []
    for exp in expirations:
        calls = [
            {
                "strike": s,
                "impliedVolatility": iv,
                "openInterest": oi,
                "volume": volume,
                "ask": ask,
                "bid": bid,
                "lastPrice": ask,
            }
            for s in strikes
        ]
        puts = [
            {
                "strike": s,
                "impliedVolatility": iv,
                "openInterest": oi,
                "volume": volume,
                "ask": ask,
                "bid": bid,
                "lastPrice": ask,
            }
            for s in strikes
        ]
        data.append(
            {
                "expirationDate": exp,
                "options": {"CALL": calls, "PUT": puts},
            }
        )
    return {"data": data}


# ---------------------------------------------------------------------------
# build_iv_surface
# ---------------------------------------------------------------------------


class TestBuildIvSurface:
    def test_returns_available_false_on_empty_input(self):
        result = build_iv_surface({}, 100.0)
        assert result["available"] is False
        assert result["surface"] == []
        assert result["expirations"] == []

    def test_returns_available_false_on_none_input(self):
        result = build_iv_surface(None, 100.0)
        assert result["available"] is False

    def test_returns_available_false_when_no_data_key(self):
        result = build_iv_surface({"data": []}, 100.0)
        assert result["available"] is False

    def test_basic_surface_structure(self):
        chain = _make_chain(
            strikes=(90, 100, 110), iv=0.30, expirations=("2025-01-17",)
        )
        result = build_iv_surface(chain, 100.0)
        assert result["available"] is True
        assert len(result["surface"]) == 6  # 3 calls + 3 puts
        assert "2025-01-17" in result["expirations"]

    def test_iv_converted_to_percentage(self):
        chain = _make_chain(strikes=(100,), iv=0.25, expirations=("2025-01-17",))
        result = build_iv_surface(chain, 100.0)
        ivs = [e["iv"] for e in result["surface"]]
        # iv=0.25 → 25.0%
        assert all(iv == pytest.approx(25.0) for iv in ivs)

    def test_filters_zero_iv_options(self):
        chain = _make_chain(strikes=(100,), iv=0.0, expirations=("2025-01-17",))
        result = build_iv_surface(chain, 100.0)
        assert result["available"] is False

    def test_expirations_sorted(self):
        chain = _make_chain(expirations=("2025-03-21", "2025-01-17", "2025-02-21"))
        result = build_iv_surface(chain, 100.0)
        assert result["expirations"] == sorted(result["expirations"])

    def test_surface_entries_have_required_keys(self):
        chain = _make_chain()
        result = build_iv_surface(chain, 100.0)
        for entry in result["surface"]:
            assert "strike" in entry
            assert "expiry" in entry
            assert "iv" in entry
            assert "type" in entry


# ---------------------------------------------------------------------------
# compute_options_metrics
# ---------------------------------------------------------------------------


class TestComputeOptionsMetrics:
    def test_empty_chain_returns_unavailable(self):
        result = compute_options_metrics({}, 100.0)
        assert result["available"] is False

    def test_basic_metrics_structure(self):
        chain = _make_chain()
        result = compute_options_metrics(chain, 100.0)
        assert result["available"] is True
        assert "put_call_ratio" in result
        assert "max_pain" in result
        assert "avg_iv_pct" in result
        assert "total_call_oi" in result
        assert "total_put_oi" in result
        assert "unusual_flows" in result

    def test_put_call_ratio_equal_oi(self):
        chain = _make_chain(oi=500)
        result = compute_options_metrics(chain, 100.0)
        # equal put and call OI → ratio = 1.0
        assert result["put_call_ratio"] == pytest.approx(1.0, abs=0.01)

    def test_put_call_ratio_none_when_no_calls(self):
        data = [
            {
                "expirationDate": "2025-01-17",
                "options": {
                    "PUT": [
                        {"strike": 100, "impliedVolatility": 0.25, "openInterest": 100}
                    ]
                },
            }
        ]
        result = compute_options_metrics({"data": data}, 100.0)
        # no calls → ratio is None
        assert result["put_call_ratio"] is None

    def test_avg_iv_pct_is_percentage(self):
        chain = _make_chain(iv=0.20)
        result = compute_options_metrics(chain, 100.0)
        assert result["avg_iv_pct"] == pytest.approx(20.0, abs=0.1)

    def test_total_oi_counts(self):
        chain = _make_chain(strikes=(95, 100, 105), oi=100)
        result = compute_options_metrics(chain, 100.0)
        # 3 strikes × 2 expirations × 100 OI = 600 per side
        assert result["total_call_oi"] == 600
        assert result["total_put_oi"] == 600

    def test_unusual_flows_detected(self):
        # volume = 500, OI = 100 → ratio = 5.0 > 3x threshold
        chain = _make_chain(
            strikes=(100,), oi=100, volume=500, expirations=("2025-01-17",)
        )
        result = compute_options_metrics(chain, 100.0)
        assert len(result["unusual_flows"]) > 0
        for flow in result["unusual_flows"]:
            assert flow["volume_oi_ratio"] > 3.0

    def test_unusual_flows_not_detected_below_threshold(self):
        chain = _make_chain(
            strikes=(100,), oi=500, volume=100, expirations=("2025-01-17",)
        )
        result = compute_options_metrics(chain, 100.0)
        assert result["unusual_flows"] == []

    def test_atm_iv_values_populated(self):
        chain = _make_chain(strikes=(90, 100, 110), iv=0.30)
        result = compute_options_metrics(chain, 100.0)
        assert result["atm_iv_call"] is not None
        assert result["atm_iv_put"] is not None

    def test_implied_move_pct_calculation(self):
        chain = _make_chain(strikes=(100,), iv=0.25, ask=5.0, bid=4.8)
        result = compute_options_metrics(chain, 100.0)
        if result["atm_straddle_cost"] is not None:
            # straddle cost = call ask + put ask = 5 + 5 = 10 → 10/100 * 100 = 10%
            assert result["implied_move_pct"] == pytest.approx(10.0, abs=0.01)

    def test_max_pain_in_strike_range(self):
        chain = _make_chain(strikes=(90, 100, 110))
        result = compute_options_metrics(chain, 100.0)
        if result["max_pain"] is not None:
            assert result["max_pain"] in (90, 100, 110)


# ---------------------------------------------------------------------------
# compute_hedge_suggestions
# ---------------------------------------------------------------------------


class TestComputeHedgeSuggestions:
    def test_empty_chain_returns_unavailable(self):
        result = compute_hedge_suggestions(100.0, {})
        assert result["available"] is False

    def test_zero_price_returns_unavailable(self):
        chain = _make_chain()
        result = compute_hedge_suggestions(0.0, chain)
        assert result["available"] is False

    def test_protective_put_fields(self):
        chain = _make_chain(
            strikes=(90, 95, 100, 105, 110),
            ask=3.0,
            bid=2.8,
            expirations=("2025-01-17", "2025-02-21"),
        )
        result = compute_hedge_suggestions(100.0, chain, position_value=10_000)
        assert result["available"] is True
        pp = result["protective_put"]
        assert "strike" in pp
        assert "expiry" in pp
        assert "cost_per_share" in pp
        assert "cost_pct_position" in pp
        assert "breakeven" in pp
        assert "max_loss_pct" in pp

    def test_protective_put_strike_is_otm(self):
        chain = _make_chain(
            strikes=(90, 95, 100, 105, 110),
            ask=3.0,
            expirations=("2025-01-17", "2025-02-21"),
        )
        result = compute_hedge_suggestions(100.0, chain)
        if result["available"]:
            # Protective put target is ~5% OTM → should be around strike 95
            pp = result["protective_put"]
            assert pp["strike"] <= 100.0

    def test_collar_fields_present(self):
        chain = _make_chain(
            strikes=(90, 95, 100, 105, 110),
            ask=3.0,
            bid=2.8,
            expirations=("2025-01-17", "2025-02-21"),
        )
        result = compute_hedge_suggestions(100.0, chain)
        if result["available"] and result["collar"]:
            collar = result["collar"]
            assert "put_strike" in collar
            assert "call_strike" in collar
            assert "expiry" in collar
            assert "net_cost_per_share" in collar
            assert "description" in collar

    def test_uses_second_expiry_for_hedge(self):
        chain = _make_chain(
            strikes=(90, 95, 100, 105, 110),
            ask=2.0,
            bid=1.8,
            expirations=("2025-01-17", "2025-02-21"),
        )
        result = compute_hedge_suggestions(100.0, chain)
        if result["available"]:
            assert result["protective_put"].get("expiry") == "2025-02-21"

    def test_no_puts_returns_unavailable(self):
        data = [
            {
                "expirationDate": "2025-01-17",
                "options": {
                    "CALL": [{"strike": 100, "ask": 3.0}],
                    "PUT": [],
                },
            },
            {
                "expirationDate": "2025-02-21",
                "options": {
                    "CALL": [{"strike": 100, "ask": 3.0}],
                    "PUT": [],
                },
            },
        ]
        result = compute_hedge_suggestions(100.0, {"data": data})
        assert result["available"] is False

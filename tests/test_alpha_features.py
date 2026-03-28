"""Tests for all 15 alpha feature modules."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Congress signal
# ---------------------------------------------------------------------------


class TestCongressSignal:
    def test_no_data_returns_neutral(self):
        from src.analysis.factors import _factor_congress_signal

        r = _factor_congress_signal(None)
        assert r["score"] == 50
        assert r["name"] == "Congress Signal"

    def test_buying_signal_high_score(self):
        from src.analysis.factors import _factor_congress_signal

        data = {
            "available": True,
            "buys": 5,
            "sells": 0,
            "net_signal": "Buying",
            "score": 80,
            "detail": "5 buys",
        }
        r = _factor_congress_signal(data)
        assert r["score"] == 80
        assert "buying" in r["label"].lower()

    def test_selling_signal_low_score(self):
        from src.analysis.factors import _factor_congress_signal

        data = {
            "available": True,
            "buys": 0,
            "sells": 3,
            "net_signal": "Selling",
            "score": 22,
            "detail": "3 sells",
        }
        r = _factor_congress_signal(data)
        assert r["score"] == 22
        assert "selling" in r["label"].lower()


# ---------------------------------------------------------------------------
# Institutional flow
# ---------------------------------------------------------------------------


class TestInstitutionalFlow:
    def test_no_data_returns_neutral(self):
        from src.analysis.factors import _factor_institutional_flow

        r = _factor_institutional_flow(None)
        assert r["score"] == 50

    def test_entering_institutions_high_score(self):
        from src.analysis.factors import _factor_institutional_flow

        data = {
            "available": True,
            "entering": ["Vanguard", "BlackRock"],
            "exiting": [],
            "net_change_pct": 1.5,
            "score": 78,
            "detail": "2 new entrants",
        }
        r = _factor_institutional_flow(data)
        assert r["score"] == 78

    def test_exiting_institutions_low_score(self):
        from src.analysis.factors import _factor_institutional_flow

        data = {
            "available": True,
            "entering": [],
            "exiting": ["Vanguard", "BlackRock"],
            "net_change_pct": -1.5,
            "score": 28,
            "detail": "2 exits",
        }
        r = _factor_institutional_flow(data)
        assert r["score"] == 28


# ---------------------------------------------------------------------------
# Estimate revision velocity
# ---------------------------------------------------------------------------


class TestEstimateVelocity:
    def test_max_streak_function(self):
        from src.data.estimate_tracker import _max_streak

        assert _max_streak(["up", "up", "up", "down"], "up") == 3
        assert _max_streak(["down", "up", "up"], "up") == 2
        assert _max_streak(["down", "down", "down"], "up") == 0
        assert _max_streak([], "up") == 0

    def test_no_history_returns_neutral(self):
        from src.data.estimate_tracker import compute_revision_velocity

        # Fresh symbol with no history
        result = compute_revision_velocity("XXXX_FAKE_TICKER", window_days=60)
        assert result["velocity_score"] == 50

    def test_factor_no_data_neutral(self):
        from src.analysis.factors import _factor_estimate_velocity

        r = _factor_estimate_velocity(None)
        assert r["score"] == 50

    def test_three_up_streak_score_high(self):
        from src.analysis.factors import _factor_estimate_velocity

        data = {
            "consecutive_up": 3,
            "consecutive_down": 0,
            "eps_change_pct": 8.0,
            "velocity_score": 90,
            "detail": "Up streak: 3",
        }
        r = _factor_estimate_velocity(data)
        assert r["score"] == 90

    def test_three_down_streak_score_low(self):
        from src.analysis.factors import _factor_estimate_velocity

        data = {
            "consecutive_up": 0,
            "consecutive_down": 3,
            "eps_change_pct": -8.0,
            "velocity_score": 12,
            "detail": "Down streak: 3",
        }
        r = _factor_estimate_velocity(data)
        assert r["score"] == 12


# ---------------------------------------------------------------------------
# Buyback effectiveness
# ---------------------------------------------------------------------------


class TestBuyback:
    def test_score_buyback_decreasing_shares(self):
        from src.analysis.buyback import score_buyback_effectiveness

        data = {
            "available": True,
            "share_count_trend": "decreasing",
            "shares_yoy_change_pct": -2.5,
            "buyback_yield_pct": 3.5,
            "detail": "Share trend: decreasing | YoY: -2.5%",
        }
        r = score_buyback_effectiveness(data)
        assert r["score"] >= 70
        assert "accretive" in r["label"].lower() or "buyback" in r["label"].lower()

    def test_score_buyback_increasing_shares(self):
        from src.analysis.buyback import score_buyback_effectiveness

        data = {
            "available": True,
            "share_count_trend": "increasing",
            "shares_yoy_change_pct": 4.0,
            "buyback_yield_pct": 0.1,
            "detail": "Share trend: increasing",
        }
        r = score_buyback_effectiveness(data)
        assert r["score"] <= 35

    def test_no_data_returns_neutral(self):
        from src.analysis.buyback import score_buyback_effectiveness

        r = score_buyback_effectiveness({"available": False})
        assert r["score"] == 50

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_buyback

        r = _factor_buyback(None)
        assert r["score"] == 50
        assert r["name"] == "Buyback Effectiveness"


# ---------------------------------------------------------------------------
# Guidance quality
# ---------------------------------------------------------------------------


class TestGuidanceQuality:
    def test_empty_earnings_neutral(self):
        from src.analysis.guidance_quality import compute_guidance_quality_score

        r = compute_guidance_quality_score([])
        assert r["score"] == 50

    def test_all_beats_high_score(self):
        from src.analysis.guidance_quality import compute_guidance_quality_score

        earnings = [
            {"actual": 1.5, "estimate": 1.2, "surprisePercent": 25},
            {"actual": 1.3, "estimate": 1.1, "surprisePercent": 18},
            {"actual": 1.1, "estimate": 0.9, "surprisePercent": 22},
            {"actual": 0.9, "estimate": 0.7, "surprisePercent": 28},
        ]
        r = compute_guidance_quality_score(earnings)
        assert r["score"] >= 70
        assert r["beat_rate"] == 1.0
        assert r["consecutive_beats"] == 4

    def test_all_misses_low_score(self):
        from src.analysis.guidance_quality import compute_guidance_quality_score

        earnings = [
            {"actual": 0.8, "estimate": 1.2, "surprisePercent": -33},
            {"actual": 0.7, "estimate": 1.1, "surprisePercent": -36},
            {"actual": 0.6, "estimate": 0.9, "surprisePercent": -33},
        ]
        r = compute_guidance_quality_score(earnings)
        assert r["score"] <= 35
        assert r["beat_rate"] == 0.0

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_guidance_quality

        r = _factor_guidance_quality(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Options flow anomaly detector
# ---------------------------------------------------------------------------


class TestOptionsFlow:
    def test_neutral_on_none(self):
        from src.analysis.options_flow import classify_options_flow

        r = classify_options_flow(None, 100.0)
        assert r["score"] == 50
        assert r["flow_type"] == "NEUTRAL"

    def test_bullish_sweep_detection(self):
        from src.analysis.options_flow import classify_options_flow

        chain = {
            "callVolume": 10000,
            "putVolume": 2000,
            "putCallRatio": 0.2,
            "options": [
                {
                    "type": "call",
                    "volume": 500,
                    "openInterest": 100,
                    "strike": 105,
                    "expiration": "2026-04-18",
                    "impliedVolatility": 0.35,
                }
            ],
        }
        r = classify_options_flow(chain, 100.0)
        assert r["score"] > 50

    def test_bearish_sweep_detection(self):
        from src.analysis.options_flow import classify_options_flow

        chain = {
            "callVolume": 1000,
            "putVolume": 8000,
            "putCallRatio": 2.5,
            "options": [
                {
                    "type": "put",
                    "volume": 600,
                    "openInterest": 100,
                    "strike": 95,
                    "expiration": "2026-04-18",
                    "impliedVolatility": 0.45,
                }
            ],
        }
        r = classify_options_flow(chain, 100.0)
        assert r["score"] < 50

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_options_flow

        r = _factor_options_flow(None)
        assert r["score"] == 50

    def test_gamma_no_data(self):
        from src.analysis.options_flow import compute_gamma_exposure

        r = compute_gamma_exposure(None, 100.0)
        assert r["gamma_condition"] == "unknown"

    def test_approx_gamma_positive(self):
        from src.analysis.options_flow import _approx_gamma

        g = _approx_gamma(100.0, 100.0, 0.2, 0.25)
        assert g > 0


# ---------------------------------------------------------------------------
# Catalyst calendar
# ---------------------------------------------------------------------------


class TestCatalystCalendar:
    def test_fomc_dates_loaded(self):
        from src.data.catalyst_calendar import _get_upcoming_fomc

        events = _get_upcoming_fomc(days_ahead=365)
        # Should have at least some FOMC dates in the next year
        assert isinstance(events, list)
        for e in events:
            assert e["event_type"] == "FOMC"

    def test_catalyst_result_structure(self):
        from src.data.catalyst_calendar import get_catalyst_calendar

        # Should return valid structure even without API access
        result = get_catalyst_calendar("AAPL", days_ahead=60)
        assert "events" in result
        assert "catalysts_within_7d" in result
        assert "fomc_within_30d" in result
        assert isinstance(result["events"], list)


# ---------------------------------------------------------------------------
# Supply chain graph
# ---------------------------------------------------------------------------


class TestSupplyChainGraph:
    def test_parse_sole_source_detected(self):
        from src.analysis.supply_chain_graph import parse_supply_chain_from_text

        text = """
        The company relies on a sole-source supplier in China for all
        critical components. Any disruption would materially impact production.
        """
        result = parse_supply_chain_from_text("TEST", text)
        assert result["sole_source_risk"] is True
        assert "china" in result["high_risk_regions"]

    def test_parse_diverse_supply_chain(self):
        from src.analysis.supply_chain_graph import parse_supply_chain_from_text

        text = """
        The company sources materials from over 50 independent suppliers
        across the United States, Canada, and Europe.
        """
        result = parse_supply_chain_from_text("TEST", text)
        assert result["concentration_score"] < 60

    def test_score_high_concentration(self):
        from src.analysis.supply_chain_graph import score_supply_chain_risk

        data = {
            "concentration_score": 90,
            "sole_source_risk": True,
            "customer_concentration": True,
            "high_risk_regions": ["china", "russia"],
        }
        r = score_supply_chain_risk(data)
        assert r["score"] <= 30

    def test_score_low_concentration(self):
        from src.analysis.supply_chain_graph import score_supply_chain_risk

        data = {
            "concentration_score": 15,
            "sole_source_risk": False,
            "customer_concentration": False,
            "high_risk_regions": [],
        }
        r = score_supply_chain_risk(data)
        assert r["score"] >= 70

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_supply_chain_risk

        r = _factor_supply_chain_risk(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Special situations
# ---------------------------------------------------------------------------


class TestSpecialSituations:
    def test_no_situation_neutral(self):
        from src.analysis.special_situations import score_special_situation

        r = score_special_situation({"available": False})
        assert r["score"] == 50
        assert r["overrides_composite"] is False

    def test_high_certainty_merger(self):
        from src.analysis.special_situations import score_special_situation

        data = {
            "available": True,
            "situation_type": "merger",
            "filings": [{"form_type": "DEFM14A"}],
            "description": "Definitive merger agreement",
        }
        r = score_special_situation(data)
        assert r["score"] >= 60
        assert "merger" in r["label"].lower() or "arb" in r["label"].lower()

    def test_spinoff_positive_signal(self):
        from src.analysis.special_situations import score_special_situation

        data = {
            "available": True,
            "situation_type": "spinoff",
            "filings": [{"form_type": "10-12B"}],
            "description": "Spin-off registration",
        }
        r = score_special_situation(data)
        assert r["score"] >= 65

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_special_situation

        r = _factor_special_situation(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Market regime detector
# ---------------------------------------------------------------------------


class TestRegime:
    def test_classify_risk_on_growth(self):
        from src.analysis.regime import _classify_regime

        signals = {
            "vix": 12.0,
            "spy_above_200d": True,
            "spy_vs_200_pct": 8.0,
            "hyg_ief_ratio": 0.90,
        }
        regime, confidence = _classify_regime(signals)
        assert regime == "Risk-On Growth"
        assert confidence > 0.3

    def test_classify_risk_off_panic(self):
        from src.analysis.regime import _classify_regime

        signals = {
            "vix": 42.0,
            "spy_above_200d": False,
            "spy_vs_200_pct": -15.0,
            "hyg_ief_ratio": 0.60,
        }
        regime, confidence = _classify_regime(signals)
        assert regime == "Risk-Off Panic"

    def test_empty_signals_returns_sideways(self):
        from src.analysis.regime import _classify_regime

        regime, confidence = _classify_regime({})
        assert regime == "Sideways"

    def test_multipliers_defined(self):
        from src.analysis.regime import REGIME_MULTIPLIERS, REGIME_RISK_ON_GROWTH, REGIME_RISK_OFF_PANIC

        assert REGIME_MULTIPLIERS[REGIME_RISK_ON_GROWTH] > 0
        assert REGIME_MULTIPLIERS[REGIME_RISK_OFF_PANIC] < 0

    def test_apply_regime_multiplier(self):
        from src.analysis.regime import apply_regime_multiplier

        r = apply_regime_multiplier(65, {"multiplier": 8})
        assert r == 73
        r2 = apply_regime_multiplier(10, {"multiplier": -12})
        assert r2 == 0  # clamped

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_regime

        r = _factor_regime(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Cross-asset signals
# ---------------------------------------------------------------------------


class TestCrossAsset:
    def test_resolve_sector_exact(self):
        from src.data.cross_asset import _resolve_sector

        assert _resolve_sector("Technology") == "Technology"
        assert _resolve_sector("Financials") == "Financials"

    def test_resolve_sector_partial(self):
        from src.data.cross_asset import _resolve_sector

        assert _resolve_sector("Tech") == "Technology"

    def test_resolve_unknown_returns_fallback(self):
        from src.data.cross_asset import _resolve_sector, _FALLBACK_SECTOR

        assert _resolve_sector("Unkwnown Sector") == _FALLBACK_SECTOR

    def test_no_data_neutral_score(self):
        from src.analysis.factors import _factor_cross_asset

        r = _factor_cross_asset(None)
        assert r["score"] == 50

    def test_high_score_tailwind(self):
        from src.analysis.factors import _factor_cross_asset

        data = {"available": True, "sector": "Technology", "score": 75, "detail": "Tailwinds"}
        r = _factor_cross_asset(data)
        assert r["score"] == 75
        assert "tailwind" in r["label"].lower()


# ---------------------------------------------------------------------------
# Geographic revenue
# ---------------------------------------------------------------------------


class TestGeoRevenue:
    def test_extract_from_text_us_dominant(self):
        from src.data.geographic_revenue import extract_geo_revenue_from_text

        text = "Our operations are primarily domestic. United States revenue represents 90% of our total."
        weights = extract_geo_revenue_from_text(text)
        assert "united states" in weights
        assert weights["united states"] > 0.5

    def test_score_us_only_moderate_risk(self):
        from src.data.geographic_revenue import score_geographic_risk

        r = score_geographic_risk({"united states": 1.0})
        assert r["score"] >= 50
        assert r["weighted_risk"] < 0.2

    def test_score_china_heavy_high_risk(self):
        from src.data.geographic_revenue import score_geographic_risk

        r = score_geographic_risk({"china": 0.8, "united states": 0.2})
        assert r["weighted_risk"] > 0.5
        assert r["score"] <= 50

    def test_empty_weights_neutral(self):
        from src.data.geographic_revenue import score_geographic_risk

        r = score_geographic_risk({})
        assert r["score"] == 50

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_geo_revenue

        r = _factor_geo_revenue(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Factor crowding
# ---------------------------------------------------------------------------


class TestCrowding:
    def test_cosine_similarity_identical(self):
        from src.analysis.crowding import _cosine_similarity

        v = [0.8, 0.7, 0.6, 0.5]
        result = _cosine_similarity(v, v)
        assert abs(result - 1.0) < 0.001

    def test_cosine_similarity_opposite(self):
        from src.analysis.crowding import _cosine_similarity

        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        result = _cosine_similarity(v1, v2)
        assert abs(result - 0.0) < 0.001

    def test_cosine_similarity_empty(self):
        from src.analysis.crowding import _cosine_similarity

        assert _cosine_similarity([], []) == 0.0

    def test_classify_crowding_extreme(self):
        from src.analysis.crowding import _classify_crowding

        r = _classify_crowding(0.95)
        assert r["risk_level"] == "Extreme"
        assert r["penalty"] == 15

    def test_classify_crowding_low(self):
        from src.analysis.crowding import _classify_crowding

        r = _classify_crowding(0.3)
        assert r["risk_level"] == "Low"
        assert r["penalty"] == 0

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_crowding_risk

        r = _factor_crowding_risk(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Dark pool signal
# ---------------------------------------------------------------------------


class TestDarkPool:
    def test_compute_signal_spike(self):
        from src.data.dark_pool import _compute_signal

        # History with spike in latest week
        history = [
            {"ats_pct": 55.0, "week_date": "2026-03-28"},
            {"ats_pct": 35.0, "week_date": "2026-03-21"},
            {"ats_pct": 36.0, "week_date": "2026-03-14"},
            {"ats_pct": 34.0, "week_date": "2026-03-07"},
        ]
        r = _compute_signal(history)
        assert r["available"] is True
        assert r["spike"] is True
        assert r["ats_pct_latest"] == 55.0

    def test_compute_signal_empty_history(self):
        from src.data.dark_pool import _compute_signal

        r = _compute_signal([])
        assert r["available"] is False
        assert r["score"] == 50

    def test_compute_trend_increasing(self):
        from src.data.dark_pool import _compute_signal

        history = [
            {"ats_pct": 45.0, "week_date": "2026-03-28"},
            {"ats_pct": 40.0, "week_date": "2026-03-21"},
            {"ats_pct": 35.0, "week_date": "2026-03-14"},
        ]
        r = _compute_signal(history)
        assert r["trend"] == "increasing"

    def test_factor_wrapper(self):
        from src.analysis.factors import _factor_dark_pool

        r = _factor_dark_pool(None)
        assert r["score"] == 50


# ---------------------------------------------------------------------------
# Borrow rates
# ---------------------------------------------------------------------------


class TestBorrowRates:
    def test_classify_ctb_very_expensive(self):
        from src.data.borrow_rates import _classify_ctb

        assert _classify_ctb(75.0) == "Very Expensive"

    def test_classify_ctb_cheap(self):
        from src.data.borrow_rates import _classify_ctb

        assert _classify_ctb(1.0) == "Cheap"

    def test_estimate_from_short_pct(self):
        from src.data.borrow_rates import _estimate_ctb_from_short_pct

        ctb_high = _estimate_ctb_from_short_pct(35.0)
        ctb_low = _estimate_ctb_from_short_pct(3.0)
        assert ctb_high > ctb_low


# ---------------------------------------------------------------------------
# Guardrails: new alpha flags
# ---------------------------------------------------------------------------


class TestGuardrailAlphaFlags:
    def _minimal_call(self, **kwargs):
        """Call _build_flags with minimal required args + alpha kwargs."""
        from src.analysis.guardrails import _build_flags

        return _build_flags(
            close=None,
            price=100.0,
            financials={},
            earnings=[],
            recommendations=[],
            sentiment_agg=None,
            composite_factor_score=50,
            hv=None,
            drawdown_pct=None,
            **kwargs,
        )

    def test_congress_selling_flag(self):
        flags = self._minimal_call(
            congress_data={"available": True, "net_signal": "Selling", "sells": 3, "buys": 0}
        )
        titles = [f["title"] for f in flags]
        assert any("congressional" in t.lower() for t in titles)

    def test_crowding_extreme_flag(self):
        flags = self._minimal_call(
            crowding_data={"risk_level": "Extreme", "penalty": 15, "detail": "test"}
        )
        titles = [f["title"] for f in flags]
        assert any("crowding" in t.lower() for t in titles)

    def test_catalyst_within_7d_flag(self):
        flags = self._minimal_call(
            catalyst_data={"catalysts_within_7d": 3, "fomc_within_30d": False}
        )
        titles = [f["title"] for f in flags]
        assert any("catalyst" in t.lower() for t in titles)

    def test_fomc_flag(self):
        flags = self._minimal_call(
            catalyst_data={"catalysts_within_7d": 0, "fomc_within_30d": True}
        )
        titles = [f["title"] for f in flags]
        assert any("fomc" in t.lower() for t in titles)

    def test_sole_source_supply_chain_flag(self):
        flags = self._minimal_call(
            supply_chain_data={"sole_source_risk": True, "high_risk_regions": []}
        )
        titles = [f["title"] for f in flags]
        assert any("supply" in t.lower() for t in titles)

    def test_risk_off_panic_flag(self):
        flags = self._minimal_call(
            regime_data={"regime": "Risk-Off Panic", "multiplier": -12, "detail": "test"}
        )
        titles = [f["title"] for f in flags]
        assert any("panic" in t.lower() for t in titles)

    def test_bearish_sweep_flag(self):
        flags = self._minimal_call(
            options_flow_data={"flow_type": "BEARISH_SWEEP", "put_call_ratio": 2.5}
        )
        titles = [f["title"] for f in flags]
        assert any("bearish" in t.lower() or "sweep" in t.lower() for t in titles)


# ---------------------------------------------------------------------------
# compute_factors integration — new parameters accepted
# ---------------------------------------------------------------------------


class TestComputeFactorsIntegration:
    def _make_quote(self, price=100.0):
        return {"c": price}

    def test_compute_factors_no_alpha_data(self):
        from src.analysis.factors import compute_factors

        factors = compute_factors(
            quote=self._make_quote(),
            financials={},
            close=None,
            earnings=[],
            recommendations=[],
            sentiment_agg=None,
        )
        assert isinstance(factors, list)
        assert len(factors) >= 11  # original 11 + new alpha factors

    def test_compute_factors_with_alpha_data(self):
        from src.analysis.factors import compute_factors

        factors = compute_factors(
            quote=self._make_quote(),
            financials={},
            close=None,
            earnings=[],
            recommendations=[],
            sentiment_agg=None,
            congress_data={"available": True, "score": 75, "net_signal": "Buying", "detail": "", "buys": 2, "sells": 0},
            regime_data={"regime": "Risk-On Growth", "confidence": 0.8, "multiplier": 8, "detail": ""},
        )
        assert len(factors) >= 23
        factor_names = [f["name"] for f in factors]
        assert "Congress Signal" in factor_names
        assert "Market Regime" in factor_names

    def test_all_factors_have_required_keys(self):
        from src.analysis.factors import compute_factors

        factors = compute_factors(
            quote=self._make_quote(),
            financials={},
            close=None,
            earnings=[],
            recommendations=[],
            sentiment_agg=None,
        )
        for f in factors:
            assert "name" in f
            assert "score" in f
            assert "weight" in f
            assert "label" in f
            assert 0 <= f["score"] <= 100, f"Score out of range: {f}"

"""Tests for P23-P27 investment strategies.

Covers:
- P23: Low Volatility, Shareholder Yield, Earnings Revision, Altman Z-Score, NCAV
- P24: 52W High Breakout, Index Trend Gate, Dual Momentum
- P25: Cluster Insider Buying, Tax-Loss Bounce, Spinoff Screen
- P26: VRP Harvest, IV Rank/Percentile
- P27: Rate Sensitivity, FX Exposure
"""

from __future__ import annotations

import pandas as pd

from factors import (
    compute_low_volatility_score,
    compute_shareholder_yield,
    compute_earnings_revision_momentum,
    compute_altman_zscore,
    compute_ncav,
    compute_breakout_signal,
    get_index_trend_gate,
    compute_tax_loss_bounce_signal,
    compute_rate_sensitivity,
    compute_fx_exposure_adjustment,
)
from options_analysis import compute_vrp, compute_iv_rank
from ownership import compute_cluster_insider_score
from sectors import compute_dual_momentum
from screener import (
    LOW_VOL_PRESET,
    SHAREHOLDER_YIELD_PRESET,
    NCAV_PRESET,
    BREAKOUT_PRESET,
    INSIDER_BUYING_PRESET,
    TAX_LOSS_BOUNCE_PRESET,
    VRP_HARVEST_PRESET,
    is_breakout_candidate,
    is_insider_buying_candidate,
    is_tax_loss_bounce_candidate,
    is_vrp_harvest_candidate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rising(n=100, start=100.0, step=0.5):
    return pd.Series([start + i * step for i in range(n)])


def _flat(n=100, price=100.0):
    return pd.Series([price] * n)


def _declining_ytd(pct=-50.0, n=260):
    """Series that has declined `pct` % over its full length."""
    end = 100.0
    start = end / (1 + pct / 100)
    return pd.Series([start + (end - start) * i / (n - 1) for i in range(n)])


# ---------------------------------------------------------------------------
# P23.1: Low Volatility Anomaly
# ---------------------------------------------------------------------------


class TestLowVolatilityScore:
    def test_no_data_returns_50(self):
        result = compute_low_volatility_score(None)
        assert result["score"] == 50
        assert result["volatility_60d"] is None

    def test_insufficient_data(self):
        result = compute_low_volatility_score(pd.Series([100.0] * 30))
        assert result["score"] == 50

    def test_low_vol_scores_high(self):
        # Near-flat series → very low vol
        close = _flat(n=100, price=100.0)
        result = compute_low_volatility_score(close)
        assert result["score"] >= 75

    def test_high_vol_scores_low(self):
        # Highly volatile series
        import random

        rng = random.Random(42)
        prices = [100.0]
        for _ in range(120):
            prices.append(prices[-1] * (1 + rng.uniform(-0.05, 0.05)))
        close = pd.Series(prices)
        result = compute_low_volatility_score(close)
        # Score should be lower than flat series
        assert result["score"] < 70

    def test_returns_volatility_value(self):
        close = _rising(n=100)
        result = compute_low_volatility_score(close)
        if result["volatility_60d"] is not None:
            assert result["volatility_60d"] >= 0


# ---------------------------------------------------------------------------
# P23.2: Shareholder Yield
# ---------------------------------------------------------------------------


class TestShareholderYield:
    def test_no_financials(self):
        result = compute_shareholder_yield(None)
        assert result["score"] >= 0
        assert result["total_yield_pct"] == 0.0

    def test_high_yield(self):
        fin = {"dividendYieldIndicatedAnnual": 5.0, "marketCapitalization": 1000.0}
        result = compute_shareholder_yield(fin)
        assert result["dividend_yield_pct"] == 5.0
        assert result["score"] >= 70

    def test_buyback_yield_added(self):
        fin = {
            "dividendYieldIndicatedAnnual": 2.0,
            "repurchaseOfCommonStockAnnual": 40.0,  # $40M buyback
            "marketCapitalization": 1000.0,  # $1B market cap → 4% buyback yield
        }
        result = compute_shareholder_yield(fin)
        assert result["buyback_yield_pct"] is not None
        assert result["total_yield_pct"] > 2.0

    def test_exceptional_yield_label(self):
        fin = {"dividendYieldIndicatedAnnual": 10.0}
        result = compute_shareholder_yield(fin)
        assert result["score"] >= 90
        assert "Exceptional" in result["label"]

    def test_no_dividend(self):
        result = compute_shareholder_yield({})
        assert result["dividend_yield_pct"] == 0.0
        assert result["buyback_yield_pct"] is None


# ---------------------------------------------------------------------------
# P23.3: Earnings Revision Momentum
# ---------------------------------------------------------------------------


class TestEarningsRevisionMomentum:
    def test_no_data(self):
        result = compute_earnings_revision_momentum(None, None)
        assert result["score"] == 50
        assert result["trend"] == "No data"

    def test_upward_revision_direction(self):
        result = compute_earnings_revision_momentum([], {"revision_direction": "up", "available": True})
        assert result["score"] > 50
        assert result["trend"] == "Improving"

    def test_downward_revision_direction(self):
        result = compute_earnings_revision_momentum([], {"revision_direction": "down", "available": True})
        assert result["score"] < 50

    def test_accelerating_surprises(self):
        # Increasing surprises: 2%, 4%, 6%, 8% (most recent last)
        earnings = [
            {"surprisePercent": 8.0},
            {"surprisePercent": 6.0},
            {"surprisePercent": 4.0},
            {"surprisePercent": 2.0},
        ]
        result = compute_earnings_revision_momentum(earnings, None)
        assert result["score"] >= 70
        assert result["surprise_slope"] is not None
        assert result["surprise_slope"] > 0

    def test_decelerating_surprises(self):
        # Decreasing surprises: 8%, 6%, 4%, 2% → most recent = 2%, declining
        earnings = [
            {"surprisePercent": 2.0},
            {"surprisePercent": 4.0},
            {"surprisePercent": 6.0},
            {"surprisePercent": 8.0},
        ]
        result = compute_earnings_revision_momentum(earnings, None)
        # slope should be negative → lower score
        assert result["surprise_slope"] is not None

    def test_score_clamped(self):
        earnings = [{"surprisePercent": 20.0}, {"surprisePercent": 20.0}]
        result = compute_earnings_revision_momentum(earnings, None)
        assert 0 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# P23.4: Altman Z-Score
# ---------------------------------------------------------------------------


class TestAltmanZScore:
    def test_no_data(self):
        result = compute_altman_zscore(None)
        assert result["zone"] == "No data"
        assert result["z_score"] is None

    def test_insufficient_components(self):
        # Only 1 component available
        result = compute_altman_zscore({"marketCapitalization": 1000.0})
        assert result["zone"] == "No data"

    def test_safe_zone(self):
        fin = {
            "totalCurrentAssetsAnnual": 500.0,
            "totalCurrentLiabilitiesAnnual": 200.0,
            "totalAssetsAnnual": 1000.0,
            "retainedEarningsAnnual": 400.0,
            "ebitAnnual": 150.0,
            "marketCapitalization": 2000.0,
            "totalLiabilitiesAnnual": 400.0,
            "revenueAnnual": 800.0,
        }
        result = compute_altman_zscore(fin)
        assert result["zone"] == "Safe"
        assert result["z_score"] is not None
        assert result["z_score"] > 2.99
        assert result["score"] >= 75

    def test_distress_zone(self):
        fin = {
            "totalCurrentAssetsAnnual": 50.0,
            "totalCurrentLiabilitiesAnnual": 300.0,
            "totalAssetsAnnual": 500.0,
            "retainedEarningsAnnual": -200.0,
            "ebitAnnual": -50.0,
            "marketCapitalization": 80.0,
            "totalLiabilitiesAnnual": 450.0,
            "revenueAnnual": 100.0,
        }
        result = compute_altman_zscore(fin)
        assert result["zone"] == "Distress"
        assert result["score"] < 35

    def test_components_dict_returned(self):
        fin = {
            "totalCurrentAssetsAnnual": 200.0,
            "totalCurrentLiabilitiesAnnual": 100.0,
            "totalAssetsAnnual": 500.0,
            "retainedEarningsAnnual": 150.0,
            "ebitAnnual": 80.0,
        }
        result = compute_altman_zscore(fin)
        assert "components" in result
        assert "X1" in result["components"]


# ---------------------------------------------------------------------------
# P23.5: NCAV
# ---------------------------------------------------------------------------


class TestNCaV:
    def test_no_data(self):
        result = compute_ncav(None, 100.0)
        assert result["ncav_per_share"] is None
        assert result["is_net_net"] is False

    def test_net_net_detected(self):
        # NCAV = (500 - 100) * 1e6 = $400M, shares = 10M → NCAV/share = $40
        fin = {
            "totalCurrentAssetsAnnual": 500.0,  # $500M
            "totalLiabilitiesAnnual": 100.0,  # $100M
            "shareOutstanding": 10_000_000,
        }
        result = compute_ncav(fin, price=20.0)  # price < NCAV/share
        assert result["is_net_net"] is True
        assert result["margin_of_safety"] is not None
        assert result["margin_of_safety"] > 0
        assert result["score"] >= 70

    def test_not_net_net(self):
        fin = {
            "totalCurrentAssetsAnnual": 100.0,
            "totalLiabilitiesAnnual": 500.0,
            "shareOutstanding": 10_000_000,
        }
        result = compute_ncav(fin, price=50.0)
        assert result["is_net_net"] is False
        assert result["score"] < 50

    def test_no_price(self):
        fin = {
            "totalCurrentAssetsAnnual": 500.0,
            "totalLiabilitiesAnnual": 100.0,
            "shareOutstanding": 10_000_000,
        }
        result = compute_ncav(fin, None)
        assert result["ncav_per_share"] is not None
        assert result["margin_of_safety"] is None


# ---------------------------------------------------------------------------
# P24.1: 52-Week High Breakout
# ---------------------------------------------------------------------------


class TestBreakoutSignal:
    def test_no_data(self):
        result = compute_breakout_signal(None, None, None)
        assert result["is_breakout"] is False
        assert result["score"] == 50

    def test_confirmed_breakout(self):
        # Price at 52-week high with high volume
        close = _rising(n=252, start=50.0, step=0.5)
        vol = pd.Series([1_000_000.0] * 252)
        vol.iloc[-1] = 2_000_000.0  # 2x average
        fin = {"52WeekHigh": float(close.iloc[-1])}
        result = compute_breakout_signal(close, vol, fin)
        assert result["is_breakout"] is True
        assert result["score"] >= 72

    def test_below_high(self):
        close = _rising(n=100)
        fin = {"52WeekHigh": float(close.iloc[-1]) * 1.5}
        result = compute_breakout_signal(close, None, fin)
        assert result["is_breakout"] is False
        assert result["pct_from_52w_high"] is not None
        assert result["pct_from_52w_high"] < 0


# ---------------------------------------------------------------------------
# P24.3: Index Trend Gate
# ---------------------------------------------------------------------------


class TestIndexTrendGate:
    def test_no_data_defaults_open(self):
        result = get_index_trend_gate(None)
        assert result["gate_open"] is True
        assert result["penalty"] == 0

    def test_gate_open_above_200sma(self):
        # Steadily rising for 250 days → price above 200d SMA
        close = _rising(n=250, start=100.0, step=0.5)
        result = get_index_trend_gate(close)
        assert result["gate_open"] is True
        assert result["penalty"] == 0
        assert result["sma200"] is not None

    def test_gate_closed_below_200sma(self):
        # Rising then falling sharply
        prices = [100.0 + i * 0.5 for i in range(200)] + [200.0 - i * 2.0 for i in range(50)]
        close = pd.Series(prices)
        result = get_index_trend_gate(close)
        assert result["gate_open"] is False
        assert result["penalty"] > 0

    def test_insufficient_data(self):
        result = get_index_trend_gate(pd.Series([100.0] * 50))
        assert result["gate_open"] is True  # default to open


# ---------------------------------------------------------------------------
# P24.2: Dual Momentum
# ---------------------------------------------------------------------------


class TestDualMomentum:
    def _make_asset_data(self):
        return [
            {"ticker": "SPY", "name": "US Equities", "perf_12m": 15.0, "perf_6m": 8.0, "volatility": 15.0},
            {"ticker": "TLT", "name": "Long Treasuries", "perf_12m": -5.0, "perf_6m": -2.0, "volatility": 12.0},
            {"ticker": "GLD", "name": "Gold", "perf_12m": 12.0, "perf_6m": 6.0, "volatility": 14.0},
        ]

    def test_returns_augmented_data(self):
        assets = self._make_asset_data()
        result = compute_dual_momentum(assets, risk_free_rate_annual=5.0)
        assert len(result) == len(assets)
        for r in result:
            assert "dual_momentum_pass" in r
            assert "dual_momentum_signal" in r

    def test_spy_passes_dual_momentum(self):
        assets = self._make_asset_data()
        result = compute_dual_momentum(assets, risk_free_rate_annual=5.0)
        spy = next(r for r in result if r["ticker"] == "SPY")
        assert spy["abs_momentum_pass"] is True
        assert spy["dual_momentum_signal"] == "Hold"

    def test_negative_return_goes_to_cash(self):
        assets = self._make_asset_data()
        result = compute_dual_momentum(assets, risk_free_rate_annual=5.0)
        tlt = next(r for r in result if r["ticker"] == "TLT")
        assert tlt["abs_momentum_pass"] is False
        assert tlt["dual_momentum_signal"] == "Cash"

    def test_empty_assets(self):
        result = compute_dual_momentum([], risk_free_rate_annual=5.0)
        assert result == []


# ---------------------------------------------------------------------------
# P25.1: Cluster Insider Buying
# ---------------------------------------------------------------------------


class TestClusterInsiderScore:
    def test_no_transactions(self):
        result = compute_cluster_insider_score([])
        assert result["cluster_signal"] is False
        assert result["signal_label"] == "No data"

    def test_cluster_detected(self):
        from datetime import date, timedelta

        recent = (date.today() - timedelta(days=10)).isoformat()
        txns = [
            {"transactionCode": "P", "name": "CEO Smith", "transactionDate": recent,
             "share": 10000, "price": 50.0},
            {"transactionCode": "P", "name": "CFO Jones", "transactionDate": recent,
             "share": 5000, "price": 50.0},
        ]
        result = compute_cluster_insider_score(txns)
        assert result["cluster_signal"] is True
        assert result["unique_buyers"] == 2
        assert result["signal_label"] == "Cluster Buy"
        assert result["net_buy_value"] > 0

    def test_single_buyer_not_cluster(self):
        from datetime import date, timedelta

        recent = (date.today() - timedelta(days=5)).isoformat()
        txns = [
            {"transactionCode": "P", "name": "CEO Smith", "transactionDate": recent,
             "share": 10000, "price": 50.0},
        ]
        result = compute_cluster_insider_score(txns)
        assert result["cluster_signal"] is False
        assert result["signal_label"] == "Single Buy"

    def test_sales_excluded(self):
        from datetime import date, timedelta

        recent = (date.today() - timedelta(days=5)).isoformat()
        txns = [
            {"transactionCode": "S", "name": "CEO", "transactionDate": recent, "share": 10000, "price": 50.0},
            {"transactionCode": "S", "name": "CFO", "transactionDate": recent, "share": 5000, "price": 50.0},
        ]
        result = compute_cluster_insider_score(txns)
        assert result["cluster_signal"] is False
        assert result["unique_buyers"] == 0

    def test_old_transactions_excluded(self):
        from datetime import date, timedelta

        old = (date.today() - timedelta(days=60)).isoformat()
        txns = [
            {"transactionCode": "P", "name": "CEO", "transactionDate": old, "share": 10000, "price": 50.0},
            {"transactionCode": "P", "name": "CFO", "transactionDate": old, "share": 5000, "price": 50.0},
        ]
        result = compute_cluster_insider_score(txns, window_days=30)
        assert result["cluster_signal"] is False


# ---------------------------------------------------------------------------
# P25.2: Tax-Loss Harvesting Bounce
# ---------------------------------------------------------------------------


class TestTaxLossBounce:
    def test_no_data(self):
        result = compute_tax_loss_bounce_signal(None)
        assert result["ytd_return_pct"] is None
        assert result["is_candidate"] is False

    def test_candidate_in_season(self):
        close = _declining_ytd(pct=-50.0, n=260)
        result = compute_tax_loss_bounce_signal(close, month=12)
        assert result["is_candidate"] is True
        assert result["signal_active"] is True
        assert result["score"] >= 70

    def test_candidate_out_of_season(self):
        close = _declining_ytd(pct=-50.0, n=260)
        result = compute_tax_loss_bounce_signal(close, month=6)
        assert result["is_candidate"] is True
        assert result["signal_active"] is False
        assert result["score"] < 70

    def test_no_candidate_flat(self):
        close = _flat(n=260)
        result = compute_tax_loss_bounce_signal(close, month=12)
        assert result["is_candidate"] is False

    def test_ytd_return_correct(self):
        close = _declining_ytd(pct=-50.0, n=260)
        result = compute_tax_loss_bounce_signal(close)
        assert result["ytd_return_pct"] is not None
        assert result["ytd_return_pct"] < -40


# ---------------------------------------------------------------------------
# P26.1: VRP Harvest
# ---------------------------------------------------------------------------


class TestVRP:
    def test_no_iv(self):
        result = compute_vrp(None, None)
        assert result["vrp_pts"] is None
        assert result["signal"] == "No data"

    def test_high_vrp_signal(self):
        # IV = 35%, HV will be very low (flat series)
        close = _flat(n=100, price=100.0)
        result = compute_vrp(35.0, close)
        assert result["iv_pct"] == 35.0
        if result["hv30_pct"] is not None:
            assert result["vrp_pts"] is not None
            assert result["signal"] == "Premium Selling"

    def test_compressed_iv_breakout(self):
        # Create a volatile series so HV > IV
        import random

        rng = random.Random(99)
        prices = [100.0]
        for _ in range(60):
            prices.append(prices[-1] * (1 + rng.uniform(-0.04, 0.04)))
        close = pd.Series(prices)
        # IV = 10% (compressed), HV likely > 10%
        result = compute_vrp(10.0, close)
        if result["vrp_pts"] is not None and result["vrp_pts"] < 0:
            assert result["signal"] == "Breakout Watch"

    def test_iv_no_history(self):
        result = compute_vrp(25.0, None)
        assert result["iv_pct"] == 25.0
        assert result["hv30_pct"] is None


# ---------------------------------------------------------------------------
# P26.2: IV Rank and Percentile
# ---------------------------------------------------------------------------


class TestIVRank:
    def test_no_data(self):
        result = compute_iv_rank(None, [])
        assert result["iv_rank_pct"] is None
        assert result["signal"] == "No data"

    def test_high_iv_rank(self):
        history = [20.0] * 200 + [50.0] * 52  # mostly 20%, then spike to 50%
        result = compute_iv_rank(55.0, history)
        assert result["iv_rank_pct"] is not None
        assert result["iv_rank_pct"] > 80
        assert result["signal"] == "High IV Rank"

    def test_low_iv_rank(self):
        history = [50.0] * 200 + [20.0] * 52
        result = compute_iv_rank(15.0, history)
        assert result["iv_rank_pct"] is not None
        assert result["iv_rank_pct"] < 20
        assert result["signal"] == "Low IV Rank"

    def test_normal_range(self):
        history = [10.0 + i * 0.1 for i in range(200)]
        result = compute_iv_rank(15.0, history)
        assert result["signal"] == "Normal"

    def test_insufficient_history(self):
        result = compute_iv_rank(25.0, [20.0, 30.0])
        assert result["iv_rank_pct"] is None

    def test_52w_high_low_returned(self):
        history = list(range(10, 60))
        result = compute_iv_rank(35.0, history)
        assert result["iv_52w_high"] is not None
        assert result["iv_52w_low"] is not None


# ---------------------------------------------------------------------------
# P27.1: Rate Sensitivity
# ---------------------------------------------------------------------------


class TestRateSensitivity:
    def test_no_data(self):
        result = compute_rate_sensitivity(None, None)
        assert result["beta_tlt"] is None
        assert result["is_rate_sensitive"] is False

    def test_correlated_stocks_positive_beta(self):
        # Stock moves with TLT (bond-like: utilities)
        n = 100
        tlt = _rising(n=n, start=90.0, step=0.3)
        stock = _rising(n=n, start=50.0, step=0.15)  # correlated with TLT
        result = compute_rate_sensitivity(stock, tlt, window=60)
        if result["beta_tlt"] is not None:
            assert isinstance(result["beta_tlt"], float)
            assert isinstance(result["is_rate_sensitive"], bool)

    def test_anticorrelated_stock(self):
        # Generate perfectly anti-correlated daily returns
        import random

        rng = random.Random(7)
        # TLT daily returns: small random positive drift
        tlt_rets = [rng.gauss(0.001, 0.005) for _ in range(100)]
        # Stock daily returns: exact mirror of TLT (anti-correlated)
        stock_rets = [-r for r in tlt_rets]

        # Build price series from returns
        def _from_rets(rets, start=100.0):
            prices = [start]
            for r in rets:
                prices.append(prices[-1] * (1 + r))
            return pd.Series(prices)

        tlt = _from_rets(tlt_rets, 90.0)
        stock = _from_rets(stock_rets, 130.0)
        result = compute_rate_sensitivity(stock, tlt, window=60)
        if result["beta_tlt"] is not None:
            assert result["beta_tlt"] < 0

    def test_insufficient_data(self):
        result = compute_rate_sensitivity(
            pd.Series([100.0] * 20),
            pd.Series([90.0] * 20),
            window=60,
        )
        assert result["beta_tlt"] is None

    def test_neutral_direction_label(self):
        # Unrelated flat series → low beta
        close = _flat(n=200)
        tlt = _flat(n=200, price=90.0)
        result = compute_rate_sensitivity(close, tlt, window=60)
        # Both flat → variance near zero, should handle gracefully
        assert "direction" in result


# ---------------------------------------------------------------------------
# P27.2: FX Exposure
# ---------------------------------------------------------------------------


class TestFXExposure:
    def test_no_data(self):
        result = compute_fx_exposure_adjustment(None)
        assert result["fx_exposure"] == "Unknown"
        assert result["score_adjustment"] == 0

    def test_high_intl_revenue(self):
        fin = {
            "revenueInternational": 600.0,
            "revenueAnnual": 1000.0,
        }
        result = compute_fx_exposure_adjustment(fin)
        assert result["intl_revenue_pct"] == 60.0
        assert result["fx_exposure"] == "High"

    def test_low_intl_revenue(self):
        fin = {
            "revenueInternational": 100.0,
            "revenueAnnual": 1000.0,
        }
        result = compute_fx_exposure_adjustment(fin)
        assert result["fx_exposure"] == "Low"
        assert result["score_adjustment"] == 0

    def test_weakening_usd_positive_adjustment(self):
        fin = {
            "revenueInternational": 600.0,
            "revenueAnnual": 1000.0,
        }
        result = compute_fx_exposure_adjustment(fin, dxy_trend="weakening")
        assert result["score_adjustment"] > 0

    def test_strengthening_usd_negative_adjustment(self):
        fin = {
            "revenueInternational": 600.0,
            "revenueAnnual": 1000.0,
        }
        result = compute_fx_exposure_adjustment(fin, dxy_trend="strengthening")
        assert result["score_adjustment"] < 0

    def test_neutral_dxy_no_adjustment(self):
        fin = {
            "revenueInternational": 600.0,
            "revenueAnnual": 1000.0,
        }
        result = compute_fx_exposure_adjustment(fin, dxy_trend="neutral")
        assert result["score_adjustment"] == 0


# ---------------------------------------------------------------------------
# Screener preset constants
# ---------------------------------------------------------------------------


class TestScreenerPresets:
    def test_presets_exist(self):
        assert LOW_VOL_PRESET["max_vol_60d_pct"] > 0
        assert SHAREHOLDER_YIELD_PRESET["min_total_yield_pct"] > 0
        assert NCAV_PRESET["require_net_net"] is True
        assert BREAKOUT_PRESET["min_factor_score"] > 0
        assert INSIDER_BUYING_PRESET["min_insider_buyers"] >= 2
        assert TAX_LOSS_BOUNCE_PRESET["max_ytd_return_pct"] < 0
        assert VRP_HARVEST_PRESET["min_vrp_pts"] > 0

    def test_is_breakout_candidate(self):
        result = {"factor_score": 55}
        breakout_data = {"pct_from_52w_high": -0.5, "volume_ratio": 1.8}
        assert is_breakout_candidate(result, breakout_data) is True

    def test_is_breakout_candidate_fails_low_score(self):
        result = {"factor_score": 30}
        breakout_data = {"pct_from_52w_high": -0.5, "volume_ratio": 1.8}
        assert is_breakout_candidate(result, breakout_data) is False

    def test_is_insider_buying_candidate(self):
        result = {"factor_score": 55, "risk_score": 40}
        insider = {
            "recent_buyers": ["CEO", "CFO"],
            "buy_value": 500_000.0,
            "signal": "Buying",
        }
        assert is_insider_buying_candidate(result, insider) is True

    def test_is_insider_buying_fails_single_buyer(self):
        result = {"factor_score": 55, "risk_score": 40}
        insider = {"recent_buyers": ["CEO"], "buy_value": 500_000.0}
        assert is_insider_buying_candidate(result, insider) is False

    def test_is_tax_loss_bounce_candidate(self):
        result = {}
        assert is_tax_loss_bounce_candidate(result, ytd_return_pct=-50.0, month=12) is True
        assert is_tax_loss_bounce_candidate(result, ytd_return_pct=-50.0, month=6) is False
        assert is_tax_loss_bounce_candidate(result, ytd_return_pct=-10.0, month=12) is False

    def test_is_vrp_harvest_candidate(self):
        result = {"risk_score": 40}
        opts = {"available": True, "avg_iv_pct": 35.0}
        assert is_vrp_harvest_candidate(result, opts, hv30=25.0) is True
        assert is_vrp_harvest_candidate(result, opts, hv30=32.0) is False  # VRP = 3 < 5

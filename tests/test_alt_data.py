"""Tests for Feature 21.5 — Alternative Data Signal.

Covers:
- fetch_google_trends() with mocked pytrends
- fetch_job_posting_velocity() with mocked requests
- compute_alt_data_signals() combination logic
- _factor_alt_data() scoring and graceful degradation
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# fetch_google_trends
# ---------------------------------------------------------------------------


def _make_trends_df(values: list[int], keyword: str = "Apple Inc") -> pd.DataFrame:
    """Build a minimal DataFrame mimicking pytrends output."""
    return pd.DataFrame({keyword: values})


class TestFetchGoogleTrends:
    def test_accelerating_trend_scores_above_50(self):
        """Upward slope should produce a score > 50."""
        from src.data.alt_data import fetch_google_trends

        mock_pt = MagicMock()
        mock_pt.interest_over_time.return_value = _make_trends_df(
            [30, 35, 40, 50, 60, 70, 80], "Apple Inc"
        )

        with patch("src.data.alt_data.TrendReq", return_value=mock_pt, create=True):
            with patch.dict(
                "sys.modules",
                {"pytrends": MagicMock(), "pytrends.request": MagicMock()},
            ):
                # Patch inside the function's local import
                import sys

                # Replace pytrends.request.TrendReq
                mock_pytrends_module = MagicMock()
                mock_pytrends_module.request.TrendReq = MagicMock(return_value=mock_pt)
                sys.modules["pytrends"] = mock_pytrends_module
                sys.modules["pytrends.request"] = mock_pytrends_module.request

                result = fetch_google_trends("Apple Inc")

        assert result["available"] is True
        assert result["score"] > 50
        assert result["slope"] > 0

    def test_decelerating_trend_scores_below_50(self):
        """Downward slope should produce a score < 50."""
        from src.data.alt_data import fetch_google_trends

        mock_pt = MagicMock()
        mock_pt.interest_over_time.return_value = _make_trends_df(
            [80, 70, 60, 50, 40, 35, 30], "Apple Inc"
        )

        import sys

        mock_pytrends_module = MagicMock()
        mock_pytrends_module.request.TrendReq = MagicMock(return_value=mock_pt)
        sys.modules["pytrends"] = mock_pytrends_module
        sys.modules["pytrends.request"] = mock_pytrends_module.request

        result = fetch_google_trends("Apple Inc")

        assert result["available"] is True
        assert result["score"] < 50
        assert result["slope"] < 0

    def test_stable_trend_scores_near_50(self):
        """Flat slope should produce a score close to 50."""
        from src.data.alt_data import fetch_google_trends

        mock_pt = MagicMock()
        mock_pt.interest_over_time.return_value = _make_trends_df(
            [50, 51, 49, 50, 51, 50, 50], "Apple Inc"
        )

        import sys

        mock_pytrends_module = MagicMock()
        mock_pytrends_module.request.TrendReq = MagicMock(return_value=mock_pt)
        sys.modules["pytrends"] = mock_pytrends_module
        sys.modules["pytrends.request"] = mock_pytrends_module.request

        result = fetch_google_trends("Apple Inc")

        assert result["available"] is True
        assert 35 <= result["score"] <= 65

    def test_missing_pytrends_returns_unavailable(self):
        """When pytrends is not installed, should return available=False."""
        import sys

        # Remove any mock pytrends from sys.modules
        sys.modules.pop("pytrends", None)
        sys.modules.pop("pytrends.request", None)

        with patch.dict("sys.modules", {"pytrends": None, "pytrends.request": None}):
            from src.data.alt_data import fetch_google_trends

            result = fetch_google_trends("Apple Inc")

        assert result["available"] is False

    def test_empty_dataframe_returns_unavailable(self):
        """Empty DataFrame from pytrends should return available=False."""
        from src.data.alt_data import fetch_google_trends

        mock_pt = MagicMock()
        mock_pt.interest_over_time.return_value = pd.DataFrame()

        import sys

        mock_pytrends_module = MagicMock()
        mock_pytrends_module.request.TrendReq = MagicMock(return_value=mock_pt)
        sys.modules["pytrends"] = mock_pytrends_module
        sys.modules["pytrends.request"] = mock_pytrends_module.request

        result = fetch_google_trends("Apple Inc")

        assert result["available"] is False

    def test_api_exception_returns_unavailable(self):
        """Network error from pytrends should return available=False."""
        from src.data.alt_data import fetch_google_trends

        mock_pt = MagicMock()
        mock_pt.interest_over_time.side_effect = RuntimeError("connection error")

        import sys

        mock_pytrends_module = MagicMock()
        mock_pytrends_module.request.TrendReq = MagicMock(return_value=mock_pt)
        sys.modules["pytrends"] = mock_pytrends_module
        sys.modules["pytrends.request"] = mock_pytrends_module.request

        result = fetch_google_trends("Apple Inc")

        assert result["available"] is False

    def test_score_clamped_to_0_100(self):
        """Extreme slope values should be clamped within 0-100."""
        from src.data.alt_data import fetch_google_trends

        mock_pt = MagicMock()
        # Extreme acceleration
        mock_pt.interest_over_time.return_value = _make_trends_df(
            [1, 2, 3, 5, 10, 50, 100], "Apple Inc"
        )

        import sys

        mock_pytrends_module = MagicMock()
        mock_pytrends_module.request.TrendReq = MagicMock(return_value=mock_pt)
        sys.modules["pytrends"] = mock_pytrends_module
        sys.modules["pytrends.request"] = mock_pytrends_module.request

        result = fetch_google_trends("Apple Inc")

        assert result["available"] is True
        assert 0 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# fetch_job_posting_velocity
# ---------------------------------------------------------------------------


class TestFetchJobPostingVelocity:
    def _mock_adzuna_response(self, count: int) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"count": count}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_no_credentials_returns_unavailable(self):
        """Missing Adzuna credentials should return available=False."""
        from src.data.alt_data import fetch_job_posting_velocity

        with patch.dict("os.environ", {}, clear=True):
            # Ensure env vars are absent
            import os

            os.environ.pop("ADZUNA_APP_ID", None)
            os.environ.pop("ADZUNA_APP_KEY", None)

            result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is False

    def test_rapid_hiring_scores_above_60(self):
        """Significant positive velocity should produce a score > 60."""
        from src.data.alt_data import fetch_job_posting_velocity

        # recent=200, prior=100 → +100% velocity
        responses = [self._mock_adzuna_response(200), self._mock_adzuna_response(100)]

        with patch.dict(
            "os.environ", {"ADZUNA_APP_ID": "test_id", "ADZUNA_APP_KEY": "test_key"}
        ):
            with patch("requests.get", side_effect=responses):
                result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is True
        assert result["velocity_pct"] == pytest.approx(100.0)
        assert result["score"] > 60

    def test_layoffs_scores_below_40(self):
        """Significant negative velocity should produce a score < 40."""
        from src.data.alt_data import fetch_job_posting_velocity

        # recent=50, prior=100 → -50% velocity
        responses = [self._mock_adzuna_response(50), self._mock_adzuna_response(100)]

        with patch.dict(
            "os.environ", {"ADZUNA_APP_ID": "test_id", "ADZUNA_APP_KEY": "test_key"}
        ):
            with patch("requests.get", side_effect=responses):
                result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is True
        assert result["velocity_pct"] == pytest.approx(-50.0)
        assert result["score"] < 40

    def test_stable_hiring_scores_near_50(self):
        """Near-zero velocity should produce a score close to 50."""
        from src.data.alt_data import fetch_job_posting_velocity

        responses = [self._mock_adzuna_response(100), self._mock_adzuna_response(102)]

        with patch.dict(
            "os.environ", {"ADZUNA_APP_ID": "test_id", "ADZUNA_APP_KEY": "test_key"}
        ):
            with patch("requests.get", side_effect=responses):
                result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is True
        assert 40 <= result["score"] <= 60

    def test_zero_postings_returns_unavailable(self):
        """Both periods returning 0 postings should give available=False."""
        from src.data.alt_data import fetch_job_posting_velocity

        responses = [self._mock_adzuna_response(0), self._mock_adzuna_response(0)]

        with patch.dict(
            "os.environ", {"ADZUNA_APP_ID": "test_id", "ADZUNA_APP_KEY": "test_key"}
        ):
            with patch("requests.get", side_effect=responses):
                result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is False

    def test_api_exception_returns_unavailable(self):
        """Network error should return available=False."""
        from src.data.alt_data import fetch_job_posting_velocity

        with patch.dict(
            "os.environ", {"ADZUNA_APP_ID": "test_id", "ADZUNA_APP_KEY": "test_key"}
        ):
            with patch("requests.get", side_effect=ConnectionError("timeout")):
                result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is False

    def test_score_clamped_to_0_100(self):
        """Extreme velocity should be clamped within 0-100."""
        from src.data.alt_data import fetch_job_posting_velocity

        # recent=10000, prior=1 → extreme positive velocity
        responses = [self._mock_adzuna_response(10000), self._mock_adzuna_response(1)]

        with patch.dict(
            "os.environ", {"ADZUNA_APP_ID": "test_id", "ADZUNA_APP_KEY": "test_key"}
        ):
            with patch("requests.get", side_effect=responses):
                result = fetch_job_posting_velocity("Apple Inc")

        assert result["available"] is True
        assert 0 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# compute_alt_data_signals
# ---------------------------------------------------------------------------


class TestComputeAltDataSignals:
    def _trends_available(self, score: int = 68) -> dict:
        return {
            "available": True,
            "values": [45, 55, 65, 68],
            "slope": 0.035,
            "score": score,
            "label": "Accelerating interest",
            "detail": "Trends detail",
        }

    def _jobs_available(self, score: int = 56) -> dict:
        return {
            "available": True,
            "recent_count": 120,
            "prior_count": 100,
            "velocity_pct": 20.0,
            "score": score,
            "label": "Hiring growth",
            "detail": "Jobs detail",
        }

    def test_both_available_combines_with_equal_weight(self):
        """When both signals are available, combines at 50/50 by default."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value=self._trends_available(60),
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value=self._jobs_available(40),
            ),
        ):
            result = compute_alt_data_signals("AAPL", "Apple Inc")

        assert result["available"] is True
        assert result["score"] == 50  # (60*0.5 + 40*0.5) / 1.0

    def test_only_trends_available(self):
        """When only Trends is available, uses its score at full weight."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value=self._trends_available(70),
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value={"available": False},
            ),
        ):
            result = compute_alt_data_signals("AAPL", "Apple Inc")

        assert result["available"] is True
        assert result["score"] == 70

    def test_only_jobs_available(self):
        """When only Jobs is available, uses its score at full weight."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value={"available": False},
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value=self._jobs_available(30),
            ),
        ):
            result = compute_alt_data_signals("AAPL", "Apple Inc")

        assert result["available"] is True
        assert result["score"] == 30

    def test_neither_available_returns_unavailable(self):
        """When both signals fail, returns available=False with neutral score."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value={"available": False},
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value={"available": False},
            ),
        ):
            result = compute_alt_data_signals("AAPL", "Apple Inc")

        assert result["available"] is False
        assert result["score"] == 50  # neutral fallback

    def test_positive_label_for_high_score(self):
        """Score >= 65 should produce a positive label."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value=self._trends_available(80),
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value=self._jobs_available(80),
            ),
        ):
            result = compute_alt_data_signals("AAPL", "Apple Inc")

        assert "Positive" in result["label"]

    def test_negative_label_for_low_score(self):
        """Score <= 35 should produce a negative label."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value=self._trends_available(20),
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value=self._jobs_available(20),
            ),
        ):
            result = compute_alt_data_signals("AAPL", "Apple Inc")

        assert "Negative" in result["label"]

    def test_custom_weights_applied(self):
        """Custom trends_weight/jobs_weight should alter the combined score."""
        from src.data.alt_data import compute_alt_data_signals

        with (
            patch(
                "src.data.alt_data.fetch_google_trends",
                return_value=self._trends_available(80),
            ),
            patch(
                "src.data.alt_data.fetch_job_posting_velocity",
                return_value=self._jobs_available(20),
            ),
        ):
            # Trends weight 0.9, jobs 0.1 → should be close to 80
            result = compute_alt_data_signals(
                "AAPL", "Apple Inc", trends_weight=0.9, jobs_weight=0.1
            )

        assert result["score"] > 65  # heavily trends-weighted


# ---------------------------------------------------------------------------
# _factor_alt_data
# ---------------------------------------------------------------------------


class TestFactorAltData:
    def test_unavailable_returns_neutral_50(self):
        """None input should return neutral score of 50."""
        from src.analysis.factors import _factor_alt_data

        result = _factor_alt_data(None)

        assert result["score"] == 50
        assert result["name"] == "Alt Data Signal"
        assert result["label"] == "No data"

    def test_unavailable_dict_returns_neutral_50(self):
        """Dict with available=False should return neutral score of 50."""
        from src.analysis.factors import _factor_alt_data

        result = _factor_alt_data({"available": False, "detail": "No credentials"})

        assert result["score"] == 50

    def test_available_data_uses_score(self):
        """Dict with available=True should use the provided score."""
        from src.analysis.factors import _factor_alt_data

        alt = {
            "available": True,
            "score": 72,
            "label": "Positive alt signal",
            "detail": "Trends: Accelerating | Jobs: Hiring growth",
        }
        result = _factor_alt_data(alt)

        assert result["score"] == 72
        assert result["label"] == "Positive alt signal"
        assert result["name"] == "Alt Data Signal"

    def test_factor_has_required_keys(self):
        """Factor dict must have all required keys for the factor engine."""
        from src.analysis.factors import _factor_alt_data

        result = _factor_alt_data(None)
        required = {"name", "score", "weight", "label", "detail"}
        assert required.issubset(result.keys())

    def test_weight_is_positive(self):
        """Factor weight should be a positive float."""
        from src.analysis.factors import _factor_alt_data

        result = _factor_alt_data(None)
        assert result["weight"] > 0

    def test_score_in_valid_range(self):
        """Score should always be in 0-100 range."""
        from src.analysis.factors import _factor_alt_data

        for score in [0, 25, 50, 75, 100]:
            result = _factor_alt_data(
                {"available": True, "score": score, "label": "test", "detail": ""}
            )
            assert 0 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# compute_factors integration
# ---------------------------------------------------------------------------


class TestComputeFactorsWithAltData:
    def _base_args(self):
        import pandas as pd

        close = pd.Series([100.0, 102.0, 101.0, 103.0, 105.0] * 10)
        return {
            "quote": {"c": 105.0, "pc": 100.0, "h": 106.0, "l": 99.0},
            "financials": None,
            "close": close,
            "earnings": [],
            "recommendations": [],
            "sentiment_agg": None,
        }

    def test_compute_factors_includes_alt_data_factor(self):
        """compute_factors should include Alt Data Signal in the result."""
        from src.analysis.factors import compute_factors

        args = self._base_args()
        alt = {
            "available": True,
            "score": 65,
            "label": "Positive alt signal",
            "detail": "",
        }
        factors = compute_factors(**args, alt_data=alt)
        names = [f["name"] for f in factors]
        assert "Alt Data Signal" in names

    def test_compute_factors_without_alt_data_defaults_to_neutral(self):
        """compute_factors with alt_data=None should score Alt Data as 50."""
        from src.analysis.factors import compute_factors

        args = self._base_args()
        factors = compute_factors(**args, alt_data=None)
        alt_factor = next(f for f in factors if f["name"] == "Alt Data Signal")
        assert alt_factor["score"] == 50

    def test_compute_factors_alt_data_affects_composite(self):
        """A high alt data score should raise the composite vs a low score."""
        from src.analysis.factors import compute_factors, composite_score

        args = self._base_args()
        high_alt = {
            "available": True,
            "score": 95,
            "label": "Positive alt signal",
            "detail": "",
        }
        low_alt = {
            "available": True,
            "score": 5,
            "label": "Negative alt signal",
            "detail": "",
        }

        composite_high = composite_score(compute_factors(**args, alt_data=high_alt))
        composite_low = composite_score(compute_factors(**args, alt_data=low_alt))

        assert composite_high > composite_low

"""Tests for src/analysis/executive_tone.py and the _factor_executive_tone factor.

Covers:
- Executive speech extraction from transcripts
- Tone score conversion from Claude analysis dict
- Factor function return shape and score range
- Graceful fallback when no transcript / no AI available
- Cache behaviour (result stored, retrieved on second call)
- Integration with compute_factors()
"""

from __future__ import annotations

from unittest.mock import patch

from src.analysis.executive_tone import (
    _extract_executive_speech,
    _score_from_analysis,
    compute_executive_tone_score,
)
from src.analysis.factors import FACTOR_ABSENT_LABEL, _factor_executive_tone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_TRANSCRIPT = {
    "symbol": "AAPL",
    "transcript": [
        {
            "name": "Operator",
            "speech": ["Good afternoon and welcome to the earnings call."],
        },
        {
            "name": "CEO",
            "speech": [
                "Revenue grew 15% year-over-year driven by strong iPhone demand.",
                "We expect Q2 revenue in the range of $89 to $92 billion.",
                "We believe our services segment will continue to outperform.",
            ],
        },
        {
            "name": "CFO",
            "speech": [
                "Gross margin was 46.2%, up 180 basis points year-over-year.",
                "We returned $24 billion to shareholders this quarter.",
            ],
        },
        {
            "name": "Analyst",
            "speech": ["Can you explain the revenue headwinds?"],
        },
    ],
}

_MINIMAL_ANALYSIS = {
    "overall_score": 70,
    "confidence_score": 72,
    "transparency_score": 65,
    "hedging_score": 60,
    "forward_guidance_score": 75,
    "tone_shift_score": 55,
    "dominant_tone": "Confident",
    "key_signals": ["revenue grew 15%", "we expect Q2 revenue in the range of"],
    "summary": "Executives communicated with moderate confidence and specific guidance.",
}


class _MockAPI:
    def get_transcripts_list(self, symbol):
        return [
            {"id": f"{symbol}_2025_Q4", "title": f"{symbol} Q4 2025 Earnings Call"},
            {"id": f"{symbol}_2025_Q3", "title": f"{symbol} Q3 2025 Earnings Call"},
        ]

    def get_transcript(self, transcript_id):
        return _MOCK_TRANSCRIPT


class _EmptyAPI:
    def get_transcripts_list(self, symbol):
        return []

    def get_transcript(self, transcript_id):
        return {}


class _FailingAPI:
    def get_transcripts_list(self, symbol):
        raise RuntimeError("API unavailable")

    def get_transcript(self, transcript_id):
        raise RuntimeError("API unavailable")


# ---------------------------------------------------------------------------
# _extract_executive_speech
# ---------------------------------------------------------------------------


def test_extract_excludes_operator_and_analyst():
    text = _extract_executive_speech(_MOCK_TRANSCRIPT)
    assert "Operator" not in text
    assert "Analyst" not in text
    assert "CEO" in text
    assert "CFO" in text


def test_extract_contains_executive_speech_content():
    text = _extract_executive_speech(_MOCK_TRANSCRIPT)
    assert "Revenue grew 15%" in text
    assert "Gross margin was 46.2%" in text


def test_extract_empty_transcript():
    assert _extract_executive_speech({}) == ""
    assert _extract_executive_speech({"transcript": []}) == ""


def test_extract_truncates_long_text():
    long_speech = "x" * 10_000
    transcript = {
        "transcript": [{"name": "CEO", "speech": [long_speech]}]
    }
    text = _extract_executive_speech(transcript)
    assert len(text) <= 6100  # within _MAX_TRANSCRIPT_CHARS + small margin


def test_extract_no_executive_roles():
    transcript = {
        "transcript": [
            {"name": "Operator", "speech": ["Welcome everyone."]},
            {"name": "Analyst from Morgan Stanley", "speech": ["Can you comment?"]},
        ]
    }
    text = _extract_executive_speech(transcript)
    assert text == ""


# ---------------------------------------------------------------------------
# _score_from_analysis
# ---------------------------------------------------------------------------


def test_score_from_analysis_range():
    result = _score_from_analysis(_MINIMAL_ANALYSIS)
    assert 0 <= result["score"] <= 100


def test_score_from_analysis_has_required_keys():
    result = _score_from_analysis(_MINIMAL_ANALYSIS)
    assert "score" in result
    assert "label" in result
    assert "detail" in result
    assert "dominant_tone" in result
    assert "sub_signals" in result


def test_score_from_analysis_sub_signals():
    result = _score_from_analysis(_MINIMAL_ANALYSIS)
    sub = result["sub_signals"]
    assert "confidence" in sub
    assert "transparency" in sub
    assert "hedging" in sub
    assert "forward_guidance" in sub
    assert "tone_shift" in sub


def test_score_from_analysis_confident_label():
    high_confidence = {**_MINIMAL_ANALYSIS, "overall_score": 90, "confidence_score": 95}
    result = _score_from_analysis(high_confidence)
    assert "confidence" in result["label"].lower() or result["score"] >= 70


def test_score_from_analysis_defensive_label():
    low_confidence = {
        **_MINIMAL_ANALYSIS,
        "overall_score": 15,
        "confidence_score": 20,
        "transparency_score": 20,
        "hedging_score": 10,
        "forward_guidance_score": 15,
        "tone_shift_score": 20,
    }
    result = _score_from_analysis(low_confidence)
    assert result["score"] <= 30


def test_score_from_analysis_none_tone_shift():
    analysis = {**_MINIMAL_ANALYSIS, "tone_shift_score": None}
    result = _score_from_analysis(analysis)
    assert isinstance(result["score"], int)
    assert result["sub_signals"]["tone_shift"] == 50


# ---------------------------------------------------------------------------
# _factor_executive_tone
# ---------------------------------------------------------------------------


def test_factor_no_data_returns_absent():
    f = _factor_executive_tone(None)
    assert f["name"] == "Executive Tone"
    assert f["score"] == 50
    assert f["label"] == FACTOR_ABSENT_LABEL
    assert 0 < f["weight"] <= 1.0


def test_factor_with_data_returns_valid_score():
    tone_data = _score_from_analysis(_MINIMAL_ANALYSIS)
    f = _factor_executive_tone(tone_data)
    assert f["name"] == "Executive Tone"
    assert 0 <= f["score"] <= 100
    assert f["label"] != FACTOR_ABSENT_LABEL
    assert "sub_signals" in f


def test_factor_score_in_range():
    for overall in [0, 25, 50, 75, 100]:
        analysis = {**_MINIMAL_ANALYSIS, "overall_score": overall}
        tone_data = _score_from_analysis(analysis)
        f = _factor_executive_tone(tone_data)
        assert 0 <= f["score"] <= 100


# ---------------------------------------------------------------------------
# compute_executive_tone_score — integration
# ---------------------------------------------------------------------------


def test_returns_none_when_no_transcripts():
    result = compute_executive_tone_score("AAPL", _EmptyAPI())
    assert result is None


def test_returns_none_when_api_fails():
    result = compute_executive_tone_score("AAPL", _FailingAPI())
    assert result is None


def test_returns_none_when_no_executive_speech():
    """Transcripts with only operator/analyst speech → None."""

    class _NoExecAPI:
        def get_transcripts_list(self, symbol):
            return [{"id": "X_Q1"}]

        def get_transcript(self, transcript_id):
            return {
                "transcript": [
                    {"name": "Operator", "speech": ["Welcome."]},
                ]
            }

    result = compute_executive_tone_score("X", _NoExecAPI())
    assert result is None


def test_returns_none_when_claude_unavailable():
    """When Claude call fails, should return None gracefully (no cached result)."""
    import time

    unique_id = f"NOAI_{int(time.time() * 1000)}_Q4"

    class _FreshAPI:
        def get_transcripts_list(self, symbol):
            return [{"id": unique_id}]

        def get_transcript(self, transcript_id):
            return _MOCK_TRANSCRIPT

    with patch("src.analysis.executive_tone._call_claude_for_tone", return_value=None):
        result = compute_executive_tone_score("FRESH", _FreshAPI())
        assert result is None


def test_returns_dict_when_claude_succeeds():
    """When Claude returns a valid analysis, result is a proper dict."""
    import time

    unique_id = f"OK_{int(time.time() * 1000)}_Q4"

    class _FreshAPI:
        def get_transcripts_list(self, symbol):
            return [{"id": unique_id}]

        def get_transcript(self, transcript_id):
            return _MOCK_TRANSCRIPT

    with patch(
        "src.analysis.executive_tone._call_claude_for_tone",
        return_value=_MINIMAL_ANALYSIS,
    ):
        result = compute_executive_tone_score("FRESH2", _FreshAPI())
        assert result is not None
        assert "score" in result
        assert "label" in result
        assert "sub_signals" in result
        assert 0 <= result["score"] <= 100


def test_result_is_cached_on_second_call():
    """Second call should return cached result without calling Claude."""
    import time

    call_count = {"n": 0}
    original = _MINIMAL_ANALYSIS.copy()
    # Use a unique transcript ID to avoid cross-test cache pollution
    unique_id = f"TESTCACHE_{int(time.time() * 1000)}_Q4"

    def _fake_claude(symbol, text, prior=None):
        call_count["n"] += 1
        return original

    class _CacheTestAPI:
        def get_transcripts_list(self, symbol):
            return [{"id": unique_id}]

        def get_transcript(self, transcript_id):
            return _MOCK_TRANSCRIPT

    with patch("src.analysis.executive_tone._call_claude_for_tone", side_effect=_fake_claude):
        r1 = compute_executive_tone_score("TESTCACHE", _CacheTestAPI())
        r2 = compute_executive_tone_score("TESTCACHE", _CacheTestAPI())

    # Claude should have been called only once; second call hits disk cache
    assert call_count["n"] == 1
    assert r1 is not None
    assert r2 is not None


# ---------------------------------------------------------------------------
# compute_factors() integration
# ---------------------------------------------------------------------------


def test_compute_factors_accepts_executive_tone_data():
    """compute_factors() should accept executive_tone_data without error."""
    import pandas as pd
    from src.analysis.factors import compute_factors

    tone_data = _score_from_analysis(_MINIMAL_ANALYSIS)
    factors = compute_factors(
        quote={"c": 150.0},
        financials=None,
        close=pd.Series([100.0] * 50),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        executive_tone_data=tone_data,
    )
    names = [f["name"] for f in factors]
    assert "Executive Tone" in names


def test_compute_factors_executive_tone_score_in_range():
    """Executive Tone factor score is 0-100 in the full factor list."""
    import pandas as pd
    from src.analysis.factors import compute_factors

    tone_data = _score_from_analysis(_MINIMAL_ANALYSIS)
    factors = compute_factors(
        quote={"c": 150.0},
        financials=None,
        close=pd.Series([100.0] * 50),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
        executive_tone_data=tone_data,
    )
    tone_factor = next(f for f in factors if f["name"] == "Executive Tone")
    assert 0 <= tone_factor["score"] <= 100


def test_compute_factors_executive_tone_absent_by_default():
    """When executive_tone_data is None, factor has FACTOR_ABSENT_LABEL."""
    import pandas as pd
    from src.analysis.factors import compute_factors

    factors = compute_factors(
        quote={"c": 150.0},
        financials=None,
        close=pd.Series([100.0] * 50),
        earnings=[],
        recommendations=[],
        sentiment_agg=None,
    )
    tone_factor = next(f for f in factors if f["name"] == "Executive Tone")
    assert tone_factor["label"] == FACTOR_ABSENT_LABEL
    assert tone_factor["score"] == 50

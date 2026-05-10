"""Executive Tone Linguistic Analysis.

Analyzes the language, voice tone, and communication patterns of company
executives from earnings call transcripts and SEC filings (10-K/10-Q MD&A)
to derive forward-looking confidence signals.

Sub-signals scored 0-100:
    - confidence      : specificity and assertiveness in language
    - transparency    : openness about challenges and risks
    - hedging         : frequency of qualifying / weasel language (high = bad)
    - forward_guidance: how specific and committed the guidance is
    - tone_shift      : improvement vs. prior quarter (50 = no prior data)

The composite executive_tone_score is a weighted average of these sub-signals.
Hedging is inverted: high hedging density → lower sub-score.

Uses Claude AI for analysis; falls back to neutral (score=50) when:
  - No transcript is available for the symbol
  - The AI backend raises any exception

Results are disk-cached by transcript ID (24-hour TTL) to avoid redundant
API calls between Streamlit page refreshes.
"""

from __future__ import annotations

import json
import re

from src.core.cache import get_cache, CACHE_MISS
from src.core.log_setup import get_logger

log = get_logger(__name__)
_disk_cache = get_cache()

_TONE_CACHE_TTL = 86400  # 24 hours — transcripts don't change within a quarter

# Roles that represent executive speech we want to analyze.
_EXECUTIVE_ROLES = {
    "ceo", "cfo", "coo", "president", "chairman",
    "chief executive", "chief financial", "chief operating",
    "vice president", "svp", "evp", "general counsel",
    "chief revenue", "chief technology", "cto",
}

# Maximum characters of transcript text to send to Claude (fits within ~1500 tokens)
_MAX_TRANSCRIPT_CHARS = 6000

_ANALYSIS_SYSTEM_PROMPT = """\
You are a financial linguist and expert at analyzing executive communication patterns.
Your task is to evaluate how executives speak during earnings calls and in financial
filings — not what they say, but HOW they say it. You will return a JSON object only,
with no preamble or explanation.

Focus on:
- Specificity: do executives give concrete numbers, dates, and commitments, or are
  they vague ("we expect continued improvement", "we believe", "going forward")?
- Confidence: assertive vs. hedged language; past tense certainty vs. future tense hedging
- Transparency: do they proactively acknowledge problems and explain root causes?
- Hedging density: count of qualifiers like "may", "might", "could", "potentially",
  "subject to", "we believe", "approximately", "in the range of", "we hope"
- Forward guidance quality: are numerical targets given with specific time horizons?
- Tone shift vs prior quarter: does the language sound more or less confident than before?
"""

_ANALYSIS_USER_PROMPT = """\
Analyze the following executive speech from {symbol}'s earnings call transcript.
{prior_context}

EXECUTIVE SPEECH (current quarter):
{transcript_text}

Return ONLY a valid JSON object with this exact structure:
{{
  "overall_score": <int 0-100, where 100=highly confident, specific, transparent>,
  "confidence_score": <int 0-100>,
  "transparency_score": <int 0-100, higher=more open about challenges>,
  "hedging_score": <int 0-100, LOWER=more hedging (bad), HIGHER=less hedging (good)>,
  "forward_guidance_score": <int 0-100, higher=more specific numeric guidance>,
  "tone_shift_score": <int 0-100, 50=no change, >60=more positive, <40=more negative; null if no prior>,
  "dominant_tone": <"Confident" | "Cautious" | "Defensive" | "Optimistic" | "Mixed">,
  "key_signals": [<list of 2-4 specific linguistic examples found, quoted from text>],
  "summary": "<1-2 sentence description of the executive communication quality>"
}}
"""


def _extract_executive_speech(transcript: dict) -> str:
    """Extract and concatenate speech from executives only (filter out analysts/operator).

    Parameters
    ----------
    transcript : dict with ``transcript`` key (list of ``{name, speech}`` items)

    Returns
    -------
    str : concatenated executive speech, truncated to ``_MAX_TRANSCRIPT_CHARS``
    """
    items = transcript.get("transcript", [])
    if not items:
        return ""

    parts: list[str] = []
    for item in items:
        speaker = (item.get("name") or "").strip().lower()
        if not speaker:
            continue
        # Include if the role matches known executive titles
        is_exec = any(role in speaker for role in _EXECUTIVE_ROLES)
        if not is_exec:
            continue
        speeches = item.get("speech", [])
        if isinstance(speeches, list):
            text = " ".join(str(s) for s in speeches if s)
        else:
            text = str(speeches)
        if text.strip():
            parts.append(f"[{item.get('name', 'Executive')}]: {text.strip()}")

    combined = "\n\n".join(parts)
    return combined[:_MAX_TRANSCRIPT_CHARS]


def _call_claude_for_tone(
    symbol: str,
    transcript_text: str,
    prior_transcript_text: str | None = None,
) -> dict | None:
    """Call Claude AI and return parsed tone analysis dict.

    Returns None on any failure (no AI available, parse error, etc.).
    """
    try:
        from src.analysis.analyzer import _get_client, _create_text
    except ImportError:
        log.warning("executive_tone: analyzer module not available")
        return None

    prior_context = ""
    if prior_transcript_text:
        prior_context = (
            f"\nPRIOR QUARTER EXECUTIVE SPEECH (for tone shift comparison):\n"
            f"{prior_transcript_text[:2000]}\n"
        )

    prompt = _ANALYSIS_USER_PROMPT.format(
        symbol=symbol,
        prior_context=prior_context,
        transcript_text=transcript_text,
    )

    try:
        client = _get_client()
        raw = _create_text(
            client,
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
            system=_ANALYSIS_SYSTEM_PROMPT,
        )
        # Strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        result = json.loads(raw)
        return result
    except json.JSONDecodeError as exc:
        log.warning("executive_tone: failed to parse Claude JSON response: %s", exc)
        return None
    except Exception as exc:
        log.warning("executive_tone: Claude call failed: %s", exc)
        return None


def _score_from_analysis(analysis: dict) -> dict:
    """Convert raw Claude analysis dict into the standard factor dict format.

    Computes a composite 0-100 score from the sub-signals.
    """
    overall = int(analysis.get("overall_score") or 50)
    confidence = int(analysis.get("confidence_score") or 50)
    transparency = int(analysis.get("transparency_score") or 50)
    hedging = int(analysis.get("hedging_score") or 50)
    guidance = int(analysis.get("forward_guidance_score") or 50)
    tone_shift_raw = analysis.get("tone_shift_score")
    tone_shift = int(tone_shift_raw) if tone_shift_raw is not None else 50

    dominant = analysis.get("dominant_tone", "Mixed")
    summary = analysis.get("summary", "")
    key_signals = analysis.get("key_signals", [])

    # Weighted composite (overall is the primary anchor, sub-signals refine)
    composite = int(
        overall * 0.35
        + confidence * 0.20
        + transparency * 0.15
        + hedging * 0.15
        + guidance * 0.10
        + tone_shift * 0.05
    )
    composite = max(0, min(100, composite))

    # Map to label
    if composite >= 75:
        label = "Strong executive confidence"
    elif composite >= 60:
        label = "Constructive tone"
    elif composite >= 45:
        label = "Measured / neutral"
    elif composite >= 30:
        label = "Cautious language"
    else:
        label = "Defensive / evasive tone"

    signals_str = " | ".join(key_signals[:3]) if key_signals else ""
    detail = (
        f"Tone: {dominant}  |  Confidence: {confidence}  "
        f"Transparency: {transparency}  Hedging: {hedging}  Guidance: {guidance}"
    )
    if signals_str:
        detail += f"  |  Signals: {signals_str}"
    if summary:
        detail += f"\n{summary}"

    return {
        "score": composite,
        "label": label,
        "detail": detail,
        "dominant_tone": dominant,
        "sub_signals": {
            "confidence": confidence,
            "transparency": transparency,
            "hedging": hedging,
            "forward_guidance": guidance,
            "tone_shift": tone_shift,
        },
    }


def compute_executive_tone_score(symbol: str, api) -> dict | None:
    """Fetch the most recent earnings call transcript and compute a tone score.

    Parameters
    ----------
    symbol : str
        Stock ticker (e.g. "AAPL")
    api :
        FinnhubAPI (or MockFinnhubAPI) instance

    Returns
    -------
    dict with keys: score, label, detail, dominant_tone, sub_signals
    or None if no transcript data is available.
    """
    try:
        transcripts = api.get_transcripts_list(symbol)
    except Exception as exc:
        log.warning("executive_tone: failed to fetch transcript list for %s: %s", symbol, exc)
        return None

    if not transcripts:
        log.debug("executive_tone: no transcripts available for %s", symbol)
        return None

    # Use the most recent transcript; optionally the prior one for tone shift
    latest = transcripts[0]
    transcript_id = latest.get("id", "")

    # Check disk cache first
    cache_key = f"executive_tone:{transcript_id}"
    cached = _disk_cache.get(cache_key)
    if cached is not CACHE_MISS:
        log.debug("executive_tone: cache hit for %s (%s)", symbol, transcript_id)
        return cached

    try:
        current_data = api.get_transcript(transcript_id)
    except Exception as exc:
        log.warning("executive_tone: failed to fetch transcript %s: %s", transcript_id, exc)
        return None

    current_text = _extract_executive_speech(current_data)
    if not current_text:
        log.debug("executive_tone: no executive speech found in transcript for %s", symbol)
        return None

    # Prior quarter for tone shift comparison
    prior_text: str | None = None
    if len(transcripts) >= 2:
        prior_id = transcripts[1].get("id", "")
        try:
            prior_data = api.get_transcript(prior_id)
            prior_text = _extract_executive_speech(prior_data) or None
        except Exception:
            prior_text = None

    # Call Claude for linguistic analysis
    analysis = _call_claude_for_tone(symbol, current_text, prior_text)
    if analysis is None:
        log.debug("executive_tone: Claude analysis failed for %s, returning None", symbol)
        return None

    result = _score_from_analysis(analysis)

    # Cache the result
    _disk_cache.set(cache_key, result, ttl=_TONE_CACHE_TTL)
    log.info(
        "executive_tone: %s score=%d tone=%s",
        symbol,
        result["score"],
        result.get("dominant_tone", "?"),
    )
    return result

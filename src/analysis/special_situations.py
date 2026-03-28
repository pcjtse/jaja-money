"""Special Situations Alpha Scorer.

Applies situation-specific scoring models for M&A, spin-offs,
tender offers, and restructurings.

For merger arb: score = f(deal_spread_pct, deal_type_certainty)
For spin-offs:  score based on parent-subsidiary valuation discount.
"""

from __future__ import annotations

from src.core.log_setup import get_logger

log = get_logger(__name__)

# Probability weight by deal type
_DEAL_CERTAINTY = {
    "SC TO-T": 0.85,    # Tender offer — high certainty
    "SC TO-I": 0.80,
    "DEFM14A": 0.75,    # Definitive merger proxy
    "PREM14A": 0.45,    # Preliminary — lower certainty
    "8-K": 0.60,
    "10-12B": 0.70,     # Spin-off registration
    "10-12G": 0.65,
}


def score_special_situation(
    situation_data: dict,
    current_price: float | None = None,
    financials: dict | None = None,
) -> dict:
    """Compute a 0-100 factor score for a special situation.

    For standard stocks with no situation: returns neutral 50.
    For merger arb: score based on deal spread risk/reward.
    For spin-offs: score based on sum-of-parts discount.

    Parameters
    ----------
    situation_data : output of deal_tracker.get_special_situation_filings()
    current_price  : current stock price
    financials     : optional fundamental metrics

    Returns
    -------
    dict with score (int), label (str), detail (str),
         overrides_composite (bool)
    """
    if not situation_data.get("available"):
        return {
            "score": 50,
            "label": "No special situation",
            "detail": "No M&A or spin-off activity detected",
            "overrides_composite": False,
        }

    situation_type = situation_data.get("situation_type", "none")
    filings = situation_data.get("filings", [])
    description = situation_data.get("description", "")

    form_type = filings[0].get("form_type", "") if filings else ""
    certainty = _DEAL_CERTAINTY.get(form_type, 0.55)

    if situation_type == "merger":
        return _score_merger_arb(certainty, description, current_price)
    elif situation_type == "spinoff":
        return _score_spinoff(certainty, description, financials)
    elif situation_type == "tender":
        return _score_merger_arb(certainty * 1.1, description, current_price)
    else:
        return {
            "score": 60,
            "label": "Special situation detected",
            "detail": description,
            "overrides_composite": False,
        }


def _score_merger_arb(
    certainty: float,
    description: str,
    current_price: float | None,
) -> dict:
    """Score based on deal certainty and type."""
    # Without live deal price data, score by certainty level
    base = int(certainty * 100)

    # High-certainty deals near closing have limited upside but low risk
    if certainty >= 0.80:
        label = "High-certainty merger arb — tight spread"
        score = min(82, base)
    elif certainty >= 0.60:
        label = "Moderate-certainty merger — watch for break risk"
        score = min(70, base)
    else:
        label = "Early-stage deal — significant break risk"
        score = min(60, base)

    return {
        "score": score,
        "label": label,
        "detail": f"Merger situation ({description}) | Deal certainty: ~{certainty:.0%}",
        "overrides_composite": certainty >= 0.75,
    }


def _score_spinoff(
    certainty: float,
    description: str,
    financials: dict | None,
) -> dict:
    """Score spin-off based on certainty and potential sum-of-parts upside."""
    # Spin-offs historically outperform parent by 10-15% in first year
    base = 70
    if certainty >= 0.70:
        base = 78
        label = "Spin-off in progress — historical alpha opportunity"
    else:
        label = "Possible spin-off — early filing stage"

    return {
        "score": base,
        "label": label,
        "detail": f"Spin-off situation ({description}) | Certainty: ~{certainty:.0%}",
        "overrides_composite": False,
    }

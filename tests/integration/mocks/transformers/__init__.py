"""Fake transformers module for integration tests.

Returns mock FinBERT sentiment predictions without loading the real model.
"""

from __future__ import annotations


def _mock_pipeline(*args, **kwargs):
    """Return a callable that mimics a HuggingFace pipeline."""

    def _run(text: str, **kw):
        # Return fake positive sentiment
        return [
            {"label": "positive", "score": 0.75},
            {"label": "neutral", "score": 0.20},
            {"label": "negative", "score": 0.05},
        ]

    return _run


def pipeline(task: str = "", *args, **kwargs):
    """Fake pipeline factory."""
    return _mock_pipeline()

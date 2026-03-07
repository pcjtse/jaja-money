"""Pytest configuration and shared fixtures.

Mocks heavy optional dependencies (transformers, torch) so that pure-logic
functions in sentiment.py can be tested without installing the full ML stack.
The FinBERT model itself is not exercised in the unit tests — only the
pure-Python aggregation helpers are tested.
"""

import sys
import types

# ---------------------------------------------------------------------------
# Stub out `transformers` before any test module imports sentiment.py
# ---------------------------------------------------------------------------

def _make_transformers_stub():
    mod = types.ModuleType("transformers")
    mod.pipeline = lambda *a, **kw: None   # score_articles tested separately
    return mod

if "transformers" not in sys.modules:
    sys.modules["transformers"] = _make_transformers_stub()

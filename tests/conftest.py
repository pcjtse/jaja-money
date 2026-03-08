"""Updated conftest.py — stubs transformers/torch and sets env vars for tests."""
import os
import sys
import types

# ---------------------------------------------------------------------------
# Stub out `transformers` so tests run without the full ML stack
# ---------------------------------------------------------------------------

def _make_transformers_stub():
    mod = types.ModuleType("transformers")
    mod.pipeline = lambda *a, **kw: None
    return mod

if "transformers" not in sys.modules:
    sys.modules["transformers"] = _make_transformers_stub()

# ---------------------------------------------------------------------------
# Stub out `torch` (sometimes imported transitively)
# ---------------------------------------------------------------------------
if "torch" not in sys.modules:
    sys.modules["torch"] = types.ModuleType("torch")

# ---------------------------------------------------------------------------
# Stub out `yfinance` so tests run without the optional dep
# ---------------------------------------------------------------------------
if "yfinance" not in sys.modules:
    sys.modules["yfinance"] = types.ModuleType("yfinance")

# ---------------------------------------------------------------------------
# Stub out `finnhub` to avoid needing a real API key
# ---------------------------------------------------------------------------
if "finnhub" not in sys.modules:
    finnhub_mod = types.ModuleType("finnhub")
    class _FakeClient:
        def __init__(self, *a, **kw): pass
    finnhub_mod.Client = _FakeClient
    sys.modules["finnhub"] = finnhub_mod

# ---------------------------------------------------------------------------
# Stub out `streamlit` for modules that import it at the top level
# ---------------------------------------------------------------------------
if "streamlit" not in sys.modules:
    st = types.ModuleType("streamlit")
    st.cache_resource = lambda **kw: (lambda fn: fn)
    st.cache_data = lambda **kw: (lambda fn: fn)
    st.session_state = {}
    sys.modules["streamlit"] = st

# ---------------------------------------------------------------------------
# Stub out `pyyaml` / `yaml`
# ---------------------------------------------------------------------------
if "yaml" not in sys.modules:
    yaml_mod = types.ModuleType("yaml")
    yaml_mod.safe_load = lambda f: {}
    sys.modules["yaml"] = yaml_mod

# ---------------------------------------------------------------------------
# Point user home to a temp dir so history/watchlist/cache don't pollute
# ---------------------------------------------------------------------------
import tempfile
import pathlib

_tmp = tempfile.mkdtemp(prefix="jaja_test_")
os.environ.setdefault("HOME", _tmp)

# Set dummy API keys so modules don't raise on import
os.environ.setdefault("FINNHUB_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")

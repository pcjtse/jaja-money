"""Updated conftest.py — stubs transformers/torch and sets env vars for tests."""

import os
import sys
import tempfile
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
    yf_mod = types.ModuleType("yfinance")

    class _FakeTicker:
        def __init__(self, *a, **kw):
            self.info = {}
            self.news = []
            self.recommendations = None
            self.institutional_holders = None

        def history(self, *a, **kw):
            class _DF:
                empty = True

                def __getitem__(self, key):
                    return []

            return _DF()

    yf_mod.Ticker = _FakeTicker
    sys.modules["yfinance"] = yf_mod

# ---------------------------------------------------------------------------
# Stub out `finnhub` to avoid needing a real API key
# ---------------------------------------------------------------------------
if "finnhub" not in sys.modules:
    finnhub_mod = types.ModuleType("finnhub")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

    finnhub_mod.Client = _FakeClient
    sys.modules["finnhub"] = finnhub_mod

# ---------------------------------------------------------------------------
# Stub out `streamlit` for modules that import it at the top level
# ---------------------------------------------------------------------------
if "streamlit" not in sys.modules:
    st = types.ModuleType("streamlit")
    st.cache_resource = lambda **kw: lambda fn: fn
    st.cache_data = lambda **kw: lambda fn: fn
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
_tmp = tempfile.mkdtemp(prefix="jaja_test_")
os.environ.setdefault("HOME", _tmp)

# Set dummy API keys so modules don't raise on import
os.environ.setdefault("FINNHUB_API_KEY", "test_key")
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")

# ---------------------------------------------------------------------------
# Stub out `requests` if not installed in this Python env (P10.2)
# ---------------------------------------------------------------------------
if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except ImportError:
        req_mod = types.ModuleType("requests")
        req_mod.get = lambda *a, **kw: None
        req_mod.post = lambda *a, **kw: None

        class _FakeResp:
            status = 200
            text = ""

            def json(self):
                return {}

            def raise_for_status(self):
                pass

        req_mod.Response = _FakeResp
        sys.modules["requests"] = req_mod

# ---------------------------------------------------------------------------
# Stub out `redis` if not installed (P14.2)
# ---------------------------------------------------------------------------
if "redis" not in sys.modules:
    try:
        import redis  # noqa: F401
    except ImportError:
        redis_mod = types.ModuleType("redis")

        class _FakeRedis:
            @classmethod
            def from_url(cls, *a, **kw):
                return cls()

            def ping(self):
                raise ConnectionError("Redis stub")

            def get(self, key):
                return None

            def setex(self, key, ttl, val):
                pass

            def delete(self, *keys):
                return 0

            def keys(self, pattern="*"):
                return []

            def info(self, section=""):
                return {}

        redis_mod.Redis = _FakeRedis
        sys.modules["redis"] = redis_mod

# ---------------------------------------------------------------------------
# Stub out `fastapi` and related if not installed (P14.3)
# ---------------------------------------------------------------------------
try:
    import fastapi  # noqa: F401
except ImportError:
    fa_mod = types.ModuleType("fastapi")
    fa_mod.HTTPException = Exception
    fa_mod.Depends = lambda fn: None
    fa_mod.Security = lambda *a, **kw: None
    fa_mod.Request = object

    class _FakeApp:
        def get(self, *a, **kw):
            return lambda fn: fn

        def post(self, *a, **kw):
            return lambda fn: fn

        def add_middleware(self, *a, **kw):
            pass

    fa_mod.FastAPI = lambda *a, **kw: _FakeApp()
    sys.modules["fastapi"] = fa_mod
    for sub in [
        "fastapi.middleware",
        "fastapi.middleware.cors",
        "fastapi.security",
        "fastapi.security.api_key",
        "fastapi.responses",
    ]:
        sys.modules[sub] = types.ModuleType(sub)
    sys.modules["fastapi.middleware.cors"].CORSMiddleware = object
    sys.modules["fastapi.security.api_key"].APIKeyHeader = lambda **kw: None
    sys.modules["fastapi.security.api_key"].APIKeyQuery = lambda **kw: None
    sys.modules["fastapi.responses"].StreamingResponse = object
    sys.modules["fastapi.responses"].JSONResponse = object

try:
    import uvicorn  # noqa: F401
except ImportError:
    uv_mod = types.ModuleType("uvicorn")
    uv_mod.run = lambda *a, **kw: None
    sys.modules["uvicorn"] = uv_mod

try:
    import pydantic  # noqa: F401
except ImportError:
    pyd_mod = types.ModuleType("pydantic")

    class _BaseModel:
        pass

    pyd_mod.BaseModel = _BaseModel
    pyd_mod.Field = lambda *a, **kw: None
    sys.modules["pydantic"] = pyd_mod

try:
    import gspread  # noqa: F401
except ImportError:
    gs_mod = types.ModuleType("gspread")
    gs_mod.WorksheetNotFound = Exception
    gs_mod.authorize = lambda *a, **kw: None
    sys.modules["gspread"] = gs_mod

for _mod_name in ["google", "google.oauth2", "google.oauth2.service_account"]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)
try:
    from google.oauth2 import service_account as _sa  # noqa: F401
except ImportError:
    _sa_mod = types.ModuleType("google.oauth2.service_account")

    class _FakeCreds:
        @classmethod
        def from_service_account_file(cls, *a, **kw):
            return cls()

    _sa_mod.Credentials = _FakeCreds
    sys.modules["google.oauth2.service_account"] = _sa_mod

# ---------------------------------------------------------------------------
# Stub out `anthropic` if not installed in the pytest env
# ---------------------------------------------------------------------------
try:
    import anthropic  # noqa: F401
except ImportError:
    import types as _types

    _ant = _types.ModuleType("anthropic")

    class _FakeAnthropic:
        def __init__(self, *a, **kw):
            pass

        class messages:
            @staticmethod
            def create(*a, **kw):
                class _Resp:
                    content = []

                return _Resp()

    _ant.Anthropic = _FakeAnthropic
    _ant.APIError = Exception
    _ant.AuthenticationError = Exception
    sys.modules["anthropic"] = _ant

# Stub pdfplumber if not installed (P10.5)
try:
    import pdfplumber  # noqa: F401
except ImportError:
    sys.modules["pdfplumber"] = types.ModuleType("pdfplumber")

# Stub python-dotenv if not available
try:
    from dotenv import load_dotenv  # noqa: F401
except ImportError:
    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = dotenv_mod

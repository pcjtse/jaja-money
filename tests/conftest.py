"""Updated conftest.py — stubs transformers/torch and sets env vars for tests."""

import os
import sys
import tempfile
import types

# ---------------------------------------------------------------------------
# Stub out `pandas` if not installed — provides minimal Series/DataFrame
# ---------------------------------------------------------------------------
if "pandas" not in sys.modules:
    try:
        import pandas  # noqa: F401
    except ImportError:
        _pd = types.ModuleType("pandas")
        import math as _math_pd

        class _ILoc:
            def __init__(self, s):
                self._s = s

            def __getitem__(self, idx):
                return self._s[idx]

        class _Rolling:
            def __init__(self, data, window):
                self._data = data
                self._window = window

            def _apply(self, fn):
                result = []
                for i in range(len(self._data)):
                    start = max(0, i - self._window + 1)
                    ws = [x for x in self._data[start:i + 1] if x is not None and x == x]
                    if len(ws) < self._window:
                        result.append(float("nan"))
                    else:
                        result.append(fn(ws))
                return _Series(result)

            def mean(self):
                return self._apply(lambda xs: sum(xs) / len(xs))

            def std(self):
                def _s(xs):
                    n = len(xs)
                    if n < 2:
                        return 0.0
                    m = sum(xs) / n
                    return _math_pd.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
                return self._apply(_s)

        class _EWM:
            def __init__(self, data, span=None, alpha=None, min_periods=0, adjust=True):
                a = alpha if alpha is not None else (2 / (span + 1) if span else 0.1)
                result, ema = [], None
                for v in data:
                    if v is None or (isinstance(v, float) and v != v):
                        result.append(float("nan"))
                        continue
                    ema = v if ema is None else a * v + (1 - a) * ema
                    result.append(ema)
                self._result = result

            def mean(self):
                return _Series(self._result)

        class _Series(list):
            """Minimal pandas.Series stub — extends list for iteration."""

            def __init__(self, data=None, *args, **kwargs):
                super().__init__(data or [])

            def __getitem__(self, key):
                if isinstance(key, _Series):
                    return _Series([v for v, m in zip(self, key) if m])
                return super().__getitem__(key)

            @property
            def iloc(self):
                return _ILoc(self)

            def rolling(self, window=1, *a, **kw):
                return _Rolling(self, window)

            def mean(self):
                vals = [x for x in self if x is not None and x == x]
                return sum(vals) / len(vals) if vals else float("nan")

            def std(self):
                vals = [x for x in self if x is not None and x == x]
                n = len(vals)
                if n < 2:
                    return 0.0
                m = sum(vals) / n
                return _math_pd.sqrt(sum((x - m) ** 2 for x in vals) / (n - 1))

            def ewm(self, span=None, alpha=None, min_periods=0, adjust=True, **kw):
                return _EWM(self, span=span, alpha=alpha, min_periods=min_periods, adjust=adjust)

            def diff(self):
                return _Series([float("nan")] + [self[i] - self[i - 1] for i in range(1, len(self))])

            def clip(self, lower=None, upper=None):
                result = []
                for x in self:
                    if x is None or (isinstance(x, float) and x != x):
                        result.append(x)
                        continue
                    if lower is not None and x < lower:
                        x = lower
                    if upper is not None and x > upper:
                        x = upper
                    result.append(x)
                return _Series(result)

            def max(self):
                vals = [x for x in self if x is not None and x == x]
                return max(vals) if vals else float("nan")

            def min(self):
                vals = [x for x in self if x is not None and x == x]
                return min(vals) if vals else float("nan")

            def apply(self, fn):
                return _Series([fn(x) if (x is not None and x == x) else float("nan") for x in self])

            def tail(self, n):
                return _Series(self[-n:])

            def dropna(self):
                return _Series([x for x in self if x is not None and x == x])

            def tolist(self):
                return list(self)

            def shift(self, n):
                if n >= 0:
                    return _Series([float("nan")] * n + list(self[:-n] if n else list(self)))
                return _Series(list(self[-n:]) + [float("nan")] * (-n))

            def __truediv__(self, other):
                def _div(a, b):
                    if a is None or (isinstance(a, float) and a != a):
                        return float("nan")
                    if b == 0:
                        return float("inf") if a != 0 else float("nan")
                    return a / b

                if isinstance(other, _Series):
                    return _Series([_div(a, b) for a, b in zip(self, other)])
                return _Series([_div(x, other) for x in self])

            def __add__(self, other):
                if isinstance(other, _Series):
                    return _Series([a + b for a, b in zip(self, other)])
                return _Series([x + other for x in self])

            def __sub__(self, other):
                if isinstance(other, _Series):
                    return _Series([a - b for a, b in zip(self, other)])
                return _Series([x - other for x in self])

            def __mul__(self, other):
                if isinstance(other, _Series):
                    return _Series([a * b for a, b in zip(self, other)])
                return _Series([x * other for x in self])

            def __gt__(self, val):
                return _Series([bool(x > val) if (x is not None and x == x) else False for x in self])

            def __lt__(self, val):
                return _Series([bool(x < val) if (x is not None and x == x) else False for x in self])

            def __neg__(self):
                return _Series([-x if (x is not None and x == x) else float("nan") for x in self])

            def __radd__(self, other):
                return _Series([other + x for x in self])

            def __rsub__(self, other):
                return _Series([other - x for x in self])

            def __rmul__(self, other):
                return _Series([other * x for x in self])

            def __rtruediv__(self, other):
                return _Series([other / x if x else float("nan") for x in self])

        class _DataFrame:
            def __init__(self, data=None, *a, **kw):
                self._data = data or {}

            def __len__(self):
                cols = list(self._data.values())
                return len(cols[0]) if cols else 0

            def __getitem__(self, key):
                return _Series(self._data.get(key, []))

            @property
            def empty(self):
                return not bool(self._data)

            def iterrows(self):
                return iter([])

            @property
            def index(self):
                return []

            @property
            def columns(self):
                return list(self._data.keys())

            def dropna(self):
                return self

        def _date_range(start=None, end=None, periods=None, freq="D", **kw):
            from datetime import datetime, timedelta
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if periods:
                delta = timedelta(days=1) if freq in ("D", "B") else timedelta(days=7)
                return [start + delta * i for i in range(periods)]
            return []

        _pd.Series = _Series
        _pd.DataFrame = _DataFrame
        _pd.NA = None
        _pd.NaT = None
        _pd.isna = lambda x: x is None
        _pd.notna = lambda x: x is not None
        _pd.to_datetime = lambda x, **kw: x
        _pd.date_range = _date_range
        _pd.concat = lambda dfs, **kw: _DataFrame()
        _pd.read_csv = lambda *a, **kw: _DataFrame()
        sys.modules["pandas"] = _pd

# ---------------------------------------------------------------------------
# Stub out `numpy` if not installed
# ---------------------------------------------------------------------------
if "numpy" not in sys.modules:
    try:
        import numpy  # noqa: F401
    except ImportError:
        import math as _math

        class _NpArray(list):
            """Minimal numpy.ndarray stub."""

            def min(self, **kw):
                vals = [x for x in self if x is not None and x == x]
                return min(vals) if vals else float("nan")

            def max(self, **kw):
                vals = [x for x in self if x is not None and x == x]
                return max(vals) if vals else float("nan")

            def mean(self, **kw):
                vals = [x for x in self if x is not None and x == x]
                return sum(vals) / len(vals) if vals else float("nan")

            def std(self, **kw):
                vals = [x for x in self if x is not None and x == x]
                n = len(vals)
                if n < 2:
                    return 0.0
                m = sum(vals) / n
                return _math.sqrt(sum((x - m) ** 2 for x in vals) / n)

            def sum(self, **kw):
                return sum(x for x in self if x is not None and x == x)

            def __add__(self, other):
                if isinstance(other, list):
                    return _NpArray([a + b for a, b in zip(self, other)])
                return _NpArray([x + other for x in self])

            def __sub__(self, other):
                if isinstance(other, list):
                    return _NpArray([a - b for a, b in zip(self, other)])
                return _NpArray([x - other for x in self])

            def __mul__(self, other):
                if isinstance(other, list):
                    return _NpArray([a * b for a, b in zip(self, other)])
                return _NpArray([x * other for x in self])

            def __truediv__(self, other):
                if isinstance(other, list):
                    return _NpArray([a / b if b else float("nan") for a, b in zip(self, other)])
                return _NpArray([x / other if other else float("nan") for x in self])

            def __gt__(self, val):
                return _NpArray([bool(x > val) for x in self])

            def __lt__(self, val):
                return _NpArray([bool(x < val) for x in self])

            def __ge__(self, val):
                return _NpArray([bool(x >= val) for x in self])

            def __le__(self, val):
                return _NpArray([bool(x <= val) for x in self])

            def __eq__(self, val):
                if isinstance(val, list):
                    return _NpArray([a == b for a, b in zip(self, val)])
                return _NpArray([bool(x == val) for x in self])

            def __neg__(self):
                return _NpArray([-x for x in self])

            def astype(self, *a, **kw):
                return self

            def reshape(self, *shape, **kw):
                return self

            @property
            def T(self):
                return self

            @property
            def shape(self):
                return (len(self),)

        def _np_array(data, *a, **kw):
            if hasattr(data, '__iter__'):
                return _NpArray(data)
            return _NpArray([data])

        _np = types.ModuleType("numpy")
        _np.nan = float("nan")
        _np.inf = float("inf")
        _np.sqrt = _math.sqrt
        _np.log = _math.log
        _np.exp = _math.exp
        _np.pi = _math.pi
        _np.ndarray = _NpArray
        _np.array = _np_array
        _np.zeros = lambda n, **kw: [0.0] * n
        _np.ones = lambda n, **kw: [1.0] * n
        _np.mean = lambda x: sum(x) / len(x) if x else 0.0
        _np.std = lambda x, **kw: 0.0
        _np.isnan = _math.isnan
        _np.float64 = float
        _np.int64 = int
        _np.ndarray = list
        _np.isscalar = lambda x: isinstance(x, (int, float, complex, bool))
        _np.abs = abs

        def _percentile(a, q, **kw):
            data = sorted(x for x in a if x is not None and x == x)
            if not data:
                return float("nan")
            if isinstance(q, (list, tuple)):
                return [_percentile(data, qi) for qi in q]
            idx = (len(data) - 1) * q / 100.0
            lo, hi = int(idx), min(int(idx) + 1, len(data) - 1)
            frac = idx - lo
            return data[lo] + frac * (data[hi] - data[lo])

        _np.percentile = _percentile
        _np.quantile = lambda a, q, **kw: _percentile(a, q * 100 if isinstance(q, float) else [qi * 100 for qi in q])
        _np.bool_ = bool
        _np.integer = int
        _np.floating = float
        _np.arange = lambda start, stop=None, step=1, **kw: list(range(int(start) if stop is not None else 0, int(stop) if stop is not None else int(start), int(step)))
        _np.linspace = lambda start, stop, num=50, **kw: [start + (stop - start) * i / (num - 1) for i in range(num)]
        def _polyfit(x, y, deg):
            """Minimal linear regression (deg=1) via least squares."""
            if deg != 1 or len(x) < 2:
                return [0.0] * (deg + 1)
            n = len(x)
            sx = sum(x)
            sy = sum(y)
            sxy = sum(xi * yi for xi, yi in zip(x, y))
            sx2 = sum(xi * xi for xi in x)
            denom = n * sx2 - sx * sx
            if denom == 0:
                return [0.0, sy / n]
            a = (n * sxy - sx * sy) / denom
            b = (sy - a * sx) / n
            return [a, b]

        _np.polyfit = _polyfit
        _np.poly1d = lambda coeffs: (lambda x: sum(c * x ** (len(coeffs) - 1 - i) for i, c in enumerate(coeffs)))

        import random as _random_mod

        class _RNG:
            def __init__(self, seed=None):
                self._rng = _random_mod.Random(seed)

            def standard_normal(self, n=None):
                if n is None:
                    return self._rng.gauss(0, 1)
                return [self._rng.gauss(0, 1) for _ in range(n)]

            def normal(self, loc=0.0, scale=1.0, size=None):
                if size is None:
                    return self._rng.gauss(loc, scale)
                return [self._rng.gauss(loc, scale) for _ in range(size)]

            def uniform(self, low=0.0, high=1.0, size=None):
                if size is None:
                    return self._rng.uniform(low, high)
                return [self._rng.uniform(low, high) for _ in range(size)]

            def integers(self, low, high=None, size=None):
                if high is None:
                    low, high = 0, low
                if size is None:
                    return self._rng.randint(low, high - 1)
                return [self._rng.randint(low, high - 1) for _ in range(size)]

        _np_random = types.ModuleType("numpy.random")
        _np_random.default_rng = _RNG
        _np_random.seed = lambda s=None: None
        _np_random.randn = lambda *a: [_random_mod.gauss(0, 1) for _ in range(a[0] if a else 1)]
        _np_random.rand = lambda *a: [_random_mod.random() for _ in range(a[0] if a else 1)]
        _np_random.normal = lambda loc=0.0, scale=1.0, size=None: (
            [_random_mod.gauss(loc, scale) for _ in range(size if isinstance(size, int) else size[0])]
            if size is not None else _random_mod.gauss(loc, scale)
        )
        _np_random.uniform = lambda low=0.0, high=1.0, size=None: (
            [_random_mod.uniform(low, high) for _ in range(size if isinstance(size, int) else size[0])]
            if size is not None else _random_mod.uniform(low, high)
        )
        _np.random = _np_random
        sys.modules["numpy.random"] = _np_random
        sys.modules["numpy"] = _np

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
    _torch_stub = types.ModuleType("torch")
    # scipy >= 1.17 checks for torch.Tensor when torch is present in sys.modules
    _torch_stub.Tensor = type("Tensor", (), {})
    sys.modules["torch"] = _torch_stub

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

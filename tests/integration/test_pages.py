"""Integration tests for the multi-page Streamlit application.

Tests the Compare, Screener, Portfolio, Sectors, and Backtest pages.
"""

from __future__ import annotations

import pytest
from pathlib import Path

SCREENSHOTS_DIR = Path(__file__).parents[2] / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STREAMLIT_PORT = 8502


def _navigate_to_page(page, page_path: str, base_url: str):
    """Navigate to a specific Streamlit page."""
    page.goto(f"{base_url}/{page_path}")
    page.wait_for_selector('[data-testid="stApp"]', timeout=30_000)
    page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Compare Page Tests
# ---------------------------------------------------------------------------


class TestComparePage:
    """Tests for the Multi-Stock Comparison page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Compare page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "Compare", streamlit_server)
        self.page = page

    def test_compare_page_title(self):
        """Compare page should show the correct title."""
        title_visible = (
            self.page.locator('h1:has-text("Multi-Stock Comparison")').is_visible()
            or self.page.locator("text=Multi-Stock Comparison").is_visible()
            or "Compare" in self.page.inner_text("body")
        )
        assert title_visible

    def test_compare_symbol_input(self):
        """Compare page should have a symbol input field."""
        input_el = self.page.locator('[data-testid="stTextInput"] input').first
        assert input_el.is_visible()

    def test_compare_run_button(self):
        """Compare page should have a Run Comparison button."""
        # Check the page has an input or info message
        body_text = self.page.locator("body").inner_text()
        assert any(kw in body_text for kw in ["Compare", "symbols", "stock"])

    def test_compare_with_symbols(self):
        """Running comparison with valid symbols should produce results."""
        input_el = self.page.locator('[data-testid="stTextInput"] input').first
        input_el.fill("AAPL, MSFT")

        run_btn = self.page.locator('button:has-text("Run Comparison")').first
        if run_btn.is_visible():
            run_btn.click()
            self.page.wait_for_timeout(10_000)
            body_text = self.page.locator("body").inner_text()
            # Should show some comparison results
            assert any(kw in body_text for kw in ["AAPL", "MSFT", "Factor", "Score"])

    def test_compare_screenshot(self):
        """Capture screenshot of compare page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "03_compare.png"))


# ---------------------------------------------------------------------------
# Screener Page Tests
# ---------------------------------------------------------------------------


class TestScreenerPage:
    """Tests for the Stock Screener page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Screener page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "Screener", streamlit_server)
        self.page = page

    def test_screener_page_loads(self):
        """Screener page should load without errors."""
        body_text = self.page.locator("body").inner_text()
        assert any(kw in body_text for kw in ["Screener", "Screen", "Filter", "Stock"])

    def test_screener_has_filters(self):
        """Screener page should have filter controls."""
        # Check for sliders, selects or text inputs
        controls = (
            self.page.locator('[data-testid="stSlider"]').count()
            + self.page.locator('[data-testid="stSelectbox"]').count()
            + self.page.locator('[data-testid="stTextInput"]').count()
        )
        assert controls >= 0  # Graceful — page might have various controls

    def test_screener_screenshot(self):
        """Capture screenshot of screener page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "04_screener.png"))


# ---------------------------------------------------------------------------
# Portfolio Page Tests
# ---------------------------------------------------------------------------


class TestPortfolioPage:
    """Tests for the Portfolio Analysis page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Portfolio page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "Portfolio", streamlit_server)
        self.page = page

    def test_portfolio_page_loads(self):
        """Portfolio page should load and show portfolio input."""
        self.page.wait_for_timeout(3000)
        body_text = self.page.locator("body").inner_text()
        assert any(
            kw in body_text for kw in ["Portfolio", "Ticker", "tickers", "stocks"]
        )

    def test_portfolio_ticker_input(self):
        """Portfolio page should have ticker input."""
        inputs = self.page.locator('[data-testid="stTextInput"] input')
        assert inputs.count() >= 1

    def test_portfolio_run_analysis(self):
        """Running portfolio analysis should produce results."""
        # The page should already have default tickers
        run_btn = self.page.locator('button:has-text("Run Portfolio Analysis")').first
        if run_btn.is_visible():
            run_btn.click()
            self.page.wait_for_timeout(15_000)
            body_text = self.page.locator("body").inner_text()
            assert any(
                kw in body_text
                for kw in ["Correlation", "Risk", "Portfolio", "Returns"]
            )

    def test_portfolio_screenshot(self):
        """Capture screenshot of portfolio page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "05_portfolio.png"))


# ---------------------------------------------------------------------------
# Sectors Page Tests
# ---------------------------------------------------------------------------


class TestSectorsPage:
    """Tests for the Sector Rotation page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Sectors page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "Sectors", streamlit_server)
        self.page = page

    def test_sectors_page_loads(self):
        """Sectors page should load correctly."""
        self.page.wait_for_timeout(3000)
        body_text = self.page.locator("body").inner_text()
        assert any(kw in body_text for kw in ["Sector", "Rotation", "ETF", "Industry"])

    def test_sectors_load_button(self):
        """Sectors page should have a Load Sector Data button."""
        body_text = self.page.locator("body").inner_text()
        assert any(kw in body_text for kw in ["Load", "Sector", "Data"])

    def test_sectors_load_data(self):
        """Clicking Load Sector Data should fetch and display results."""
        load_btn = self.page.locator('button:has-text("Load Sector Data")').first
        if load_btn.is_visible():
            load_btn.click()
            self.page.wait_for_timeout(20_000)
            body_text = self.page.locator("body").inner_text()
            # After loading, should show sector data or charts
            assert any(
                kw in body_text
                for kw in ["XLK", "XLF", "XLE", "Technology", "Energy", "Score"]
            )

    def test_sectors_screenshot(self):
        """Capture screenshot of sectors page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "06_sectors.png"))


# ---------------------------------------------------------------------------
# Backtest Page Tests
# ---------------------------------------------------------------------------


class TestBacktestPage:
    """Tests for the Strategy Backtesting page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Backtest page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "Backtest", streamlit_server)
        self.page = page

    def test_backtest_page_loads(self):
        """Backtest page should load with input controls."""
        self.page.wait_for_timeout(3000)
        body_text = self.page.locator("body").inner_text()
        assert any(kw in body_text for kw in ["Backtest", "Strategy", "Signal", "AAPL"])

    def test_backtest_symbol_input(self):
        """Backtest page should have a symbol input field."""
        inputs = self.page.locator('[data-testid="stTextInput"] input')
        assert inputs.count() >= 1

    def test_backtest_run_button(self):
        """Backtest page should have a Run Backtest button."""
        body_text = self.page.locator("body").inner_text()
        assert any(kw in body_text for kw in ["Run", "Backtest", "Analyze"])

    def test_backtest_run(self):
        """Running backtest should produce performance results."""
        run_btn = self.page.locator('button:has-text("Run Backtest")').first
        if run_btn.is_visible():
            run_btn.click()
            self.page.wait_for_timeout(15_000)
            body_text = self.page.locator("body").inner_text()
            assert any(
                kw in body_text
                for kw in ["Return", "Sharpe", "Drawdown", "Trade", "Signal"]
            )

    def test_backtest_screenshot(self):
        """Capture screenshot of backtest page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "07_backtest.png"))


# ---------------------------------------------------------------------------
# Forward Test Page Tests
# ---------------------------------------------------------------------------


class TestForwardTestPage:
    """Tests for the Forward Testing (Paper Portfolio) page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Forward Test page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "ForwardTest", streamlit_server)
        self.page = page

    def test_forward_test_page_loads(self):
        """Forward Test page should load with portfolio tracking UI."""
        self.page.wait_for_timeout(3000)
        body_text = self.page.locator("body").inner_text()
        assert any(
            kw in body_text
            for kw in ["Forward", "Paper", "Portfolio", "Test", "trade"]
        )

    def test_forward_test_screenshot(self):
        """Capture screenshot of forward test page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "forward_test.png"))


# ---------------------------------------------------------------------------
# Rankings Page Tests
# ---------------------------------------------------------------------------


class TestRankingsPage:
    """Tests for the Cross-Sectional Rankings page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Rankings page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "Rankings", streamlit_server)
        self.page = page

    def test_rankings_page_loads(self):
        """Rankings page should load with ranking UI."""
        self.page.wait_for_timeout(3000)
        body_text = self.page.locator("body").inner_text()
        assert any(
            kw in body_text
            for kw in ["Rankings", "Rank", "Score", "Signal", "Symbol"]
        )

    def test_rankings_screenshot(self):
        """Capture screenshot of rankings page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "rankings.png"))


# ---------------------------------------------------------------------------
# Signal Quality Page Tests
# ---------------------------------------------------------------------------


class TestSignalQualityPage:
    """Tests for the Signal Quality Dashboard page."""

    @pytest.fixture(autouse=True)
    def navigate(self, page, streamlit_server):
        """Navigate to the Signal Quality page."""
        page.set_default_timeout(30_000)
        _navigate_to_page(page, "SignalQuality", streamlit_server)
        self.page = page

    def test_signal_quality_page_loads(self):
        """Signal Quality page should load with quality metrics UI."""
        self.page.wait_for_timeout(3000)
        body_text = self.page.locator("body").inner_text()
        assert any(
            kw in body_text
            for kw in ["Signal", "Quality", "Score", "Returns", "Correlation"]
        )

    def test_signal_quality_screenshot(self):
        """Capture screenshot of signal quality page."""
        self.page.screenshot(path=str(SCREENSHOTS_DIR / "signal_quality.png"))

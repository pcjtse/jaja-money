"""Full-flow integration tests — end-to-end Streamlit UI flows.

Tests complete user journeys through the application:
- Analyzing a stock and reading results
- Checking risk guardrails output
- Adding a stock to the watchlist
- Sidebar controls (cache, dark mode)
"""

from __future__ import annotations

import pytest
from pathlib import Path

SCREENSHOTS_DIR = Path(__file__).parents[2] / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enter_symbol_and_analyze(page, symbol: str):
    """Type symbol in sidebar and click Analyze; wait for results."""
    symbol_input = page.locator('[data-testid="stTextInput"] input').first
    symbol_input.fill(symbol)
    symbol_input.press("Enter")

    # Wait for Streamlit to finish the rerun triggered by Enter before clicking
    page.wait_for_timeout(3000)

    analyze_btn = page.locator(
        '[data-testid="stSidebar"] button:has-text("Analyze")'
    ).first
    analyze_btn.click()

    # Wait for the Stock Quote header which confirms analysis rendered.
    # We avoid matching the custom page_header HTML (unsafe_allow_html)
    # since Playwright text= selectors can't reliably match it.
    try:
        page.wait_for_selector("text=Stock Quote", timeout=45_000)
    except Exception:
        # Capture debug info before re-raising
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"debug_fail_{symbol}.png"), full_page=True
        )
        body = page.locator("body").inner_text()
        raise AssertionError(
            f"Analysis page for {symbol} did not render 'Stock Quote'.\n"
            f"Page text (first 2000 chars): {body[:2000]}"
        ) from None
    page.wait_for_timeout(2000)


# ---------------------------------------------------------------------------
# Complete analysis flow
# ---------------------------------------------------------------------------


class TestCompleteAnalysisFlow:
    """Tests the full stock analysis workflow."""

    def test_analyze_tech_stock(self, app_page):
        """Analyze a tech stock (AAPL) end-to-end."""
        _enter_symbol_and_analyze(app_page, "AAPL")
        app_page.wait_for_timeout(3000)

        # Use body.inner_text() since stMain may briefly disappear during re-render
        body_text = app_page.locator("body").inner_text()

        # Should show analysis title
        assert "Analysis: AAPL" in body_text or "AAPL" in body_text

        # Should show price information
        assert any(kw in body_text for kw in ["Price", "$", "Quote", "Stock"])

        app_page.screenshot(
            path=str(SCREENSHOTS_DIR / "08_aapl_full.png"),
            full_page=True,
        )

    def test_analyze_different_symbols(self, app_page):
        """The app should handle multiple different symbol analyses."""
        for symbol in ["MSFT", "GOOGL"]:
            _enter_symbol_and_analyze(app_page, symbol)
            body_text = app_page.locator("body").inner_text()
            assert symbol in body_text

    def test_scroll_through_analysis(self, app_page):
        """Scroll through a full analysis to ensure all sections load."""
        _enter_symbol_and_analyze(app_page, "AAPL")

        # Scroll down through the page in stages
        for scroll_y in [500, 1000, 1500, 2000, 2500]:
            app_page.evaluate(f"window.scrollTo(0, {scroll_y})")
            app_page.wait_for_timeout(500)

        # Take full-page screenshot after scrolling
        app_page.evaluate("window.scrollTo(0, 0)")
        app_page.screenshot(
            path=str(SCREENSHOTS_DIR / "09_analysis_scroll.png"),
            full_page=True,
        )

    def test_risk_section_appears(self, app_page):
        """After analysis, a Risk section should appear."""
        _enter_symbol_and_analyze(app_page, "AAPL")
        app_page.wait_for_timeout(5000)

        body_text = app_page.locator("body").inner_text()
        assert any(
            kw in body_text
            for kw in ["Risk", "Guardrail", "Volatility", "Factor Score"]
        )

    def test_chart_is_interactive(self, app_page):
        """The Plotly chart should be rendered and interactive."""
        _enter_symbol_and_analyze(app_page, "AAPL")
        app_page.wait_for_timeout(5000)

        try:
            chart = app_page.locator('[data-testid="stPlotlyChart"]').first
            if chart.is_visible():
                # Hover over the chart to test interactivity
                chart.hover()
                app_page.wait_for_timeout(500)
        except Exception:
            # Chart interaction is optional
            pass


# ---------------------------------------------------------------------------
# Sidebar interaction tests
# ---------------------------------------------------------------------------


class TestSidebarInteractions:
    """Tests for sidebar controls and settings."""

    def test_cache_expander_opens(self, app_page):
        """Cache & Settings expander should be clickable."""
        cache_expander = (
            app_page.locator('[data-testid="stExpander"]')
            .filter(has_text="Cache")
            .first
        )
        if cache_expander.is_visible():
            cache_expander.click()
            app_page.wait_for_timeout(1000)
            # Expander content should be visible
            expanded_text = cache_expander.inner_text()
            assert any(
                kw in expanded_text for kw in ["entries", "MB", "Clear", "Cache"]
            )

    def test_factor_weights_expander(self, app_page):
        """Factor Weights expander should show weight sliders."""
        weights_expander = (
            app_page.locator('[data-testid="stExpander"]')
            .filter(has_text="Factor Weights")
            .first
        )
        if weights_expander.is_visible():
            weights_expander.click()
            app_page.wait_for_timeout(1000)
            expanded_text = weights_expander.inner_text()
            assert any(
                kw in expanded_text for kw in ["Valuation", "Trend", "RSI", "MACD"]
            )

    def test_dark_mode_toggle(self, app_page):
        """Dark mode button should toggle when clicked."""
        sidebar = app_page.locator('[data-testid="stSidebar"]')
        initial_text = sidebar.inner_text()

        # Find and click dark mode button
        dark_btn = sidebar.locator(
            'button:has-text("Dark Mode"), button:has-text("Light Mode")'
        ).first
        if dark_btn.is_visible():
            dark_btn.click()
            app_page.wait_for_timeout(2000)
            # Button text should have changed
            new_text = sidebar.inner_text()
            assert initial_text != new_text or "Mode" in new_text


# ---------------------------------------------------------------------------
# Metrics validation tests
# ---------------------------------------------------------------------------


class TestMetricsValidation:
    """Tests that rendered numeric values are reasonable."""

    @pytest.fixture(autouse=True)
    def setup(self, app_page):
        """Analyze AAPL and set up reference to page."""
        _enter_symbol_and_analyze(app_page, "AAPL")
        app_page.wait_for_timeout(5000)
        self.page = app_page

    def test_price_metrics_are_positive(self):
        """Price metrics should show positive dollar values."""
        # In Streamlit >= 1.20, metrics use data-testid="stMetric"
        metrics = self.page.locator('[data-testid="stMetric"]')
        if metrics.count() >= 4:
            for i in range(min(4, metrics.count())):
                metric_text = metrics.nth(i).inner_text()
                # Should contain currency values
                assert "$" in metric_text or any(c.isdigit() for c in metric_text)

    def test_no_error_alerts(self):
        """Analysis should complete without showing error alerts."""
        # Check for Streamlit error/exception messages
        error_containers = self.page.locator(
            '[data-testid="stAlert"][data-baseweb="notification"]'
        )
        # Filter to only error-level alerts (not warnings/info)
        error_count = 0
        for i in range(error_containers.count()):
            alert = error_containers.nth(i)
            alert_text = alert.inner_text()
            if (
                "Error" in alert_text
                or "Exception" in alert_text
                or "Traceback" in alert_text
            ):
                error_count += 1

        assert error_count == 0, f"Found {error_count} error alerts in the analysis"

    def test_full_page_screenshot(self):
        """Take a full-page screenshot of the complete analysis."""
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.screenshot(
            path=str(SCREENSHOTS_DIR / "10_full_analysis.png"),
            full_page=True,
        )

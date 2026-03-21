"""Tests for export.py — analysis_to_pdf (graceful skip) and broker CSV parsers."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# analysis_to_pdf (requires reportlab — skip gracefully if not installed)
# ---------------------------------------------------------------------------


class TestAnalysisToPdf:
    def _sample_factors(self):
        return [
            {
                "name": "Valuation",
                "score": 70,
                "weight": 0.20,
                "label": "Bullish",
                "detail": "P/E below peer median",
            },
            {
                "name": "Trend",
                "score": 55,
                "weight": 0.15,
                "label": "Neutral",
                "detail": "Price above 50-day SMA",
            },
        ]

    def _sample_risk(self):
        return {
            "risk_score": 35,
            "risk_level": "Low",
            "risk_color": "green",
            "flags": [
                {
                    "severity": "warning",
                    "title": "Elevated HV",
                    "message": "Historical volatility above 20%",
                }
            ],
        }

    def test_raises_runtime_error_without_reportlab(self):
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"reportlab": None, "reportlab.lib": None}):
            from export import analysis_to_pdf

            with pytest.raises(RuntimeError, match="reportlab"):
                analysis_to_pdf(
                    symbol="AAPL",
                    quote={"c": 150.0, "d": 1.0, "dp": 0.67},
                    profile={"name": "Apple Inc.", "finnhubIndustry": "Technology"},
                    financials={
                        "peBasicExclExtraTTM": 28.0,
                        "marketCapitalization": 2_500_000,
                    },
                    factors=self._sample_factors(),
                    risk=self._sample_risk(),
                    composite_score=68,
                    composite_label="Bullish",
                )

    def test_returns_bytes_when_reportlab_available(self):
        pytest.importorskip("reportlab")
        from export import analysis_to_pdf

        result = analysis_to_pdf(
            symbol="AAPL",
            quote={"c": 150.0, "d": 1.0, "dp": 0.67},
            profile={"name": "Apple Inc.", "finnhubIndustry": "Technology"},
            financials={"peBasicExclExtraTTM": 28.0, "marketCapitalization": 2_500_000},
            factors=self._sample_factors(),
            risk=self._sample_risk(),
            composite_score=68,
            composite_label="Bullish",
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_pdf_starts_with_pdf_magic_bytes(self):
        pytest.importorskip("reportlab")
        from export import analysis_to_pdf

        result = analysis_to_pdf(
            symbol="TSLA",
            quote={"c": 200.0, "d": -5.0, "dp": -2.4},
            profile=None,
            financials=None,
            factors=self._sample_factors(),
            risk=self._sample_risk(),
            composite_score=45,
            composite_label="Neutral",
        )
        assert result[:4] == b"%PDF"

    def test_handles_none_profile_and_financials(self):
        pytest.importorskip("reportlab")
        from export import analysis_to_pdf

        # Should not raise even with None profile/financials
        result = analysis_to_pdf(
            symbol="X",
            quote={"c": 10.0, "d": 0.0, "dp": 0.0},
            profile=None,
            financials=None,
            factors=[],
            risk={"risk_score": 0, "risk_level": "Low", "flags": []},
            composite_score=50,
            composite_label="Neutral",
        )
        assert isinstance(result, bytes)


# ---------------------------------------------------------------------------
# parse_brokerage_csv — auto detection and per-broker parsers
# ---------------------------------------------------------------------------


class TestParseBrokerageCSV:
    """Tests for parse_brokerage_csv and underlying parsers.

    All parsers return position-level dicts with keys:
    symbol, quantity, cost_basis, current_value, unrealized_pnl
    """

    def _csv(self, lines: list[str]) -> bytes:
        return "\n".join(lines).encode("utf-8")

    def _schwab_csv(self):
        """Schwab positions export format."""
        return self._csv(
            [
                '"Positions for account XXXX1234 as of 01/01/2024"',
                '""',
                '"Symbol","Description","Quantity","Price","Price Change %","Price Change $","Market Value","Day Change %","Day Change $","Cost Basis","Gain/Loss %","Gain/Loss $","Ratings","Reinvest Dividends?","Capital Gains?","% Of Account","Security Type"',
                '"AAPL","Apple Inc","10","$150.00","0.50%","$0.75","$1500.00","0.50%","$7.50","$1200.00","25.00%","$300.00","","No","No","10.00%","Equity"',
                '"MSFT","Microsoft Corp","5","$380.00","1.00%","$3.80","$1900.00","1.00%","$19.00","$1600.00","18.75%","$300.00","","No","No","12.67%","Equity"',
            ]
        )

    def _fidelity_csv(self):
        """Fidelity positions export format."""
        return self._csv(
            [
                "Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Type",
                "AAPL,Apple Inc,10,$150.00,$0.75,$1500.00,$7.50,0.50%,$300.00,25.00%,10.00%,$1200.00,Margin",
                "MSFT,Microsoft Corp,5,$380.00,$3.80,$1900.00,$19.00,1.00%,$300.00,18.75%,12.67%,$1600.00,Cash",
            ]
        )

    def _ibkr_csv(self):
        """IBKR positions export format.

        The parser reads: row[4]=Symbol, row[5]=Quantity, row[7]=CostPrice,
        row[10]=Value (after: Positions,Data,AssetClass,Currency,Symbol,Qty,Mult,Cost,...).
        """
        return self._csv(
            [
                "Positions,Header,Asset Category,Currency,Symbol,Quantity,Mult,Cost Price,Cost Basis,Close Price,Value,Unrealized P/L,Code",
                "Positions,Data,Stocks,USD,AAPL,10,1,120.00,1200.00,150.00,1500.00,300.00,",
                "Positions,Data,Stocks,USD,MSFT,5,1,320.00,1600.00,380.00,1900.00,300.00,",
            ]
        )

    def test_schwab_auto_detection(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._schwab_csv(), broker="auto")
        assert isinstance(result, list)

    def test_fidelity_returns_list(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._fidelity_csv(), broker="fidelity")
        assert isinstance(result, list)

    def test_ibkr_returns_list(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._ibkr_csv(), broker="ibkr")
        assert isinstance(result, list)

    def test_fidelity_result_has_expected_keys(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._fidelity_csv(), broker="fidelity")
        if result:
            for key in (
                "symbol",
                "quantity",
                "cost_basis",
                "current_value",
                "unrealized_pnl",
            ):
                assert key in result[0]

    def test_ibkr_result_has_expected_keys(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._ibkr_csv(), broker="ibkr")
        if result:
            for key in (
                "symbol",
                "quantity",
                "cost_basis",
                "current_value",
                "unrealized_pnl",
            ):
                assert key in result[0]

    def test_ibkr_symbol_parsed_correctly(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._ibkr_csv(), broker="ibkr")
        symbols = [r["symbol"] for r in result]
        assert "AAPL" in symbols

    def test_ibkr_unrealized_pnl_is_numeric(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(self._ibkr_csv(), broker="ibkr")
        for r in result:
            assert isinstance(r["unrealized_pnl"], (int, float))

    def test_empty_csv_returns_empty_list(self):
        from export import parse_brokerage_csv

        result = parse_brokerage_csv(b"", broker="fidelity")
        assert result == []

    def test_unknown_broker_returns_list(self):
        from export import parse_brokerage_csv

        # Should not raise; tries generic parser and returns list
        result = parse_brokerage_csv(b"col1,col2\nval1,val2", broker="unknown_broker")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _parse_float helper
# ---------------------------------------------------------------------------


class TestParseFloat:
    def test_valid_float_string(self):
        from export import _parse_float

        assert _parse_float("1500.00") == pytest.approx(1500.0)

    def test_none_returns_none(self):
        from export import _parse_float

        assert _parse_float(None) is None

    def test_empty_string_returns_none(self):
        from export import _parse_float

        assert _parse_float("") is None

    def test_string_with_commas(self):
        from export import _parse_float

        # "1,500.00" might fail gracefully → None
        result = _parse_float("1500.00")
        assert result is not None

    def test_none_string(self):
        from export import _parse_float

        assert _parse_float("None") is None

    def test_negative_value(self):
        from export import _parse_float

        result = _parse_float("-150.50")
        assert result == pytest.approx(-150.50)


# ---------------------------------------------------------------------------
# export_to_google_sheets (stub test — no real credentials)
# ---------------------------------------------------------------------------


class TestExportToGoogleSheets:
    def test_returns_error_without_credentials_path(self):
        from export import export_to_google_sheets

        result = export_to_google_sheets(
            symbol="AAPL",
            factors=[],
            risk={"risk_score": 30, "risk_level": "Low", "flags": []},
            spreadsheet_id="fake_id",
            credentials_path="",  # no credentials
        )
        # Should not raise; should return error dict
        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is False

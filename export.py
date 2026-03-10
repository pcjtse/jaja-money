"""Export utilities — CSV download and printable HTML report.

Provides helper functions that return bytes suitable for st.download_button.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any


def factors_to_csv(symbol: str, factors: list[dict], risk: dict,
                   quote: dict, financials: dict | None = None) -> bytes:
    """Serialize factor scores and risk data to CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header block
    writer.writerow(["jaja-money Analysis Export"])
    writer.writerow(["Symbol", symbol])
    writer.writerow(["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")])
    writer.writerow([])

    # Quote
    writer.writerow(["== Quote =="])
    writer.writerow(["Price", "Day Change", "Day Change %", "Day High", "Day Low", "Prev Close"])
    writer.writerow([
        quote.get("c", ""), quote.get("d", ""), quote.get("dp", ""),
        quote.get("h", ""), quote.get("l", ""), quote.get("pc", ""),
    ])
    writer.writerow([])

    # Financials
    if financials:
        writer.writerow(["== Key Financials =="])
        writer.writerow(["P/E (TTM)", "EPS (TTM)", "Market Cap (M)", "Div Yield %",
                         "52W High", "52W Low"])
        writer.writerow([
            financials.get("peBasicExclExtraTTM", ""),
            financials.get("epsBasicExclExtraItemsTTM", ""),
            financials.get("marketCapitalization", ""),
            financials.get("dividendYieldIndicatedAnnual", ""),
            financials.get("52WeekHigh", ""),
            financials.get("52WeekLow", ""),
        ])
        writer.writerow([])

    # Factor scores
    writer.writerow(["== Factor Score Engine =="])
    writer.writerow(["Factor", "Score", "Weight", "Label", "Detail"])
    for f in factors:
        writer.writerow([
            f.get("name", ""), f.get("score", ""),
            f"{f.get('weight', 0):.0%}", f.get("label", ""), f.get("detail", ""),
        ])
    writer.writerow([])

    # Risk
    writer.writerow(["== Risk Guardrails =="])
    writer.writerow(["Risk Score", "Risk Level", "Volatility (20d %)", "Drawdown from 52W High %"])
    writer.writerow([
        risk.get("risk_score", ""), risk.get("risk_level", ""),
        f"{risk.get('hv', ''):.1f}" if risk.get("hv") is not None else "",
        f"{risk.get('drawdown_pct', ''):.1f}" if risk.get("drawdown_pct") is not None else "",
    ])
    writer.writerow([])

    # Flags
    writer.writerow(["== Active Risk Flags =="])
    writer.writerow(["Severity", "Title", "Message"])
    for flag in risk.get("flags", []):
        writer.writerow([flag.get("severity", ""), flag.get("title", ""), flag.get("message", "")])

    return buf.getvalue().encode("utf-8")


def price_history_to_csv(symbol: str, df: Any) -> bytes:
    """Export price DataFrame to CSV bytes."""
    buf = io.StringIO()
    buf.write(f"# {symbol} Price History — exported {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n")
    df.to_csv(buf)
    return buf.getvalue().encode("utf-8")


def analysis_to_html(
    symbol: str,
    quote: dict,
    profile: dict | None,
    financials: dict | None,
    factors: list[dict],
    risk: dict,
    composite_score: int,
    composite_label: str,
) -> bytes:
    """Generate a printable HTML report."""
    price = quote.get("c", 0)
    change = quote.get("d", 0)
    change_pct = quote.get("dp", 0)
    name = (profile or {}).get("name", symbol)
    sector = (profile or {}).get("finnhubIndustry", "N/A")
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    rows = ""
    for f in factors:
        score = f["score"]
        bar_color = "#2da44e" if score >= 60 else "#f0b429" if score >= 40 else "#e05252"
        rows += f"""
        <tr>
          <td>{f['name']}</td>
          <td style="width:120px">
            <div style="background:#eee;border-radius:3px;height:14px">
              <div style="width:{score}%;background:{bar_color};height:14px;border-radius:3px"></div>
            </div>
          </td>
          <td><b>{score}/100</b></td>
          <td>{f.get('weight',0):.0%}</td>
          <td>{f['label']}</td>
          <td style="font-size:0.85em;color:#666">{f['detail']}</td>
        </tr>"""

    flag_rows = ""
    for flag in risk.get("flags", []):
        sev = flag["severity"]
        bg = {"danger": "#fde8e8", "warning": "#fef3cd", "info": "#d1ecf1"}.get(sev, "#fff")
        flag_rows += f"""<tr style="background:{bg}">
          <td>{flag['icon']} {flag['title']}</td>
          <td>{flag['message']}</td></tr>"""

    signal_color = "#1a7f37" if composite_score >= 70 else \
                   "#2da44e" if composite_score >= 55 else \
                   "#888" if composite_score >= 45 else \
                   "#e05252" if composite_score >= 30 else "#cf2929"

    risk_score = risk.get("risk_score", 0)
    risk_level = risk.get("risk_level", "N/A")
    risk_color = risk.get("risk_color", "#888")

    pe = (financials or {}).get("peBasicExclExtraTTM")
    mc = (financials or {}).get("marketCapitalization")
    mc_str = f"${float(mc)/1000:.1f}B" if mc and float(mc) < 1_000_000 else \
             f"${float(mc)/1_000_000:.2f}T" if mc else "N/A"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{symbol} — jaja-money Analysis</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         margin: 0; padding: 24px; color: #222; background: #fff; }}
  h1 {{ color: #1a1a2e; margin-bottom: 4px; }}
  h2 {{ color: #444; border-bottom: 2px solid #e0e0e0; padding-bottom: 6px; margin-top: 32px; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 24px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin: 16px 0; }}
  .kpi {{ background: #f8f9fa; border-radius: 8px; padding: 12px 16px; border-left: 4px solid #2da44e; }}
  .kpi .val {{ font-size: 1.6rem; font-weight: 700; }}
  .kpi .lbl {{ color: #666; font-size: 0.8em; text-transform: uppercase; letter-spacing: 0.05em; }}
  .composite {{ display: inline-block; font-size: 2rem; font-weight: 800;
                color: {signal_color}; margin-right: 16px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th {{ background: #f0f2f4; text-align: left; padding: 8px 12px; font-size: 0.85em; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; font-size: 0.9em; }}
  @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
<h1>{name} ({symbol})</h1>
<div class="meta">Sector: {sector} &nbsp;|&nbsp; Generated: {generated}</div>

<h2>Quote</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="lbl">Price</div><div class="val">${price:,.2f}</div></div>
  <div class="kpi"><div class="lbl">Day Change</div>
    <div class="val" style="color:{'#2da44e' if change >= 0 else '#e05252'}">{change:+.2f} ({change_pct:+.2f}%)</div></div>
  <div class="kpi"><div class="lbl">P/E Ratio</div>
    <div class="val">{f"{pe:.1f}x" if pe else "N/A"}</div></div>
  <div class="kpi"><div class="lbl">Market Cap</div><div class="val">{mc_str}</div></div>
</div>

<h2>Factor Score Engine</h2>
<div>
  <span class="composite">{composite_score}/100</span>
  <span style="font-size:1.2rem;font-weight:600;color:{signal_color}">{composite_label}</span>
</div>
<table>
  <tr><th>Factor</th><th colspan="2">Score</th><th>Weight</th><th>Label</th><th>Detail</th></tr>
  {rows}
</table>

<h2>Risk Guardrails</h2>
<div style="font-size:1.2rem;font-weight:600;color:{risk_color};margin-bottom:12px">
  Risk Score: {risk_score}/100 — {risk_level}
</div>
{"<table><tr><th>Flag</th><th>Message</th></tr>" + flag_rows + "</table>"
 if flag_rows else "<p style='color:#2da44e'>No active risk flags.</p>"}

</body>
</html>"""
    return html.encode("utf-8")


def analysis_to_pdf(
    symbol: str,
    quote: dict,
    profile: dict | None,
    financials: dict | None,
    factors: list[dict],
    risk: dict,
    composite_score: int,
    composite_label: str,
    chart_image_bytes: bytes | None = None,
) -> bytes:
    """Generate a PDF analysis report using reportlab.

    Raises RuntimeError if reportlab is not installed.
    chart_image_bytes: optional PNG bytes of the price chart (requires kaleido).
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, Image as RLImage,
        )
    except ImportError:
        raise RuntimeError(
            "reportlab is required for PDF export. "
            "Install it with: pip install reportlab"
        )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "JajaTitle", parent=styles["Title"], fontSize=20, spaceAfter=4,
    )
    h2_style = ParagraphStyle(
        "JajaH2", parent=styles["Heading2"], fontSize=12,
        spaceBefore=12, spaceAfter=4,
    )
    small_style = ParagraphStyle(
        "JajaSmall", parent=styles["Normal"], fontSize=8,
        textColor=colors.grey,
    )
    body_style = ParagraphStyle("JajaBody", parent=styles["Normal"], fontSize=9)

    price = quote.get("c", 0)
    change = quote.get("d", 0)
    change_pct = quote.get("dp", 0)
    name = (profile or {}).get("name", symbol)
    sector = (profile or {}).get("finnhubIndustry", "N/A")
    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    pe = (financials or {}).get("peBasicExclExtraTTM")
    mc = (financials or {}).get("marketCapitalization")
    if mc:
        mc_f = float(mc)
        mc_str = (
            f"${mc_f / 1_000_000:.2f}T" if mc_f >= 1_000_000 else
            f"${mc_f / 1_000:.1f}B" if mc_f >= 1_000 else
            f"${mc_f:.0f}M"
        )
    else:
        mc_str = "N/A"

    story = []

    story.append(Paragraph(f"{name} ({symbol})", title_style))
    story.append(Paragraph(f"Sector: {sector}  |  Generated: {generated}", small_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("Quote", h2_style))
    _row_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])
    qt_data = [
        ["Metric", "Value"],
        ["Price", f"${price:,.2f}"],
        ["Day Change", f"{change:+.2f} ({change_pct:+.2f}%)"],
        ["P/E Ratio", f"{pe:.1f}x" if pe else "N/A"],
        ["Market Cap", mc_str],
    ]
    qt = Table(qt_data, colWidths=[7 * cm, 9 * cm])
    qt.setStyle(_row_style)
    story.append(qt)
    story.append(Spacer(1, 0.4 * cm))

    if chart_image_bytes:
        story.append(Paragraph("Price Chart", h2_style))
        img_buf = io.BytesIO(chart_image_bytes)
        img = RLImage(img_buf, width=15 * cm, height=7.5 * cm)
        story.append(img)
        story.append(Spacer(1, 0.4 * cm))

    composite_txt = f"{composite_score}/100 — {composite_label}"
    story.append(Paragraph(f"Factor Score Engine  ({composite_txt})", h2_style))
    factor_data = [["Factor", "Score", "Wt", "Label", "Detail"]]
    for f in factors:
        detail = f.get("detail") or ""
        factor_data.append([
            f.get("name", ""),
            str(f.get("score", "")),
            f"{f.get('weight', 0):.0%}",
            f.get("label", ""),
            detail[:55] + ("…" if len(detail) > 55 else ""),
        ])
    ft = Table(factor_data, colWidths=[4.5 * cm, 1.5 * cm, 1.5 * cm, 3.5 * cm, 5.5 * cm])
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f4f8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(ft)
    story.append(Spacer(1, 0.4 * cm))

    risk_score = risk.get("risk_score", 0)
    risk_level = risk.get("risk_level", "N/A")
    story.append(Paragraph(f"Risk Guardrails  ({risk_score}/100 — {risk_level})", h2_style))
    flags = risk.get("flags", [])
    if flags:
        flag_data = [["Severity", "Title", "Message"]]
        for flag in flags:
            msg = flag.get("message") or ""
            flag_data.append([
                flag.get("severity", "").upper(),
                flag.get("title", ""),
                msg[:80] + ("…" if len(msg) > 80 else ""),
            ])
        flt = Table(flag_data, colWidths=[2.5 * cm, 5 * cm, 8.5 * cm])
        flt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f4f8")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(flt)
    else:
        story.append(Paragraph("No active risk flags.", body_style))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# P12.2: Google Sheets Export & Sync
# ---------------------------------------------------------------------------


def export_to_google_sheets(
    symbol: str,
    factors: list[dict],
    risk: dict,
    financials: dict | None = None,
    spreadsheet_id: str = "",
    sheet_name: str = "jaja-money",
    credentials_path: str = "",
    append_log: bool = True,
) -> dict:
    """Export analysis results to a Google Sheet.

    Requires `gspread` and a Google service account credentials JSON file.

    Parameters
    ----------
    symbol : stock ticker
    factors : list of factor dicts (name, score, label, etc.)
    risk : risk analysis dict (risk_score, risk_level, flags)
    financials : optional dict of financial metrics
    spreadsheet_id : Google Sheet ID (from URL)
    sheet_name : worksheet name to write to
    credentials_path : path to service account JSON credentials file
    append_log : if True, append a new row instead of overwriting

    Returns dict with success, url, and error message if any.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        return {
            "success": False,
            "error": "gspread not installed. Run: pip install gspread google-auth",
        }

    if not credentials_path or not spreadsheet_id:
        return {
            "success": False,
            "error": "Google Sheets requires credentials_path and spreadsheet_id in config.",
        }

    try:
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(spreadsheet_id)

        try:
            ws = sh.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)

        # Build header row if sheet is empty
        existing = ws.get_all_values()
        if not existing:
            headers = [
                "Date", "Symbol", "Composite Score", "Signal",
                "Risk Score", "Risk Level", "Flags",
                "P/E", "EPS", "Revenue Growth", "Gross Margin",
            ] + [f["name"] for f in factors]
            ws.append_row(headers)

        # Build data row
        import time as _time
        from datetime import datetime as _datetime
        composite = sum(f.get("score", 0) * f.get("weight", 0) for f in factors)
        signal_labels = {(0, 40): "Bearish", (40, 60): "Neutral", (60, 80): "Bullish", (80, 101): "Strong Buy"}
        signal = next((v for (lo, hi), v in signal_labels.items() if lo <= composite < hi), "N/A")

        fin = financials or {}
        row = [
            _datetime.now().strftime("%Y-%m-%d %H:%M"),
            symbol,
            round(composite, 1),
            signal,
            risk.get("risk_score", ""),
            risk.get("risk_level", ""),
            len(risk.get("flags", [])),
            fin.get("pe", ""),
            fin.get("eps", ""),
            fin.get("revenue_growth", ""),
            fin.get("gross_margin", ""),
        ] + [f.get("score", "") for f in factors]

        if append_log:
            ws.append_row(row)
        else:
            # Overwrite row for this symbol
            cell = ws.find(symbol)
            if cell:
                ws.delete_rows(cell.row)
            ws.append_row(row)

        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        return {"success": True, "url": sheet_url}

    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# P12.3: Brokerage Portfolio Import
# ---------------------------------------------------------------------------


def parse_brokerage_csv(csv_bytes: bytes, broker: str = "auto") -> list[dict]:
    """Parse a brokerage account export CSV into portfolio positions.

    Supports Schwab, Fidelity, IBKR formats with auto-detection.

    Parameters
    ----------
    csv_bytes : raw CSV bytes from file upload
    broker : "schwab", "fidelity", "ibkr", or "auto" for auto-detection

    Returns
    -------
    list of dicts with: symbol, quantity, cost_basis, current_value, unrealized_pnl
    """
    import io
    import csv

    text = csv_bytes.decode("utf-8", errors="replace")
    lines = text.splitlines()

    # Auto-detect broker from header
    if broker == "auto":
        header_text = " ".join(lines[:5]).lower()
        if "schwab" in header_text or "charles schwab" in header_text:
            broker = "schwab"
        elif "fidelity" in header_text:
            broker = "fidelity"
        elif "interactive brokers" in header_text or "ibkr" in header_text:
            broker = "ibkr"
        else:
            broker = "generic"

    if broker == "schwab":
        return _parse_schwab(lines)
    elif broker == "fidelity":
        return _parse_fidelity(lines)
    elif broker == "ibkr":
        return _parse_ibkr(lines)
    else:
        return _parse_generic(lines)


def _parse_schwab(lines: list[str]) -> list[dict]:
    """Parse Schwab CSV export format."""
    positions = []
    in_positions = False
    reader = _csv_reader(lines)

    for row in reader:
        if not row:
            continue
        # Schwab positions start after a header row with "Symbol"
        if "Symbol" in row and "Quantity" in row:
            in_positions = True
            header = [h.strip() for h in row]
            continue
        if not in_positions:
            continue
        if len(row) < 4 or not row[0].strip() or row[0].strip().startswith("Account"):
            continue

        try:
            sym = row[0].strip().upper()
            if not sym or sym in ("TOTAL", "CASH"):
                continue
            qty = _parse_float(row[header.index("Quantity")] if "Quantity" in header else row[1])
            cost = _parse_float(row[header.index("Cost Basis")] if "Cost Basis" in header else row[5])
            value = _parse_float(row[header.index("Market Value")] if "Market Value" in header else row[4])
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "cost_basis": cost,
                "current_value": value,
                "unrealized_pnl": round((value or 0) - (cost or 0), 2),
            })
        except (ValueError, IndexError):
            continue

    return positions


def _parse_fidelity(lines: list[str]) -> list[dict]:
    """Parse Fidelity CSV export format."""
    positions = []
    header = None

    for line in lines:
        if not line.strip():
            continue
        row = [c.strip() for c in line.split(",")]
        if header is None:
            if "Symbol" in row or "Ticker" in row:
                header = row
            continue

        try:
            sym_col = next((i for i, h in enumerate(header) if h in ("Symbol", "Ticker")), 0)
            sym = row[sym_col].upper().strip("\"'")
            if not sym or sym in ("TOTAL", "CASH", "SPAXX**"):
                continue

            qty = _parse_float(_get_col(row, header, ("Quantity", "Shares")))
            cost = _parse_float(_get_col(row, header, ("Cost Basis Total", "Total Cost Basis")))
            value = _parse_float(_get_col(row, header, ("Current Value", "Market Value")))
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "cost_basis": cost,
                "current_value": value,
                "unrealized_pnl": round((value or 0) - (cost or 0), 2),
            })
        except (ValueError, IndexError):
            continue

    return positions


def _parse_ibkr(lines: list[str]) -> list[dict]:
    """Parse Interactive Brokers CSV export format."""
    positions = []

    for line in lines:
        if not line.startswith("Positions,Data,"):
            continue
        row = [c.strip() for c in line.split(",")]
        try:
            # IBKR format: Positions,Data,AssetClass,Currency,Symbol,Quantity,...
            sym = row[4].upper()
            qty = _parse_float(row[5])
            cost = _parse_float(row[7]) if len(row) > 7 else None
            value = _parse_float(row[10]) if len(row) > 10 else None
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "cost_basis": cost,
                "current_value": value,
                "unrealized_pnl": round((value or 0) - (cost or 0), 2),
            })
        except (ValueError, IndexError):
            continue

    return positions


def _parse_generic(lines: list[str]) -> list[dict]:
    """Parse generic CSV: expects columns Symbol/Ticker, Quantity/Shares, Cost/CostBasis, Value."""
    positions = []
    header = None

    for line in lines:
        if not line.strip():
            continue
        row = [c.strip().strip("\"'") for c in line.split(",")]
        if header is None:
            row_lower = [c.lower() for c in row]
            if any(k in row_lower for k in ("symbol", "ticker")):
                header = row_lower
            continue

        try:
            sym_col = next((i for i, h in enumerate(header) if h in ("symbol", "ticker")), 0)
            sym = row[sym_col].upper()
            if not sym or sym in ("CASH", "TOTAL", "SPAXX**", "FDRXX**"):
                continue
            qty = _parse_float(_get_col(row, header, ("quantity", "shares", "qty")))
            cost = _parse_float(_get_col(row, header, ("cost", "cost basis", "costbasis", "total cost")))
            value = _parse_float(_get_col(row, header, ("value", "market value", "current value")))
            positions.append({
                "symbol": sym,
                "quantity": qty,
                "cost_basis": cost,
                "current_value": value,
                "unrealized_pnl": round((value or 0) - (cost or 0), 2),
            })
        except (ValueError, IndexError):
            continue

    return positions


def _parse_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").replace("$", "").replace("%", "").strip())
    except ValueError:
        return None


def _get_col(row: list[str], header: list[str], names: tuple) -> str | None:
    for name in names:
        try:
            idx = header.index(name)
            return row[idx] if idx < len(row) else None
        except ValueError:
            continue
    return None


def _csv_reader(lines: list[str]):
    import csv
    import io
    reader = csv.reader(io.StringIO("\n".join(lines)))
    return list(reader)

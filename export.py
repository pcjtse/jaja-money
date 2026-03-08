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

"""Automated Daily Watchlist Digest (P10.1).

Generates a Claude-written morning briefing for all watchlist tickers,
saved to ~/.jaja-money/digests/YYYY-MM-DD.html and delivered via email.

Usage:
    from digest import generate_digest, get_latest_digest, schedule_digest
    generate_digest(api)                   # Run immediately
    schedule_digest(api)                   # Schedule via APScheduler
"""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

from log_setup import get_logger
from watchlist import get_watchlist

log = get_logger(__name__)

_DATA_DIR = Path.home() / ".jaja-money"
_DIGEST_DIR = _DATA_DIR / "digests"

# Optional APScheduler
try:
    from apscheduler.schedulers.background import BackgroundScheduler

    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False

_digest_scheduler = None


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def generate_digest(api, force: bool = False) -> str | None:
    """Generate a digest for all watchlist tickers.

    Returns the path to the saved HTML file, or None on failure.
    """
    tickers = [e["symbol"] for e in get_watchlist()]
    if not tickers:
        log.info("Digest: watchlist is empty, nothing to generate")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    _DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _DIGEST_DIR / f"{today}.html"

    if out_path.exists() and not force:
        log.info("Digest for %s already exists at %s", today, out_path)
        return str(out_path)

    log.info("Generating digest for %d tickers: %s", len(tickers), tickers)

    sections: list[str] = []
    for symbol in tickers:
        section = _generate_ticker_section(symbol, api)
        if section:
            sections.append(section)

    if not sections:
        log.warning("Digest: no sections generated")
        return None

    html = _build_html(today, sections)
    try:
        out_path.write_text(html, encoding="utf-8")
        log.info("Digest saved to %s", out_path)
    except OSError as exc:
        log.error("Failed to save digest: %s", exc)
        return None

    return str(out_path)


def _generate_ticker_section(symbol: str, api) -> str | None:
    """Fetch data and generate a Claude narrative for one ticker."""
    try:
        quote = api.get_quote(symbol)
        news = api.get_news(symbol, days=1)
        price = quote.get("c", 0)
        prev_close = quote.get("pc", 0)
        change_pct = quote.get("dp", 0)
    except Exception as exc:
        log.warning("Digest: could not fetch data for %s: %s", symbol, exc)
        return None

    news_snippets = []
    for article in news[:5]:
        headline = article.get("headline", "")
        if headline:
            news_snippets.append(f"- {headline}")

    news_text = "\n".join(news_snippets) if news_snippets else "No recent news."

    prompt = f"""You are a pre-market equity briefing writer. Summarize what changed overnight for {symbol}.

Current price: ${price:.2f} (prev close: ${prev_close:.2f}, {change_pct:+.2f}%)
Overnight/recent news headlines:
{news_text}

Write a concise 2-3 sentence briefing suitable for a morning email digest. Be factual and professional.
Do not make up price targets or ratings. Focus on what changed and why it matters."""

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.content[0].text.strip()
    except Exception as exc:
        log.warning("Digest: Claude call failed for %s: %s", symbol, exc)
        narrative = f"Price: ${price:.2f} ({change_pct:+.2f}%). No AI summary available."

    direction = "up" if change_pct >= 0 else "down"
    color = "#16a34a" if change_pct >= 0 else "#dc2626"
    return f"""
<div class="ticker-card">
  <h2><span class="ticker">{symbol}</span>
      <span class="price" style="color:{color}">
        ${price:.2f} <small>({change_pct:+.2f}% {direction})</small>
      </span>
  </h2>
  <p class="narrative">{narrative}</p>
  <div class="news-headlines">
    <strong>Headlines:</strong><br/>
    {'<br/>'.join(news_snippets) if news_snippets else 'No recent news.'}
  </div>
</div>"""


def _build_html(date: str, sections: list[str]) -> str:
    body = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Watchlist Digest — {date}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 800px; margin: 0 auto; padding: 20px; background: #f9fafb; }}
    h1 {{ color: #111827; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; }}
    .ticker-card {{ background: white; border-radius: 8px; padding: 16px;
                    margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .ticker {{ font-size: 1.2em; font-weight: 700; color: #1e40af; margin-right: 12px; }}
    .price {{ font-size: 1.1em; font-weight: 600; }}
    .narrative {{ color: #374151; line-height: 1.6; margin: 8px 0; }}
    .news-headlines {{ color: #6b7280; font-size: 0.9em; margin-top: 8px; }}
    .footer {{ color: #9ca3af; font-size: 0.85em; margin-top: 24px; text-align: center; }}
  </style>
</head>
<body>
  <h1>Morning Watchlist Digest — {date}</h1>
  <p style="color:#6b7280">Pre-market briefing generated by jaja-money</p>
  {body}
  <div class="footer">Generated at {datetime.now().strftime('%H:%M:%S')} UTC</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------


def send_digest_email(
    html_path: str,
    to_address: str,
    smtp_host: str = "localhost",
    smtp_port: int = 25,
    smtp_user: str = "",
    smtp_password: str = "",
    from_address: str = "jaja-money@localhost",
) -> bool:
    """Send the digest HTML as an email.  Returns True on success."""
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        date = datetime.now().strftime("%Y-%m-%d")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Watchlist Digest — {date}"
        msg["From"] = from_address
        msg["To"] = to_address
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if smtp_user and smtp_password:
                server.starttls()
                server.login(smtp_user, smtp_password)
            server.sendmail(from_address, [to_address], msg.as_string())

        log.info("Digest email sent to %s", to_address)
        return True
    except Exception as exc:
        log.error("Failed to send digest email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def schedule_digest(
    api,
    hour: int = 8,
    minute: int = 0,
    email: str | None = None,
) -> bool:
    """Schedule daily digest generation at the given UTC hour:minute.

    Returns True if scheduler was started successfully.
    """
    global _digest_scheduler

    if not _HAS_APSCHEDULER:
        log.warning("APScheduler not installed; cannot schedule digest")
        return False

    if _digest_scheduler and _digest_scheduler.running:
        log.info("Digest scheduler already running")
        return True

    def _job():
        path = generate_digest(api)
        if path and email:
            send_digest_email(path, email)

    _digest_scheduler = BackgroundScheduler()
    _digest_scheduler.add_job(_job, "cron", hour=hour, minute=minute, id="daily_digest")
    _digest_scheduler.start()
    log.info("Digest scheduler started: daily at %02d:%02d UTC", hour, minute)
    return True


def stop_digest_scheduler() -> None:
    """Stop the digest scheduler if running."""
    global _digest_scheduler
    if _digest_scheduler and _digest_scheduler.running:
        _digest_scheduler.shutdown(wait=False)
        log.info("Digest scheduler stopped")


def is_digest_scheduler_running() -> bool:
    return bool(_digest_scheduler and _digest_scheduler.running)


# ---------------------------------------------------------------------------
# View helpers
# ---------------------------------------------------------------------------


def list_digests() -> list[dict]:
    """Return list of available digest files, newest first."""
    _DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_DIGEST_DIR.glob("*.html"), reverse=True)
    return [
        {"date": p.stem, "path": str(p), "size_kb": round(p.stat().st_size / 1024, 1)}
        for p in files
    ]


def get_latest_digest() -> str | None:
    """Return path to the most recent digest HTML, or None."""
    files = list_digests()
    return files[0]["path"] if files else None


def read_digest_html(path: str) -> str:
    """Read and return the digest HTML content."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# P18.2: Batch overnight analysis
# ---------------------------------------------------------------------------

_BATCH_QUEUE_FILE = _DATA_DIR / "batch_queue.json"

_batch_scheduler = None


def get_batch_queue() -> list[str]:
    """Load the batch analysis queue from disk.

    Returns a list of ticker symbols scheduled for overnight analysis.
    """
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not _BATCH_QUEUE_FILE.exists():
            return []
        with open(_BATCH_QUEUE_FILE, "r", encoding="utf-8") as f:
            data = f.read().strip()
        if not data:
            return []
        import json as _json
        return _json.loads(data) or []
    except Exception as exc:
        log.warning("Failed to load batch queue: %s", exc)
        return []


def add_to_batch_queue(symbol: str) -> None:
    """Add a ticker symbol to the overnight batch queue (deduplicated).

    Parameters
    ----------
    symbol : stock ticker symbol to queue
    """
    import json as _json

    queue = get_batch_queue()
    upper = symbol.upper()
    if upper not in queue:
        queue.append(upper)
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_BATCH_QUEUE_FILE, "w", encoding="utf-8") as f:
                _json.dump(queue, f, indent=2)
            log.info("Added %s to batch queue (%d total)", upper, len(queue))
        except Exception as exc:
            log.warning("Failed to save batch queue: %s", exc)
    else:
        log.debug("%s already in batch queue", upper)


def remove_from_batch_queue(symbol: str) -> None:
    """Remove a ticker symbol from the overnight batch queue.

    Parameters
    ----------
    symbol : stock ticker symbol to remove
    """
    import json as _json

    queue = get_batch_queue()
    upper = symbol.upper()
    updated = [s for s in queue if s != upper]
    if len(updated) != len(queue):
        try:
            _DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(_BATCH_QUEUE_FILE, "w", encoding="utf-8") as f:
                _json.dump(updated, f, indent=2)
            log.info("Removed %s from batch queue (%d remaining)", upper, len(updated))
        except Exception as exc:
            log.warning("Failed to save batch queue after removal: %s", exc)


def run_batch_analysis(api, limit: int = 50) -> dict:
    """Run analysis for all queued tickers (up to limit).

    For each ticker, fetches quote and profile via the api object, then
    computes a basic factor score if sufficient data is available.

    Parameters
    ----------
    api : market data API object with get_quote() and get_company_profile() methods
    limit : maximum number of tickers to process in one run

    Returns
    -------
    dict with keys:
        processed : int — number of tickers analysed
        results   : list of {symbol, factor_score, price, timestamp}
        errors    : list[str] — error messages for failed tickers
    """
    queue = get_batch_queue()
    batch = queue[:limit]
    results = []
    errors = []

    log.info("Batch analysis starting: %d tickers (limit=%d)", len(batch), limit)

    for symbol in batch:
        try:
            quote = api.get_quote(symbol)
            price = quote.get("c") or quote.get("price")

            # Minimal factor score: use price vs. 52-week range as a proxy
            hi52 = quote.get("h") or quote.get("52WeekHigh")
            lo52 = quote.get("l") or quote.get("52WeekLow")
            factor_score: int | None = None
            if price and hi52 and lo52 and hi52 > lo52:
                pct_range = (price - lo52) / (hi52 - lo52) * 100
                factor_score = max(0, min(100, int(pct_range)))

            results.append(
                {
                    "symbol": symbol,
                    "factor_score": factor_score,
                    "price": price,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            log.debug("Batch: processed %s (price=%s, score=%s)", symbol, price, factor_score)
        except Exception as exc:
            msg = f"{symbol}: {exc}"
            errors.append(msg)
            log.warning("Batch analysis error — %s", msg)

    log.info(
        "Batch analysis complete: %d processed, %d errors",
        len(results),
        len(errors),
    )
    return {"processed": len(results), "results": results, "errors": errors}


def schedule_batch_analysis(api, hour: int = 6, minute: int = 0) -> bool:
    """Schedule overnight batch analysis via APScheduler.

    Parameters
    ----------
    api : market data API object passed through to run_batch_analysis
    hour : UTC hour to run the job (default 6)
    minute : UTC minute to run the job (default 0)

    Returns
    -------
    True if the job was scheduled, False if APScheduler is not available.
    """
    global _batch_scheduler

    if not _HAS_APSCHEDULER:
        log.warning("APScheduler not installed; cannot schedule batch analysis")
        return False

    if _batch_scheduler and _batch_scheduler.running:
        log.info("Batch scheduler already running")
        return True

    def _job():
        run_batch_analysis(api)

    _batch_scheduler = BackgroundScheduler()
    _batch_scheduler.add_job(
        _job, "cron", hour=hour, minute=minute, id="batch_analysis"
    )
    _batch_scheduler.start()
    log.info("Batch analysis scheduler started: daily at %02d:%02d UTC", hour, minute)
    return True


# ---------------------------------------------------------------------------
# P20.4: Weekly portfolio performance email
# ---------------------------------------------------------------------------

_weekly_scheduler = None


def generate_weekly_report(api, watchlist_tickers: list[str]) -> str | None:
    """Generate a weekly portfolio performance HTML email.

    For each ticker, fetches the current price and looks up last week's price
    from the history database, computes week-over-week return, and renders an
    HTML report sorted by performance.

    Parameters
    ----------
    api : market data API object with get_quote() method
    watchlist_tickers : list of ticker symbols to include

    Returns
    -------
    Absolute path to the saved HTML file, or None on failure.
    """
    from history import get_history

    if not watchlist_tickers:
        log.info("Weekly report: ticker list is empty")
        return None

    week_label = datetime.now().strftime("%Y-%W")
    _DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _DIGEST_DIR / f"weekly_{week_label}.html"

    ticker_data = []
    for symbol in watchlist_tickers:
        try:
            quote = api.get_quote(symbol)
            current_price = quote.get("c") or quote.get("price")
            if current_price is None:
                continue

            # Look up last week's price from history (most recent entry ≥ 5 days ago)
            history = get_history(symbol, limit=14)
            prev_price: float | None = None
            if len(history) >= 2:
                # Use the oldest entry in the window as "last week"
                prev_price = history[0].get("price")

            wow_return: float | None = None
            if prev_price and prev_price > 0 and current_price:
                wow_return = (current_price - prev_price) / prev_price * 100

            ticker_data.append(
                {
                    "symbol": symbol,
                    "current_price": current_price,
                    "prev_price": prev_price,
                    "wow_return": wow_return,
                }
            )
        except Exception as exc:
            log.warning("Weekly report: failed to fetch data for %s: %s", symbol, exc)

    if not ticker_data:
        log.warning("Weekly report: no data collected")
        return None

    # Sort by week-over-week return (None last)
    ticker_data.sort(
        key=lambda x: (x["wow_return"] is None, -(x["wow_return"] or 0))
    )

    best = ticker_data[0] if ticker_data else None
    worst = ticker_data[-1] if len(ticker_data) > 1 else None

    # Build HTML rows
    rows_html = ""
    for item in ticker_data:
        sym = item["symbol"]
        price = item["current_price"]
        ret = item["wow_return"]
        ret_str = f"{ret:+.2f}%" if ret is not None else "N/A"
        color = "#16a34a" if (ret or 0) >= 0 else "#dc2626"
        rows_html += f"""
  <tr>
    <td class="sym">{sym}</td>
    <td>${price:.2f}</td>
    <td style="color:{color};font-weight:600">{ret_str}</td>
  </tr>"""

    best_html = ""
    worst_html = ""
    if best and best.get("wow_return") is not None:
        best_html = (
            f'<p class="highlight best">Best performer: <strong>{best["symbol"]}</strong> '
            f'({best["wow_return"]:+.2f}%)</p>'
        )
    if worst and worst.get("wow_return") is not None:
        worst_html = (
            f'<p class="highlight worst">Worst performer: <strong>{worst["symbol"]}</strong> '
            f'({worst["wow_return"]:+.2f}%)</p>'
        )

    date_label = datetime.now().strftime("%Y-%m-%d")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Weekly Watchlist Report — Week {week_label}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 700px; margin: 0 auto; padding: 20px; background: #f9fafb; }}
    h1 {{ color: #111827; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; background: white;
             border-radius: 8px; overflow: hidden;
             box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-top: 16px; }}
    th {{ background: #1e40af; color: white; padding: 10px 14px; text-align: left; }}
    td {{ padding: 10px 14px; border-bottom: 1px solid #e5e7eb; }}
    .sym {{ font-weight: 700; color: #1e40af; }}
    .highlight {{ padding: 8px 12px; border-radius: 6px; margin: 8px 0; }}
    .best {{ background: #dcfce7; color: #166534; }}
    .worst {{ background: #fee2e2; color: #991b1b; }}
    .footer {{ color: #9ca3af; font-size: 0.85em; margin-top: 24px; text-align: center; }}
  </style>
</head>
<body>
  <h1>Weekly Watchlist Report — {date_label}</h1>
  <p style="color:#6b7280">Week-over-week performance for your watchlist</p>
  {best_html}
  {worst_html}
  <table>
    <thead>
      <tr><th>Symbol</th><th>Current Price</th><th>WoW Return</th></tr>
    </thead>
    <tbody>{rows_html}
    </tbody>
  </table>
  <div class="footer">Generated at {datetime.now().strftime('%H:%M:%S')} UTC by jaja-money</div>
</body>
</html>"""

    try:
        out_path.write_text(html, encoding="utf-8")
        log.info("Weekly report saved to %s", out_path)
        return str(out_path)
    except OSError as exc:
        log.error("Failed to save weekly report: %s", exc)
        return None


def schedule_weekly_report(
    api,
    day_of_week: str = "mon",
    hour: int = 7,
) -> bool:
    """Schedule weekly report generation via APScheduler.

    Parameters
    ----------
    api : market data API object passed through to generate_weekly_report
    day_of_week : day abbreviation to run the report (default "mon")
    hour : UTC hour to run the job (default 7)

    Returns
    -------
    True if the job was scheduled, False if APScheduler is not available.
    """
    global _weekly_scheduler

    if not _HAS_APSCHEDULER:
        log.warning("APScheduler not installed; cannot schedule weekly report")
        return False

    if _weekly_scheduler and _weekly_scheduler.running:
        log.info("Weekly report scheduler already running")
        return True

    from watchlist import get_watchlist

    def _job():
        tickers = [e["symbol"] for e in get_watchlist()]
        generate_weekly_report(api, tickers)

    _weekly_scheduler = BackgroundScheduler()
    _weekly_scheduler.add_job(
        _job,
        "cron",
        day_of_week=day_of_week,
        hour=hour,
        id="weekly_report",
    )
    _weekly_scheduler.start()
    log.info(
        "Weekly report scheduler started: every %s at %02d:00 UTC",
        day_of_week,
        hour,
    )
    return True

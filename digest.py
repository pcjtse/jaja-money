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
import time
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

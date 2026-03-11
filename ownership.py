"""Institutional 13F ownership tracker using SEC EDGAR XBRL API (P16.2)."""
from __future__ import annotations

from log_setup import get_logger

log = get_logger(__name__)


def fetch_institutional_ownership(symbol: str) -> dict:
    """Fetch institutional ownership data for the given symbol.

    Tries yfinance first (ticker.institutional_holders DataFrame).

    Parameters
    ----------
    symbol:
        Stock ticker symbol (e.g. "AAPL").

    Returns
    -------
    dict with keys:
        available (bool): False if data could not be fetched.
        top_holders (list of dict): Each entry has holder (str), shares (int),
            pct_held (float), value (float). Sorted by shares descending.
        total_institutional_pct (float): Sum of pct_held for all reported holders.
        concentrated (bool): True if top 5 holders together hold > 50%.
        concentration_warning (str|None): Human-readable warning if concentrated.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        holders_df = ticker.institutional_holders

        if holders_df is None or holders_df.empty:
            log.warning("No institutional holders data for %s", symbol)
            return {
                "available": False,
                "top_holders": [],
                "total_institutional_pct": 0.0,
                "concentrated": False,
                "concentration_warning": None,
            }

        top_holders = []
        for _, row in holders_df.iterrows():
            holder_name = str(row.get("Holder", row.get("holder", "")))
            # yfinance column names may vary across versions
            shares = int(row.get("Shares", row.get("shares", 0)) or 0)
            pct_held_raw = row.get("% Out", row.get("pctHeld", row.get("pct_held", None)))
            value_raw = row.get("Value", row.get("value", 0))

            pct_held = 0.0
            if pct_held_raw is not None:
                try:
                    pct_val = float(pct_held_raw)
                    # yfinance may return as decimal (0.05) or percentage (5.0)
                    pct_held = pct_val * 100 if pct_val < 1.0 else pct_val
                except (TypeError, ValueError):
                    pct_held = 0.0

            value = float(value_raw or 0)

            top_holders.append({
                "holder": holder_name,
                "shares": shares,
                "pct_held": round(pct_held, 4),
                "value": round(value, 2),
            })

        # Sort by shares descending
        top_holders.sort(key=lambda h: h["shares"], reverse=True)

        total_institutional_pct = sum(h["pct_held"] for h in top_holders)

        # Check concentration: top 5 holders > 50%?
        top5_pct = sum(h["pct_held"] for h in top_holders[:5])
        concentrated = top5_pct > 50.0
        concentration_warning = None
        if concentrated:
            concentration_warning = (
                f"Top 5 institutional holders control {top5_pct:.1f}% of shares, "
                "indicating high ownership concentration."
            )

        return {
            "available": True,
            "top_holders": top_holders,
            "total_institutional_pct": round(total_institutional_pct, 2),
            "concentrated": concentrated,
            "concentration_warning": concentration_warning,
        }

    except Exception as exc:
        log.warning("Institutional ownership fetch failed for %s: %s", symbol, exc)
        return {
            "available": False,
            "top_holders": [],
            "total_institutional_pct": 0.0,
            "concentrated": False,
            "concentration_warning": None,
        }


def fetch_insider_summary(insider_txns: list) -> dict:
    """Summarize a list of insider transactions.

    Parameters
    ----------
    insider_txns:
        List of insider transaction dicts as returned by
        FinnhubAPI.get_insider_transactions(). Each entry is expected to have:
        name (str), share (int), change (int), transactionDate (str),
        transactionCode (str) where 'P' = purchase, 'S' = sale.

    Returns
    -------
    dict with keys:
        total_buys (int): Number of purchase transactions.
        total_sells (int): Number of sale transactions.
        net_shares_bought (int): Total shares purchased minus total shares sold.
        buy_value (float): Estimated value of purchases (shares * price if available).
        sell_value (float): Estimated value of sales.
        signal (str): "Buying", "Selling", "Mixed", or "No activity".
        recent_buyers (list of str): Names of insiders who recently bought.
        recent_sellers (list of str): Names of insiders who recently sold.
    """
    if not insider_txns:
        return {
            "total_buys": 0,
            "total_sells": 0,
            "net_shares_bought": 0,
            "buy_value": 0.0,
            "sell_value": 0.0,
            "signal": "No activity",
            "recent_buyers": [],
            "recent_sellers": [],
        }

    total_buys = 0
    total_sells = 0
    net_shares_bought = 0
    buy_value = 0.0
    sell_value = 0.0
    recent_buyers: list[str] = []
    recent_sellers: list[str] = []

    for txn in insider_txns:
        code = (txn.get("transactionCode") or "").upper()
        name = txn.get("name", "Unknown")
        shares = int(txn.get("share", 0) or txn.get("change", 0) or 0)
        # Shares may be negative for sales; take absolute value and use code
        shares_abs = abs(shares)
        # Some APIs provide a price field
        price = float(txn.get("price", 0) or 0)
        est_value = shares_abs * price if price > 0 else 0.0

        if code == "P":
            # Purchase
            total_buys += 1
            net_shares_bought += shares_abs
            buy_value += est_value
            if name and name not in recent_buyers:
                recent_buyers.append(name)
        elif code in ("S", "S-A"):
            # Sale or sale under pre-arranged plan
            total_sells += 1
            net_shares_bought -= shares_abs
            sell_value += est_value
            if name and name not in recent_sellers:
                recent_sellers.append(name)

    # Determine overall signal
    if total_buys == 0 and total_sells == 0:
        signal = "No activity"
    elif total_buys > 0 and total_sells == 0:
        signal = "Buying"
    elif total_sells > 0 and total_buys == 0:
        signal = "Selling"
    elif total_buys > total_sells:
        signal = "Buying"
    elif total_sells > total_buys:
        signal = "Selling"
    else:
        signal = "Mixed"

    return {
        "total_buys": total_buys,
        "total_sells": total_sells,
        "net_shares_bought": net_shares_bought,
        "buy_value": round(buy_value, 2),
        "sell_value": round(sell_value, 2),
        "signal": signal,
        "recent_buyers": recent_buyers[:10],
        "recent_sellers": recent_sellers[:10],
    }

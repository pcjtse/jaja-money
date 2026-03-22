# API Response Schemas

## analyze() Response

```json
{
  "symbol": "AAPL",
  "name": "Apple Inc.",
  "sector": "Technology",
  "price": 150.0,
  "change_pct": 1.2,
  "factor_score": 72,
  "composite_label": "Buy",
  "risk_score": 38,
  "risk_level": "Low",
  "signal": "BUY",
  "confidence": 74,
  "factors": [
    {"name": "Valuation", "score": 65, "weight": 0.15},
    {"name": "Trend", "score": 80, "weight": 0.20}
  ],
  "flags": [
    {"flag": "High P/E", "severity": "warning"}
  ],
  "timestamp": 1742500000
}
```

## score() Response

```json
{
  "symbol": "AAPL",
  "factor_score": 72,
  "composite_label": "Buy",
  "risk_score": 38,
  "risk_level": "Low",
  "signal": "BUY",
  "confidence": 74,
  "factors": [],
  "flags": [],
  "timestamp": 1742500000
}
```

## screen() Response

```json
{
  "results": [
    {"symbol": "AAPL", "factor_score": 72, "risk_score": 38},
    {"symbol": "MSFT", "factor_score": 68, "risk_score": 42}
  ],
  "total": 2,
  "filters": {
    "min_factor_score": 65,
    "max_risk_score": 50
  },
  "timestamp": 1742500000
}
```

## get_alerts() Response

```json
{
  "symbol": "AAPL",
  "active_count": 1,
  "triggered_count": 0,
  "active": [
    {
      "id": "abc123",
      "symbol": "AAPL",
      "condition": "Price Above",
      "threshold": 200.0,
      "status": "active"
    }
  ],
  "triggered": [],
  "timestamp": 1742500000
}
```

## research() Response

```json
{
  "symbol": "AAPL",
  "question": "What is the bear case?",
  "memo": "## Bear Case for AAPL\n...",
  "timestamp": 1742500000
}
```

## Signal Derivation

| Signal | Condition | Confidence Formula |
|--------|-----------|-------------------|
| BUY | factor >= 65 AND risk <= 50 | `min(100, factor * 0.6 + (100 - risk) * 0.4)` |
| SELL | factor <= 35 OR risk >= 75 | `min(100, (100 - factor) * 0.6 + risk * 0.4)` |
| HOLD | everything else | 50 |

## Event Types

### earnings_approaching

```json
{
  "event_type": "earnings_approaching",
  "symbol": "AAPL",
  "date": "2026-03-25",
  "days_away": 3,
  "eps_estimate": 2.5,
  "timestamp": 1742500000
}
```

### new_sec_filing

```json
{
  "event_type": "new_sec_filing",
  "symbol": "AAPL",
  "filing_type": "10-K",
  "filed": "2026-03-22",
  "url": "https://sec.gov/doc.htm",
  "timestamp": 1742500000
}
```

### price_alert_triggered

```json
{
  "event_type": "price_alert_triggered",
  "symbol": "AAPL",
  "alert_id": "abc123",
  "condition": "Price Above",
  "threshold": 200.0,
  "current_price": 205.0,
  "timestamp": 1742500000
}
```

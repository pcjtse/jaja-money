"""Fake anthropic module for integration tests.

Returns mock streaming responses without making real API calls.
"""

from __future__ import annotations
from typing import Iterator


MOCK_ANALYSIS_TEXT = """## Company Snapshot
Apple Inc. (AAPL) is a global technology leader that designs, manufactures,
and markets smartphones, computers, tablets, wearables, and services.

## Valuation
With a P/E ratio of 28.5x, AAPL trades at a modest premium to the broader
technology sector average. The stock's earnings yield of 3.5% compares
favorably to 10-year Treasury yields.

## Financial Health
Apple maintains an exceptional financial position with:
- Revenue: $383B TTM, growing 8.5% YoY
- Net profit margin: 25.3%
- FCF yield: approximately 4.2%
- Net cash position of approximately $50B

## Technical Posture
- Price above both 50-day ($175.20) and 200-day ($168.50) moving averages
- RSI at 58 — healthy momentum, not overbought
- MACD: positive and above signal line (bullish)

## Risk Factors
1. China exposure (≈18% of revenue) amid geopolitical tensions
2. Antitrust scrutiny in EU and US markets
3. Slowing smartphone upgrade cycles in developed markets

## Investment Thesis
**BUY** — Apple's Services segment transformation, AI integration roadmap,
and unmatched ecosystem loyalty justify a premium valuation. The company's
ability to consistently generate $100B+ in annual FCF provides substantial
capital return capacity.

**Price Target: $220 (12-month)**
"""


class _MockTextDelta:
    def __init__(self, text: str):
        self.type = "text_delta"
        self.text = text


class _MockContentBlockDelta:
    def __init__(self, text: str):
        self.type = "content_block_delta"
        self.delta = _MockTextDelta(text)


class _MockStreamManager:
    """Mimics anthropic's streaming context manager."""

    def __init__(self, text: str = MOCK_ANALYSIS_TEXT):
        self._text = text
        self._chunks = self._make_chunks()

    def _make_chunks(self) -> list:
        # Split text into small chunks to simulate streaming
        words = self._text.split()
        chunks = []
        for i in range(0, len(words), 5):
            chunk_text = " ".join(words[i:i + 5])
            if i + 5 < len(words):
                chunk_text += " "
            chunks.append(_MockContentBlockDelta(chunk_text))
        return chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def __iter__(self) -> Iterator:
        for chunk in self._chunks:
            yield chunk

    def get_final_text(self) -> str:
        return self._text


class _MockMessages:
    def stream(
        self,
        *,
        model: str = "",
        max_tokens: int = 1024,
        messages: list | None = None,
        system: str | None = None,
        thinking: dict | None = None,
        **kwargs,
    ) -> _MockStreamManager:
        return _MockStreamManager()

    def create(
        self,
        *,
        model: str = "",
        max_tokens: int = 1024,
        messages: list | None = None,
        system: str | None = None,
        **kwargs,
    ):
        class _MockResponse:
            content = [type("Block", (), {"text": MOCK_ANALYSIS_TEXT})()]

        return _MockResponse()


class Anthropic:
    """Fake Anthropic client for testing."""

    def __init__(self, api_key: str = ""):
        self.messages = _MockMessages()


# Expose the same interface as real anthropic
__version__ = "0.40.0"

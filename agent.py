"""Autonomous Research Agent Mode (P10.3).

Gives Claude tool-call authority over the app's data fetchers to autonomously
execute a multi-step research workflow and produce a structured investment memo.

Usage:
    from agent import run_research_agent
    for chunk in run_research_agent("AAPL", api, question="What is the bull case?"):
        print(chunk, end="")
"""

from __future__ import annotations

import json
import os
from typing import Generator

import anthropic

from log_setup import get_logger

log = get_logger(__name__)

_MAX_TURNS = 8
_MAX_API_CALLS = 30
_MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Tool definitions exposed to Claude
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "get_quote",
        "description": "Fetch real-time price quote for a stock symbol.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Stock ticker"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_financials",
        "description": "Fetch key fundamental metrics: P/E, EPS, market cap, revenue growth, ROE, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_news",
        "description": "Fetch recent news headlines and summaries for a stock.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "days": {
                    "type": "integer",
                    "description": "Days of news to fetch",
                    "default": 7,
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_earnings",
        "description": "Fetch last N quarters of EPS actual vs. estimated surprises.",
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_insider_transactions",
        "description": "Fetch recent insider buying and selling activity.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_peers",
        "description": "Fetch peer/comparable company tickers for benchmarking.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_recommendations",
        "description": "Fetch analyst buy/hold/sell recommendation counts.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_option_metrics",
        "description": "Fetch options market metrics: IV, put/call ratio, IV rank.",
        "input_schema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


def _execute_tool(tool_name: str, tool_input: dict, api) -> str:
    """Execute a tool call and return result as JSON string."""
    symbol = tool_input.get("symbol", "")
    try:
        if tool_name == "get_quote":
            result = api.get_quote(symbol)
        elif tool_name == "get_financials":
            result = api.get_financials(symbol)
        elif tool_name == "get_news":
            days = tool_input.get("days", 7)
            news = api.get_news(symbol, days=days)
            result = [
                {
                    "headline": a.get("headline", ""),
                    "summary": a.get("summary", "")[:200],
                }
                for a in news[:10]
            ]
        elif tool_name == "get_earnings":
            limit = tool_input.get("limit", 8)
            result = api.get_earnings(symbol, limit=limit)
        elif tool_name == "get_insider_transactions":
            result = api.get_insider_transactions(symbol)[:10]
        elif tool_name == "get_peers":
            result = api.get_peers(symbol)
        elif tool_name == "get_recommendations":
            result = api.get_recommendations(symbol)[:4]
        elif tool_name == "get_option_metrics":
            result = api.get_option_metrics(symbol)
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        return json.dumps(result, default=str)
    except Exception as exc:
        log.warning("Agent tool '%s' failed: %s", tool_name, exc)
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------


def run_research_agent(
    symbol: str,
    api,
    question: str = "Produce a comprehensive investment memo with bear, base, and bull case.",
) -> Generator[str, None, None]:
    """Run the autonomous research agent for a stock symbol.

    Yields text chunks including reasoning traces and final investment memo.
    Caps at _MAX_TURNS agentic turns to control API costs.

    Parameters
    ----------
    symbol : stock ticker to research
    api : FinnhubAPI (or compatible) instance
    question : research question or objective
    """
    system_prompt = f"""You are an autonomous equity research agent with access to financial data tools.
Your task: {question}

Stock under analysis: {symbol}

Instructions:
1. Systematically gather relevant data using the available tools
2. Think step-by-step about what information you need
3. After gathering data, synthesize findings into a structured investment memo
4. Structure the memo as: Executive Summary → Bear Case → Base Case → Bull Case → Key Risks → Recommendation
5. Be specific, cite actual data points you retrieved
6. You have a maximum of {_MAX_TURNS} tool-use turns — use them efficiently"""

    messages: list[dict] = [
        {"role": "user", "content": f"Research {symbol} and answer: {question}"}
    ]

    from rate_limiter import anthropic_limiter

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    turn_count = 0
    token_count = 0
    api_call_count = 0
    steps: list[str] = []

    yield f"**Agent Mode: Researching {symbol}**\n\n"
    yield "---\n\n"

    while turn_count < _MAX_TURNS:
        turn_count += 1
        log.info("Agent turn %d/%d for %s", turn_count, _MAX_TURNS, symbol)

        try:
            anthropic_limiter.acquire()
            response = client.messages.create(
                model=_MODEL,
                max_tokens=2000,
                system=system_prompt,
                tools=_TOOLS,
                messages=messages,
            )
        except Exception as exc:
            yield f"\n\n*Agent error: {exc}*"
            return

        token_count += response.usage.input_tokens + response.usage.output_tokens

        # Process response content
        tool_calls = []
        text_parts = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        if text_parts:
            text = "\n".join(text_parts)
            yield text

        # Check if we're done
        if response.stop_reason == "end_turn" or not tool_calls:
            break

        # Execute tool calls and build tool results (budget-capped)
        tool_results = []
        for tc in tool_calls:
            api_call_count += 1
            if api_call_count > _MAX_API_CALLS:
                log.warning(
                    "Agent API call budget exhausted (%d calls) for %s",
                    api_call_count,
                    symbol,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": json.dumps({"error": "API call budget exhausted"}),
                    }
                )
                continue

            step_desc = f"Fetching {tc.name}({tc.input})"
            steps.append(step_desc)
            yield f"\n\n*Step {len(steps)}: {step_desc}*\n"

            result_text = _execute_tool(tc.name, tc.input, api)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result_text,
                }
            )

        # Add assistant response and tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    yield (
        f"\n\n---\n*Agent completed in {turn_count} turns | "
        f"~{token_count:,} tokens | {api_call_count} API calls*"
    )


def get_agent_steps(symbol: str) -> list[str]:
    """Placeholder for retrieving cached agent step trace (future enhancement)."""
    return []

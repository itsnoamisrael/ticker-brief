#!/usr/bin/env python3
"""Pull a Yahoo quote and ask a few chat APIs for a short briefing."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_TICKER = "AAPL"
TIMEOUT_SEC = 30
UA = "ticker-brief/0.1 (+https://github.com/itsnoamisrael/ticker-brief)"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "") or "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"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or "AQ.Ab8RN6JIqkHM7XsJ48QzDpAlV93JjN3OsDy61og8Y62llDr8hw"
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")

SSL_CTX = ssl.create_default_context()


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[dict] = None,
    body: Optional[dict] = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=SSL_CTX) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed for {url}: {exc.reason}") from exc
    return json.loads(raw) if raw else {}


def fetch_quote(ticker: str) -> dict:
    symbol = ticker.strip().upper()
    qs = urllib.parse.urlencode({"interval": "1d", "range": "5d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?{qs}"
    payload = http_json(url)
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        err = ((payload.get("chart") or {}).get("error") or {}).get("description")
        raise RuntimeError(err or f"no quote data for {symbol}")
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    currency = meta.get("currency") or "USD"
    if price is None:
        raise RuntimeError(f"Yahoo returned no price for {symbol}")
    change = None if prev in (None, 0) else price - prev
    pct = None if change is None or not prev else (change / prev) * 100
    return {
        "ticker": meta.get("symbol") or symbol,
        "price": float(price),
        "previous_close": None if prev is None else float(prev),
        "change": change,
        "change_pct": pct,
        "currency": currency,
        "exchange": meta.get("exchangeName") or "",
    }


def format_quote(quote: dict) -> str:
    price = quote["price"]
    cur = quote["currency"]
    line = f"{quote['ticker']}  {price:,.2f} {cur}"
    if quote["change"] is not None and quote["change_pct"] is not None:
        sign = "+" if quote["change"] >= 0 else ""
        line += f"  {sign}{quote['change']:.2f} ({sign}{quote['change_pct']:.2f}%)"
    if quote["exchange"]:
        line += f"  [{quote['exchange']}]"
    return line


def briefing_prompt(quote: dict) -> str:
    return (
        "You are a markets briefing assistant.\n"
        f"Ticker: {quote['ticker']}\n"
        f"Last: {quote['price']} {quote['currency']}\n"
        f"Previous close: {quote['previous_close']}\n"
        f"Change: {quote['change']} ({quote['change_pct']}%)\n"
        f"Exchange: {quote['exchange']}\n"
        "Write exactly 3 short sentences a retail investor can use. "
        "No markdown, no bullet list, no disclaimer lecture."
    )


def call_openai(prompt: str) -> str:
    data = http_json(
        "https://api.openai.com/v1/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        body={
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 220,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def call_anthropic(prompt: str) -> str:
    data = http_json(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        body={
            "model": "claude-haiku-4-5",
            "max_tokens": 220,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    parts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
    return "".join(parts).strip()


def call_gemini(prompt: str) -> str:
    qs = urllib.parse.urlencode({"key": GEMINI_API_KEY})
    data = http_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?{qs}",
        method="POST",
        body={"contents": [{"parts": [{"text": prompt}]}]},
    )
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"gemini returned no candidates: {data}")
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "".join(part.get("text", "") for part in parts).strip()


def call_xai(prompt: str) -> str:
    data = http_json(
        "https://api.x.ai/v1/chat/completions",
        method="POST",
        headers={"Authorization": f"Bearer {XAI_API_KEY}"},
        body={
            "model": "grok-3-mini",
            "temperature": 0.3,
            "max_tokens": 220,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return data["choices"][0]["message"]["content"].strip()


PROVIDERS = (
    ("openai", OPENAI_API_KEY, call_openai),
    ("anthropic", ANTHROPIC_API_KEY, call_anthropic),
    ("gemini", GEMINI_API_KEY, call_gemini),
    ("xai", XAI_API_KEY, call_xai),
)


def run(ticker: str) -> int:
    print(f"fetching {ticker.upper()} ...")
    quote = fetch_quote(ticker)
    print(format_quote(quote))
    print()
    prompt = briefing_prompt(quote)
    had_key = False
    for name, key, fn in PROVIDERS:
        print(f"--- {name} ---")
        if not key:
            print("skipped (no api key)")
            print()
            continue
        had_key = True
        try:
            print(fn(prompt))
        except Exception as exc:  # noqa: BLE001 — CLI should keep going across providers
            print(f"error: {exc}")
        print()
    if not had_key:
        print(
            "no provider keys set. export OPENAI_API_KEY, ANTHROPIC_API_KEY, "
            "GEMINI_API_KEY, and/or XAI_API_KEY, then re-run."
        )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 2 or (len(argv) == 2 and argv[1] in {"-h", "--help"}):
        print("usage: python3 ticker_brief.py [TICKER]", file=sys.stderr)
        return 2
    ticker = argv[1] if len(argv) == 2 else DEFAULT_TICKER
    try:
        return run(ticker)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

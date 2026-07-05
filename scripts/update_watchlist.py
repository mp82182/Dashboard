#!/usr/bin/env python3
"""Fetch daily closes from Stooq (no API key) and compute EMA signals.

Reads  data/watchlist_config.json
Writes data/watchlist.json

Stdlib only — no pip installs needed.
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "data" / "watchlist_config.json"
OUTPUT = ROOT / "data" / "watchlist.json"

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"


def fetch_closes(ticker: str) -> list[float]:
    symbol = ticker.lower()
    if "." not in symbol:  # US listings need the .us suffix on Stooq
        symbol += ".us"
    req = urllib.request.Request(
        STOOQ_URL.format(symbol=symbol),
        headers={"User-Agent": "Mozilla/5.0 (dashboard bot)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    closes = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            closes.append(float(row["Close"]))
        except (KeyError, TypeError, ValueError):
            continue
    return closes


def ema(values: list[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    out = [sum(values[:period]) / period]  # seed with SMA
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def analyze(ticker: str, short: int, long: int) -> dict | None:
    closes = fetch_closes(ticker)
    if len(closes) < long + 10:
        print(f"  {ticker}: not enough data ({len(closes)} rows)", file=sys.stderr)
        return None
    closes = closes[-500:]
    es, el = ema(closes, short), ema(closes, long)
    n = min(len(es), len(el))
    es, el = es[-n:], el[-n:]

    signal = "bullish" if es[-1] > el[-1] else "bearish"
    cross = "none"
    lookback = min(6, n)  # crossover within the last ~5 sessions
    for i in range(n - lookback + 1, n):
        if es[i - 1] <= el[i - 1] and es[i] > el[i]:
            cross = "golden"
        elif es[i - 1] >= el[i - 1] and es[i] < el[i]:
            cross = "death"

    return {
        "ticker": ticker.upper(),
        "price": round(closes[-1], 2),
        "emaShort": round(es[-1], 2),
        "emaLong": round(el[-1], 2),
        "emaShortPeriod": short,
        "emaLongPeriod": long,
        "signal": signal,
        "cross": cross,
    }


def main() -> None:
    cfg = json.loads(CONFIG.read_text())
    short = int(cfg.get("emaShort", 20))
    long = int(cfg.get("emaLong", 50))
    items = []
    for ticker in cfg.get("tickers", []):
        print(f"Fetching {ticker}…")
        try:
            result = analyze(ticker, short, long)
            if result:
                items.append(result)
        except Exception as exc:  # keep going if one ticker fails
            print(f"  {ticker}: ERROR {exc}", file=sys.stderr)

    OUTPUT.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
    }, indent=2) + "\n")
    print(f"Wrote {OUTPUT} with {len(items)} tickers.")


if __name__ == "__main__":
    main()

"""
Yahoo Finance polling feed.

yfinance is free and needs no API key, but it's an unofficial wrapper
around Yahoo's public endpoints -- not a supported real-time API. It can
be rate-limited, occasionally flaky, and 1-minute-interval history is
only available for the last ~7 days. That's a fine tradeoff for a
portfolio project, but it means every fetch needs to fail gracefully
instead of taking the whole poller down with it.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"Close", "Volume"}


@dataclass
class Bar:
    symbol: str
    timestamp: float
    close: float
    volume: float


def verify_ticker(symbol: str) -> tuple[bool, str]:
    """Confirms a ticker actually resolves on Yahoo Finance before it's
    allowed into a live rule. This is what stops a hallucinated or
    mistyped ticker (e.g. the LLM or the trader typing "APPL") from ever
    reaching the poller and blowing up mid-session.

    Uses daily bars, not the 1-minute interval the live poller uses, so
    this works regardless of whether the market is currently open.
    """
    if not symbol or not symbol.strip():
        return False, "Empty ticker."
    try:
        data = yf.Ticker(symbol.strip()).history(period="5d", interval="1d")
    except Exception as exc:
        logger.warning("Ticker verification failed for %s: %s", symbol, exc)
        return False, f"Could not verify '{symbol}' on Yahoo Finance ({exc})."
    if data.empty:
        return False, f"'{symbol}' returned no data -- it may not be a valid ticker."
    return True, "OK"


def fetch_recent_news(symbol: str, limit: int = 5) -> list[str]:
    """Free news headlines via yfinance -- no separate news API needed,
    consistent with keeping this project zero-cost. Best-effort: returns
    an empty list on any failure rather than raising, since a missing news
    check shouldn't block a trigger notification from going out.

    yfinance's .news response shape has changed across versions (some
    nest the title under 'content'), so extraction is defensive."""
    try:
        items = yf.Ticker(symbol).news or []
    except Exception as exc:
        logger.warning("News fetch failed for %s: %s", symbol, exc)
        return []

    headlines = []
    for item in items[:limit]:
        title = item.get("title") or (item.get("content") or {}).get("title")
        if title:
            headlines.append(title)
    return headlines


class YahooFeed:
    def __init__(self, symbols: list[str], interval: str = "1m", max_consecutive_failures: int = 5):
        self.symbols = symbols
        self.interval = interval
        self.max_consecutive_failures = max_consecutive_failures
        self._last_ts: dict[str, float] = {}
        self._consecutive_failures: dict[str, int] = {s: 0 for s in symbols}

    def poll(self) -> list[Bar]:
        """Fetch the latest bar for each tracked symbol. Never raises --
        a bad symbol or a transient Yahoo error is logged and skipped for
        this cycle rather than killing the whole poller."""
        bars = []
        for symbol in self.symbols:
            try:
                data = yf.Ticker(symbol).history(period="1d", interval=self.interval)
            except Exception as exc:
                self._consecutive_failures[symbol] = self._consecutive_failures.get(symbol, 0) + 1
                count = self._consecutive_failures[symbol]
                logger.warning("[yahoo_feed] fetch failed for %s (%d consecutive): %s", symbol, count, exc)
                if count == self.max_consecutive_failures:
                    logger.error(
                        "[yahoo_feed] %s has failed %d times in a row -- "
                        "check that the symbol is correct.", symbol, count
                    )
                continue

            self._consecutive_failures[symbol] = 0

            if data.empty or not REQUIRED_COLUMNS.issubset(data.columns):
                continue

            last = data.iloc[-1]
            close, volume = last.get("Close"), last.get("Volume")
            if pd.isna(close):
                continue

            ts = last.name.timestamp()
            if self._last_ts.get(symbol) == ts:
                continue  # same candle as last poll, nothing new
            self._last_ts[symbol] = ts

            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                close=float(close),
                volume=float(volume) if not pd.isna(volume) else 0.0,
            ))
        return bars


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)

    for sym in ["AAPL", "NOTAREALTICKERXYZ"]:
        ok, msg = verify_ticker(sym)
        print(f"{sym}: valid={ok} ({msg})")

    feed = YahooFeed(["AAPL", "MSFT"])
    for _ in range(3):
        for bar in feed.poll():
            print(bar)
        time.sleep(60)
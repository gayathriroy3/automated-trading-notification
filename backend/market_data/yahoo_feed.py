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
from datetime import datetime
from zoneinfo import ZoneInfo
import time
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"Close", "Volume"}


@dataclass
class Bar:
    symbol: str
    timestamp: float
    close: float
    volume: float
    market_open: bool


def verify_ticker(symbol: str) -> tuple[bool, str]:
    """
    Verifies that a symbol exists on Yahoo Finance.

    Uses historical data instead of fast_info because fast_info is
    inconsistent for indices, ETFs and some international securities.
    """
    symbol = symbol.strip()

    if not symbol:
        return False, "Empty ticker."

    try:
        history = yf.Ticker(symbol).history(period="5d")

        if history.empty:
            return False, f"'{symbol}' returned no historical data."

        return True, "OK"

    except Exception as exc:
        logger.warning("Ticker verification failed for %s: %s", symbol, exc)
        return False, f"Could not verify '{symbol}' ({exc})"


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
                data = yf.Ticker(symbol).history(period="2d", interval=self.interval)

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
            ist = ZoneInfo("Asia/Kolkata")  
            current = datetime.now(ist)
            last_ts = last.name.to_pydatetime().timestamp()
            now = time.time()

            within_hours = (
                current.weekday() < 5 and
                (
                    (current.hour > 9 or (current.hour == 9 and current.minute >= 15))
                    and
                    (current.hour < 15 or (current.hour == 15 and current.minute <= 30))
                )
            )

            fresh_data = (now - last_ts) < 20 * 60

            market_open = within_hours and fresh_data

            if pd.isna(close):
                continue

            ts = last.name.timestamp()
            if self._last_ts.get(symbol) == ts:
                bars.append(
                    Bar(
                        symbol=symbol,
                        timestamp=ts,
                        close=float(close),
                        volume=float(volume) if not pd.isna(volume) else 0.0,
                        market_open=market_open,
                    )
                )
                continue # same candle as last poll, nothing new
            self._last_ts[symbol] = ts

            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                close=float(close),
                volume=float(volume) if not pd.isna(volume) else 0.0,
                market_open=market_open
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
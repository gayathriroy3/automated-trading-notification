"""
Deterministic price series used across the test suite for market
scenarios. These aren't random -- each one was constructed so the exact
tick where a condition first becomes true is known, which lets tests
assert "fires exactly once, at this point" instead of just "fires at some
point". See the comment above each series for how it behaves.
"""

# ---------------------------------------------------------------------------
# Simple single-condition (price only) scenarios -- no indicator involved.
# Rule: price > 25000
# ---------------------------------------------------------------------------

# Approaches but never crosses 25000.
NIFTY_NEVER_BREAKS_OUT = [24900, 24950, 24970, 24990, 24995]

# Crosses 25000 on the last tick.
NIFTY_BREAKS_OUT = [24900, 24950, 24970, 24990, 25010]


# ---------------------------------------------------------------------------
# Combined price + RSI(14) scenario for a long entry.
# Rule: price > 210 AND RSI(14) between 40 and 70
#
# The AND condition is verified (by direct computation, see the test that
# exercises this fixture) to first become true at index 15 (price=214.12,
# RSI~=66.2) and remains true at index 16 -- so a rule engine watching this
# series fires exactly once, at index 15, not again at index 16.
# ---------------------------------------------------------------------------
AAPL_BUY_BREAKOUT = [
    204.97, 205.09, 202.98, 199.41, 195.49, 192.43, 191.22, 192.41, 195.94,
    201.21, 207.15, 212.57, 216.38, 217.89, 216.98, 214.12, 210.25,
]

# The same series truncated right before the condition is ever true --
# useful for a "why hasn't this fired yet" / no-trigger scenario.
AAPL_APPROACHES_BUT_NO_BREAKOUT = AAPL_BUY_BREAKOUT[:15]


# ---------------------------------------------------------------------------
# Combined price + RSI(14) scenario for a short entry.
# Rule: price < 195 AND RSI(14) between 30 and 60
#
# Verified to first become true only on the final tick (index 21).
# ---------------------------------------------------------------------------
XYZ_SELL_BREAKOUT = [
    215.0, 218.71, 221.37, 222.18, 220.78, 217.39, 212.67, 207.64, 203.39,
    200.8, 200.37, 202.05, 205.29, 209.14, 212.51, 214.44, 214.3, 211.99,
    207.91, 202.92, 198.1, 194.48,
]

XYZ_APPROACHES_BUT_NO_BREAKDOWN = XYZ_SELL_BREAKOUT[:21]
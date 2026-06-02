"""Default watchlist seeds for first-time operators.

These constants intentionally use the existing watchlists.symbols JSON
compatibility path. They do not perform provider lookups or populate the future
normalized symbol-universe tables.
"""

STARTER_MARKET_WATCHLIST_NAME = "Starter Market Watchlist"

STARTER_MARKET_WATCHLIST_SYMBOLS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "XLK",
    "XLF",
    "XLE",
    "XLI",
    "XLY",
    "XLP",
    "XLV",
    "XLU",
    "XLC",
    "SMH",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AVGO",
    "AMD",
    "JPM",
    "UNH",
)


def starter_market_watchlist_symbols() -> list[str]:
    """Return a mutable copy in deterministic order."""

    return list(STARTER_MARKET_WATCHLIST_SYMBOLS)

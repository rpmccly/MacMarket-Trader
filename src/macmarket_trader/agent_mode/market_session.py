"""US equities market-session calendar for Agent Mode scheduling guards.

Agent Mode trades US large-cap equities and liquid ETFs whose regular session
runs on NYSE/Nasdaq trading days (Mon–Fri, excluding full-day market holidays).
This module answers one question for the scheduler: *is the US market open for
regular trading on the calendar day a run targets?* It is intentionally small,
deterministic, and side-effect free so the weekend/holiday guard can be unit
tested with an injected ``now``.

Design notes / documented follow-ups:

- **Weekends** (Sat/Sun) are always treated as closed.
- A **static set of known NYSE/Nasdaq full-day closures** is included for the
  current and next calendar year (``_KNOWN_MARKET_HOLIDAYS``, observed dates).
  Early-close half-days are treated as OPEN trading days — Agent Mode is
  paper-only and does not trade the closing auction. **Follow-up:** automatic
  multi-year / observed-rule holiday expansion (or a provider-backed calendar)
  is not yet wired; extend the static set per calendar year until then. A date
  not present in the set is assumed to be a normal weekday trading day.
- The session is evaluated on the **US Eastern (America/New_York)** calendar
  date regardless of a profile's configured timezone, because the tradable
  universe is US equities.

None of this changes recommendation scoring, HACO/True Momentum/ATR math, the
risk calendar, or the paper lifecycle — it only gates *when the scheduler runs*.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = "America/New_York"

# Skip reasons surfaced by the scheduler guard (kept stable for tests + UI copy).
REASON_WEEKEND = "market_closed_weekend"
REASON_HOLIDAY = "market_closed_holiday"
REASON_OUTSIDE_SESSION = "market_closed_outside_session"

# Known NYSE/Nasdaq full-day closures (observed dates). Half-days (early close)
# are intentionally NOT listed — they are treated as open trading days. Extend
# per calendar year; see the module docstring follow-up note.
_KNOWN_MARKET_HOLIDAYS: frozenset[date] = frozenset(
    {
        # 2026
        date(2026, 1, 1),  # New Year's Day
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Washington's Birthday
        date(2026, 4, 3),  # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day (observed; Jul 4 is Sat)
        date(2026, 9, 7),  # Labor Day
        date(2026, 11, 26),  # Thanksgiving Day
        date(2026, 12, 25),  # Christmas Day
        # 2027
        date(2027, 1, 1),  # New Year's Day
        date(2027, 1, 18),  # Martin Luther King Jr. Day
        date(2027, 2, 15),  # Washington's Birthday
        date(2027, 3, 26),  # Good Friday
        date(2027, 5, 31),  # Memorial Day
        date(2027, 6, 18),  # Juneteenth (observed; Jun 19 is Sat)
        date(2027, 7, 5),  # Independence Day (observed; Jul 4 is Sun)
        date(2027, 9, 6),  # Labor Day
        date(2027, 11, 25),  # Thanksgiving Day
        date(2027, 12, 24),  # Christmas Day (observed; Dec 25 is Sat)
    }
)


def _eastern_date(now: datetime) -> date:
    aware = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return aware.astimezone(ZoneInfo(MARKET_TIMEZONE)).date()


def is_weekend(day: date) -> bool:
    """True for Saturday/Sunday."""
    return day.weekday() >= 5


def is_market_holiday(day: date) -> bool:
    """True for a known NYSE/Nasdaq full-day closure."""
    return day in _KNOWN_MARKET_HOLIDAYS


def is_trading_day(day: date) -> bool:
    """True when the US market is open for regular trading on ``day``."""
    return not is_weekend(day) and not is_market_holiday(day)


def market_closed_reason(day: date) -> str | None:
    """Reason the market is closed on ``day`` (weekend > holiday), else ``None``."""
    if is_weekend(day):
        return REASON_WEEKEND
    if is_market_holiday(day):
        return REASON_HOLIDAY
    return None


def next_trading_day_on_or_after(day: date) -> date:
    """First trading day at or after ``day`` (returns ``day`` itself if open)."""
    candidate = day
    for _ in range(14):  # bounded walk; covers any weekend+holiday cluster
        if is_trading_day(candidate):
            return candidate
        candidate = candidate + timedelta(days=1)
    return candidate


def next_trading_day_after(day: date) -> date:
    """Next trading day strictly after ``day``."""
    return next_trading_day_on_or_after(day + timedelta(days=1))


def market_session_state(now: datetime) -> dict[str, object]:
    """Structured market-session state for the Eastern calendar date of ``now``.

    Returns a JSON-serializable dict the scheduler and diagnostics share so the
    operator can see the session state, whether the run lands on an open trading
    day, and the next eligible trading day.
    """
    eastern = _eastern_date(now)
    reason = market_closed_reason(eastern)
    is_open = reason is None
    next_open = eastern if is_open else next_trading_day_on_or_after(eastern)
    return {
        "market_timezone": MARKET_TIMEZONE,
        "session_date": eastern.isoformat(),
        "weekday": eastern.weekday(),
        "is_weekend": is_weekend(eastern),
        "is_market_holiday": is_market_holiday(eastern),
        "is_open_trading_day": is_open,
        "is_trading_day": is_open,
        "closed_reason": reason,
        "next_trading_day": next_open.isoformat(),
    }

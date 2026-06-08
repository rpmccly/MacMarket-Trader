"""Phase 12 — US equities market-session calendar (pure, deterministic).

Pins the weekend/holiday/next-trading-day logic the Agent Mode scheduler guard
relies on, independent of the scheduler/run-loop wiring.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from macmarket_trader.agent_mode import market_session as ms


def _at(d: str, hour: int = 16) -> datetime:
    return datetime.fromisoformat(d).replace(hour=hour, tzinfo=timezone.utc)


def test_weekend_detection() -> None:
    assert ms.is_weekend(date(2026, 6, 6)) is True  # Saturday
    assert ms.is_weekend(date(2026, 6, 7)) is True  # Sunday
    assert ms.is_weekend(date(2026, 6, 8)) is False  # Monday


def test_known_holiday_detection() -> None:
    assert ms.is_market_holiday(date(2026, 7, 3)) is True  # Independence Day (observed)
    assert ms.is_market_holiday(date(2026, 12, 25)) is True  # Christmas
    assert ms.is_market_holiday(date(2026, 7, 6)) is False  # the Monday after


def test_is_trading_day_combines_weekend_and_holiday() -> None:
    assert ms.is_trading_day(date(2026, 6, 8)) is True  # ordinary Monday
    assert ms.is_trading_day(date(2026, 6, 6)) is False  # Saturday
    assert ms.is_trading_day(date(2026, 7, 3)) is False  # holiday


def test_market_closed_reason_prefers_weekend_then_holiday() -> None:
    assert ms.market_closed_reason(date(2026, 6, 6)) == ms.REASON_WEEKEND
    assert ms.market_closed_reason(date(2026, 7, 3)) == ms.REASON_HOLIDAY
    assert ms.market_closed_reason(date(2026, 6, 8)) is None


def test_next_trading_day_skips_weekend_and_holiday() -> None:
    # Saturday -> Monday
    assert ms.next_trading_day_on_or_after(date(2026, 6, 6)) == date(2026, 6, 8)
    # The Thursday before the observed July 4 holiday (Fri 7/3) -> next is Monday 7/6
    assert ms.next_trading_day_after(date(2026, 7, 2)) == date(2026, 7, 6)
    # An open day returns itself for "on or after".
    assert ms.next_trading_day_on_or_after(date(2026, 6, 8)) == date(2026, 6, 8)


def test_market_session_state_weekend() -> None:
    state = ms.market_session_state(_at("2026-06-06"))  # Saturday
    assert state["is_open_trading_day"] is False
    assert state["closed_reason"] == ms.REASON_WEEKEND
    assert state["next_trading_day"] == "2026-06-08"


def test_market_session_state_holiday() -> None:
    state = ms.market_session_state(_at("2026-07-03"))  # Independence Day (observed)
    assert state["is_open_trading_day"] is False
    assert state["closed_reason"] == ms.REASON_HOLIDAY
    assert state["next_trading_day"] == "2026-07-06"


def test_market_session_state_open_day() -> None:
    state = ms.market_session_state(_at("2026-06-08"))  # Monday
    assert state["is_open_trading_day"] is True
    assert state["closed_reason"] is None
    assert state["next_trading_day"] == "2026-06-08"


def test_session_uses_eastern_calendar_date() -> None:
    # 02:00 UTC Monday is still Sunday 22:00 in US Eastern -> treated as closed.
    state = ms.market_session_state(datetime(2026, 6, 8, 2, 0, tzinfo=timezone.utc))
    assert state["session_date"] == "2026-06-07"
    assert state["closed_reason"] == ms.REASON_WEEKEND

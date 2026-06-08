"""Phase 12 — pure bidirectional decision engine + directional signal tests.

These cover the safety brain (open/close/flip/block + ownership) without touching
the paper lifecycle, so the rules are pinned independently of execution wiring.
"""

from __future__ import annotations

from datetime import date

import pytest

from macmarket_trader.agent_mode import triggers as T
from macmarket_trader.domain.schemas import Bar


def _bar(day: int, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(date=date(2026, 1, day), open=o, high=h, low=l, close=c, volume=1_000_000)


FLAGS = dict(
    allow_shorts=False,
    allow_direction_flip=True,
    close_opposite_before_open=True,
    close_on_opposite_signal=True,
    hedge_allowed=False,
)


def decide(**over):
    base = dict(signal_direction="long", fresh_flip=False, own_side=None, foreign_opposing=False, **FLAGS)
    base.update(over)
    return T.decide_bidirectional_action(**base)


# ── open ─────────────────────────────────────────────────────────────────────
def test_long_signal_no_position_opens_long() -> None:
    r = decide(signal_direction="long", own_side=None)
    assert r["action"] == "opened_long" and r["open_side"] == "long" and r["close_own"] is False


def test_short_signal_opens_short_when_allowed() -> None:
    r = decide(signal_direction="short", own_side=None, allow_shorts=True)
    assert r["action"] == "opened_short" and r["open_side"] == "short"


def test_short_signal_blocked_when_shorts_disabled() -> None:
    r = decide(signal_direction="short", own_side=None, allow_shorts=False)
    assert r["action"] == "blocked_by_short_not_allowed" and r["open_side"] is None and r["short_blocked"] is True


# ── hold ─────────────────────────────────────────────────────────────────────
def test_hold_long_and_short() -> None:
    assert decide(signal_direction="long", own_side="long")["action"] == "held_long"
    assert decide(signal_direction="short", own_side="short", allow_shorts=True)["action"] == "held_short"


def test_neutral_holds_or_no_signal() -> None:
    assert decide(signal_direction="neutral", own_side="long")["action"] == "held_long"
    assert decide(signal_direction="neutral", own_side="short")["action"] == "held_short"
    assert decide(signal_direction="neutral", own_side=None)["action"] == "no_signal"


# ── flip ─────────────────────────────────────────────────────────────────────
def test_flip_long_to_short_when_allowed() -> None:
    r = decide(signal_direction="short", own_side="long", allow_shorts=True, allow_direction_flip=True)
    assert r["action"] == "flipped_long_to_short" and r["open_side"] == "short" and r["close_own"] is True


def test_flip_short_to_long() -> None:
    r = decide(signal_direction="long", own_side="short", allow_direction_flip=True)
    assert r["action"] == "flipped_short_to_long" and r["open_side"] == "long" and r["close_own"] is True


def test_opposing_short_signal_closes_long_when_shorts_disabled_but_close_on_opposite() -> None:
    r = decide(signal_direction="short", own_side="long", allow_shorts=False, close_on_opposite_signal=True)
    assert r["action"] == "closed_long" and r["open_side"] is None and r["close_own"] is True and r["short_blocked"] is True


def test_opposing_short_signal_holds_when_no_close_and_no_flip() -> None:
    r = decide(signal_direction="short", own_side="long", allow_shorts=False, allow_direction_flip=False, close_on_opposite_signal=False)
    assert r["action"] == "held_long" and r["close_own"] is False


# ── ownership boundary / cross-profile ───────────────────────────────────────
def test_foreign_opposing_position_is_review_not_open() -> None:
    r = decide(signal_direction="short", own_side=None, foreign_opposing=True, allow_shorts=True)
    assert r["action"] == "review_opposing_external_position" and r["open_side"] is None and r["close_own"] is False


def test_hedge_allowed_lets_open_proceed_despite_foreign() -> None:
    r = decide(signal_direction="short", own_side=None, foreign_opposing=True, allow_shorts=True, hedge_allowed=True)
    assert r["action"] == "opened_short"


# ── directional signals ──────────────────────────────────────────────────────
def test_atr_signal_long_on_rising_series() -> None:
    bars = [_bar(i + 1, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(15)]
    sig = T.directional_signal(agent_type="atr_trailing_stop", profile={"atr_trail_type": "unmodified", "atr_factor": 1.0, "atr_period": 5}, bars=bars)
    assert sig.direction == "long"
    assert sig.protective_stop is not None and sig.protective_stop < bars[-1].close


def test_atr_signal_flips_short_with_fresh_flip() -> None:
    bars = [_bar(i + 1, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(10)] + [_bar(11, 109, 109.5, 104, 104.5)]
    sig = T.directional_signal(agent_type="atr_trailing_stop", profile={"atr_trail_type": "unmodified", "atr_factor": 1.0, "atr_period": 5}, bars=bars)
    assert sig.direction == "short"
    assert sig.fresh_flip is True
    assert sig.primary_trigger == "ATR Trailing Stop"


class _HacoPoint:
    def __init__(self, state, flip=None):
        self.state = state
        self.flip = flip


def test_haco_signal_direction(monkeypatch) -> None:
    bars = [_bar(i + 1, 100, 101, 99, 100) for i in range(5)]
    monkeypatch.setattr("macmarket_trader.agent_mode.triggers.compute_haco_states", lambda *a, **k: [_HacoPoint("green", "buy")])
    sig = T.directional_signal(agent_type="haco_direction", profile={"haco_direction_mode": "long_and_short"}, bars=bars)
    assert sig.direction == "long" and sig.fresh_flip is True
    monkeypatch.setattr("macmarket_trader.agent_mode.triggers.compute_haco_states", lambda *a, **k: [_HacoPoint("red")])
    sig2 = T.directional_signal(agent_type="haco_direction", profile={"haco_direction_mode": "long_and_short"}, bars=bars)
    assert sig2.direction == "short"

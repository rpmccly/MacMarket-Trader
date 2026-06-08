"""Phase 11 — Agent Profile trigger eligibility.

Pure, read-only helpers that turn existing indicator outputs (HACO direction,
True Momentum score/trend) into a trade-eligibility verdict for the non-standard
Agent Profile types. This module deliberately:

- never changes recommendation scoring or HACO/Momentum indicator math — it only
  *reads* `compute_haco_states`, `compute_true_momentum`, and
  `compute_true_momentum_score`;
- never opens a paper short — the only verdict that authorizes an open is
  ``LONG_ELIGIBLE``; bearish/short signals resolve to a review-only verdict;
- is side-effect free and exception-safe so a thin/None data series degrades to a
  neutral review instead of crashing an Agent run.

The service applies the verdict *after* deterministic ranking and *before*
turning a candidate into an OPEN_PAPER intent, so sizing/stops/risk-calendar/
recommendation approval still have the final say on every eligible-long candidate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from macmarket_trader.domain.schemas import Bar
from macmarket_trader.indicators.atr_trailing_stop import compute_atr_trailing_stop
from macmarket_trader.indicators.haco import compute_haco_states
from macmarket_trader.indicators.true_momentum import compute_true_momentum
from macmarket_trader.indicators.true_momentum_score import compute_true_momentum_score

ATR_LABEL = "ATR Trailing Stop"


# Verdict kinds.
LONG_ELIGIBLE = "LONG_ELIGIBLE"  # the only kind that authorizes a paper open
SHORT_REVIEW = "SHORT_REVIEW"  # bearish/short bias — review-only, never an order
EXIT_REVIEW = "EXIT_REVIEW"  # caution on an existing long — review-only
NEUTRAL_REVIEW = "NEUTRAL_REVIEW"  # no actionable signal — skipped (no intent)

# Operator-facing primary-trigger labels (never mislabel HACO/Momentum as Standard).
HACO_DIRECTION_LABEL = "HACO Direction"
TRUE_MOMENTUM_LABEL = "True Momentum"
STANDARD_LABEL = "Standard strategy"
HYBRID_LABEL = "Hybrid"

HACO_DIRECTION_MODES = {"long_only", "short_only", "long_and_short"}
TRUE_MOMENTUM_TRIGGER_MODES = {"conservative", "balanced", "aggressive", "review_only"}

# Canonical, operator-facing outcome reasons (see service run output taxonomy).
REASON_PAPER_SHORT_NOT_SUPPORTED = "paper_short_not_supported"
REASON_BEARISH_REVIEW_ONLY = "bearish_review_only"
REASON_REVIEW_ONLY_MODE = "review_only_mode"
REASON_TRIGGER_NOT_MET = "trigger_not_met"

_LONG_TERM_BULLISH = {"bull", "max_bull"}
_LONG_TERM_NEUTRAL_OR_IMPROVING = {"neutral_up", "neutral"}
_LONG_TERM_BEARISH = {"bear", "max_bear", "neutral_down"}


@dataclass(frozen=True)
class TriggerVerdict:
    """Outcome of an agent-type eligibility check for one candidate symbol."""

    kind: str
    primary_trigger: str
    reason: str
    summary: str
    detail: dict[str, object] = field(default_factory=dict)

    @property
    def eligible_long(self) -> bool:
        """True only when a paper open is authorized."""
        return self.kind == LONG_ELIGIBLE

    @property
    def emit_review(self) -> bool:
        """True when the operator should see a review-only (no-order) intent.

        Neutral/no-signal symbols are skipped silently to avoid notification and
        queue noise; bearish/short and exit-caution signals surface as reviews.
        """
        return self.kind in {SHORT_REVIEW, EXIT_REVIEW}


def _ohlc(bars: Sequence[Bar]) -> tuple[list[float], list[float], list[float], list[float]]:
    opens = [float(bar.open) for bar in bars]
    highs = [float(bar.high) for bar in bars]
    lows = [float(bar.low) for bar in bars]
    closes = [float(bar.close) for bar in bars]
    return opens, highs, lows, closes


def evaluate_haco_eligibility(
    bars: Sequence[Bar],
    *,
    mode: str = "long_only",
    timeframe: str = "1D",
) -> TriggerVerdict:
    """HACO direction as the primary trigger/filter.

    green => long; red => short (review-only). ``mode`` controls which directions
    the profile acts on. Short signals are never authorized as paper opens.
    """
    mode = str(mode or "long_only").strip().lower()
    if mode not in HACO_DIRECTION_MODES:
        mode = "long_only"
    if not bars or len(bars) < 2:
        return TriggerVerdict(
            NEUTRAL_REVIEW, HACO_DIRECTION_LABEL, "haco_insufficient_data",
            "Not enough price history for a HACO direction read.",
        )
    try:
        opens, highs, lows, closes = _ohlc(bars)
        states = compute_haco_states(opens, highs, lows, closes)
    except Exception as exc:  # noqa: BLE001 - bad data degrades to a neutral review.
        return TriggerVerdict(
            NEUTRAL_REVIEW, HACO_DIRECTION_LABEL, "haco_unavailable",
            f"HACO direction unavailable ({type(exc).__name__}).",
        )
    if not states:
        return TriggerVerdict(
            NEUTRAL_REVIEW, HACO_DIRECTION_LABEL, "haco_unavailable",
            "HACO direction returned no states.",
        )
    latest = states[-1]
    state = str(getattr(latest, "state", "") or "").lower()
    flip = getattr(latest, "flip", None)
    detail: dict[str, object] = {"haco_state": state, "haco_flip": flip, "haco_mode": mode}
    if state == "green":
        if mode in {"long_only", "long_and_short"}:
            return TriggerVerdict(
                LONG_ELIGIBLE, HACO_DIRECTION_LABEL, "haco_long",
                "HACO direction is long (green); paper long is eligible.",
                detail,
            )
        return TriggerVerdict(
            NEUTRAL_REVIEW, HACO_DIRECTION_LABEL, "haco_long_not_acted",
            "HACO direction is long but this profile is short-only.",
            detail,
        )
    if state == "red":
        # No explicit paper-short lifecycle exists, so a short/red signal never
        # opens an order in ANY mode (incl. short_only / long_and_short). It is
        # surfaced as a review with a clear reason rather than a paper short.
        return TriggerVerdict(
            SHORT_REVIEW, HACO_DIRECTION_LABEL, REASON_PAPER_SHORT_NOT_SUPPORTED,
            "HACO direction is short (red); paper shorting is not supported, so this "
            "is review-only (no paper order).",
            detail,
        )
    return TriggerVerdict(
        NEUTRAL_REVIEW, HACO_DIRECTION_LABEL, REASON_TRIGGER_NOT_MET,
        "HACO direction is not clearly long; no paper long trigger.",
        detail,
    )


def _momentum_states(bars: Sequence[Bar], *, timeframe: str) -> dict[str, object] | None:
    try:
        score_series = compute_true_momentum_score(bars, timeframe=timeframe)
        tm_series = compute_true_momentum(bars, timeframe=timeframe)
    except Exception:  # noqa: BLE001 - bad data degrades to a neutral review.
        return None
    score_points = list(getattr(score_series, "points", []) or [])
    tm_points = list(getattr(tm_series, "points", []) or [])
    if not score_points or not tm_points:
        return None
    score = score_points[-1]
    tm = tm_points[-1]
    total_state = str(getattr(score, "total_state", "") or "").lower()
    trend_score = float(getattr(score, "trend_score", 0.0) or 0.0)
    cross_up = bool(getattr(tm, "cross_up", False))
    cross_down = bool(getattr(tm, "cross_down", False))
    new_bull = bool(getattr(tm, "new_bull_signal", False))
    new_bear = bool(getattr(tm, "new_bear_signal", False))
    trend_direction = int(getattr(tm, "trend_direction", 0) or 0)
    return {
        "total_state": total_state,
        "total_label": str(getattr(score, "total_label", "") or ""),
        "trend_score": trend_score,
        "cross_up": cross_up,
        "cross_down": cross_down,
        "new_bull_signal": new_bull,
        "new_bear_signal": new_bear,
        "trend_direction": trend_direction,
        "long_term_bullish": total_state in _LONG_TERM_BULLISH,
        "long_term_neutral_or_improving": total_state in _LONG_TERM_NEUTRAL_OR_IMPROVING,
        "long_term_bearish": total_state in _LONG_TERM_BEARISH,
        # Short-term bullish/rising or a fresh bullish turn ("trigger").
        "short_term_rising": bool(cross_up or new_bull or trend_direction == 1 or trend_score > 0),
        "short_term_trigger": bool(cross_up or new_bull),
        "short_term_bearish": bool(cross_down or new_bear or trend_direction == -1 or trend_score < 0),
    }


def evaluate_true_momentum_eligibility(
    bars: Sequence[Bar],
    *,
    trigger_mode: str = "review_only",
    timeframe: str = "1D",
) -> TriggerVerdict:
    """True Momentum trigger rules (v1) gated by trigger mode.

    - conservative: long-term AND short-term momentum alignment required.
    - balanced: long-term bias with a short-term trigger/rising read.
    - aggressive: short-term trigger allowed when long-term is neutral/improving.
    - review_only: never opens; always a review.

    Bearish long-term + bearish short-term resolves to a short-bias review.
    """
    trigger_mode = str(trigger_mode or "review_only").strip().lower()
    if trigger_mode not in TRUE_MOMENTUM_TRIGGER_MODES:
        trigger_mode = "review_only"
    if not bars or len(bars) < 2:
        return TriggerVerdict(
            NEUTRAL_REVIEW, TRUE_MOMENTUM_LABEL, "momentum_insufficient_data",
            "Not enough price history for a True Momentum read.",
        )
    states = _momentum_states(bars, timeframe=timeframe)
    if states is None:
        return TriggerVerdict(
            NEUTRAL_REVIEW, TRUE_MOMENTUM_LABEL, "momentum_unavailable",
            "True Momentum signals unavailable for this symbol.",
        )
    detail = {**states, "trigger_mode": trigger_mode}
    long_term_bullish = bool(states["long_term_bullish"])
    long_term_neutral_or_improving = bool(states["long_term_neutral_or_improving"])
    long_term_bearish = bool(states["long_term_bearish"])
    short_term_rising = bool(states["short_term_rising"])
    short_term_trigger = bool(states["short_term_trigger"])
    short_term_bearish = bool(states["short_term_bearish"])

    eligible = False
    if trigger_mode == "conservative":
        eligible = long_term_bullish and short_term_rising
    elif trigger_mode == "balanced":
        eligible = long_term_bullish and (short_term_rising or short_term_trigger)
    elif trigger_mode == "aggressive":
        eligible = (long_term_bullish and (short_term_rising or short_term_trigger)) or (
            long_term_neutral_or_improving and short_term_trigger
        )
    # review_only => eligible stays False.

    if eligible:
        return TriggerVerdict(
            LONG_ELIGIBLE, TRUE_MOMENTUM_LABEL, "momentum_long",
            f"True Momentum {trigger_mode} trigger met "
            f"({states['total_label'] or states['total_state']}, short-term rising); "
            "paper long is eligible.",
            detail,
        )
    if long_term_bearish and short_term_bearish:
        return TriggerVerdict(
            SHORT_REVIEW, TRUE_MOMENTUM_LABEL, REASON_BEARISH_REVIEW_ONLY,
            "True Momentum is bearish on both timeframes; review-only "
            "(paper shorting is not supported).",
            detail,
        )
    if trigger_mode == "review_only":
        return TriggerVerdict(
            EXIT_REVIEW, TRUE_MOMENTUM_LABEL, REASON_REVIEW_ONLY_MODE,
            f"True Momentum review-only mode: {states['total_label'] or states['total_state']} "
            "(no paper open).",
            detail,
        )
    return TriggerVerdict(
        NEUTRAL_REVIEW, TRUE_MOMENTUM_LABEL, REASON_TRIGGER_NOT_MET,
        f"True Momentum {trigger_mode} trigger not met "
        f"({states['total_label'] or states['total_state']}).",
        detail,
    )


def evaluate_true_momentum_exit_caution(
    bars: Sequence[Bar],
    *,
    timeframe: str = "1D",
) -> TriggerVerdict | None:
    """Informational exit/caution read for an OPEN long (never forces a close).

    Returns an ``EXIT_REVIEW`` verdict when short-term momentum flips bearish or
    weakens materially, otherwise None. The existing deterministic stop/target/
    invalidation lifecycle remains the only thing that closes a paper position.
    """
    if not bars or len(bars) < 2:
        return None
    states = _momentum_states(bars, timeframe=timeframe)
    if states is None:
        return None
    weakening = bool(states["short_term_bearish"]) or bool(states["long_term_bearish"])
    if not weakening:
        return None
    return TriggerVerdict(
        EXIT_REVIEW, TRUE_MOMENTUM_LABEL, "momentum_exit_caution",
        "True Momentum weakened/flipped bearish on an open long; review for exit. "
        "Deterministic stops/targets still control any paper close.",
        {**states, "timeframe": timeframe},
    )


def evaluate_agent_eligibility(
    *,
    agent_type: str,
    profile: Mapping[str, object],
    bars: Sequence[Bar],
    candidate: Mapping[str, object],
    timeframe: str = "1D",
) -> TriggerVerdict:
    """Dispatch the eligibility check for a candidate by agent type.

    Standard preserves the existing behavior exactly: a top-ranked candidate is
    eligible long; anything else is a silent skip (NEUTRAL_REVIEW, no review intent).
    HACO/True Momentum use their indicator as the primary trigger. Hybrid requires
    a top-ranked Standard candidate AND the enabled HACO/Momentum filters.
    """
    agent_type = str(agent_type or "standard").strip().lower()
    is_top = str(candidate.get("status") or "") == "top_candidate"
    strategy_label = str(candidate.get("strategy") or STANDARD_LABEL)

    if agent_type == "haco_direction":
        return evaluate_haco_eligibility(
            bars, mode=str(profile.get("haco_direction_mode") or "long_only"), timeframe=timeframe
        )

    if agent_type == "true_momentum":
        return evaluate_true_momentum_eligibility(
            bars,
            trigger_mode=str(profile.get("true_momentum_trigger_mode") or "review_only"),
            timeframe=timeframe,
        )

    if agent_type == "hybrid":
        if not is_top:
            return TriggerVerdict(
                NEUTRAL_REVIEW, HYBRID_LABEL, "hybrid_not_top_candidate",
                "Hybrid agent waits for a top-ranked Standard candidate.",
                {"strategy": strategy_label},
            )
        applied: list[str] = ["Standard strategy"]
        detail: dict[str, object] = {"strategy": strategy_label}
        if bool(profile.get("use_haco_filter")):
            haco = evaluate_haco_eligibility(
                bars, mode=str(profile.get("haco_direction_mode") or "long_only"), timeframe=timeframe
            )
            detail["haco"] = haco.detail
            applied.append("HACO filter")
            if not haco.eligible_long:
                kind = SHORT_REVIEW if haco.kind == SHORT_REVIEW else NEUTRAL_REVIEW
                return TriggerVerdict(
                    kind, HYBRID_LABEL, f"hybrid_haco_block:{haco.reason}",
                    f"Hybrid: {strategy_label} candidate held — HACO filter not long.",
                    detail,
                )
        if bool(profile.get("use_true_momentum_confirmation")):
            momentum = evaluate_true_momentum_eligibility(
                bars,
                trigger_mode=str(profile.get("true_momentum_trigger_mode") or "conservative"),
                timeframe=timeframe,
            )
            detail["true_momentum"] = momentum.detail
            applied.append("True Momentum confirmation")
            if not momentum.eligible_long:
                kind = SHORT_REVIEW if momentum.kind == SHORT_REVIEW else NEUTRAL_REVIEW
                return TriggerVerdict(
                    kind, HYBRID_LABEL, f"hybrid_momentum_block:{momentum.reason}",
                    f"Hybrid: {strategy_label} candidate held — momentum not confirmed.",
                    detail,
                )
        detail["filters_applied"] = applied
        return TriggerVerdict(
            LONG_ELIGIBLE, HYBRID_LABEL, "hybrid_long",
            f"Hybrid: {strategy_label} top candidate confirmed by {', '.join(applied)}.",
            detail,
        )

    # Standard (default): unchanged behavior — only top-ranked candidates open.
    if is_top:
        return TriggerVerdict(
            LONG_ELIGIBLE, STANDARD_LABEL, "ranked_top_candidate",
            f"{strategy_label} top-ranked candidate from deterministic ranking.",
            {"strategy": strategy_label},
        )
    return TriggerVerdict(
        NEUTRAL_REVIEW, STANDARD_LABEL, "not_top_candidate",
        f"{strategy_label} candidate did not rank as a top candidate.",
        {"strategy": strategy_label},
    )


# ── Phase 12 — directional signals + bidirectional decision engine ────────────
@dataclass(frozen=True)
class DirectionalSignal:
    """A directional read (long/short/neutral) from a directional agent's indicator.

    Read-only; the protective_stop is the indicator's own level (ATR trailing stop)
    used by the service to size an indicator-driven open. Whether a short is acted
    on is decided downstream by :func:`decide_bidirectional_action` + profile flags.
    """

    direction: Literal["long", "short", "neutral"]
    fresh_flip: bool
    primary_trigger: str
    reason: str
    summary: str
    protective_stop: float | None = None
    detail: dict[str, object] = field(default_factory=dict)


def evaluate_atr_signal(
    bars: Sequence[Bar],
    *,
    profile: Mapping[str, object] | None = None,
    timeframe: str = "1D",
) -> DirectionalSignal:
    """ATR Trailing Stop direction + fresh-flip + trailing-stop level (read-only)."""
    cfg = {
        "trail_type": (profile or {}).get("atr_trail_type", "modified"),
        "atr_period": (profile or {}).get("atr_period", 9),
        "atr_factor": (profile or {}).get("atr_factor", 2.9),
        "first_trade": (profile or {}).get("atr_first_trade", "long"),
        "average_type": (profile or {}).get("atr_average_type", "wilders"),
    }
    try:
        series = compute_atr_trailing_stop(bars, config=cfg)
    except Exception as exc:  # noqa: BLE001 - degrade to neutral on bad data.
        return DirectionalSignal("neutral", False, ATR_LABEL, "atr_unavailable", f"ATR unavailable ({type(exc).__name__}).")
    point = series.latest
    if point is None:
        return DirectionalSignal("neutral", False, ATR_LABEL, "atr_insufficient_data", "Not enough bars for an ATR read.")
    direction: Literal["long", "short", "neutral"] = point.state if point.state in {"long", "short"} else "neutral"
    fresh = bool(point.buy_signal or point.sell_signal)
    reason = f"atr_{direction}" + ("_flip" if fresh else "")
    summary = (
        f"ATR Trailing Stop is {direction.upper()}"
        + (" (fresh flip)" if fresh else "")
        + f"; trailing stop {point.trailing_stop}."
    )
    return DirectionalSignal(
        direction, fresh, ATR_LABEL, reason, summary,
        protective_stop=point.trailing_stop,
        detail={
            "state": point.state, "trailing_stop": point.trailing_stop,
            "stop_distance": point.stop_distance, "stop_distance_pct": point.stop_distance_pct,
            "bars_since_flip": point.bars_since_flip, "buy_signal": point.buy_signal,
            "sell_signal": point.sell_signal, "atr_timeframe": timeframe,
        },
    )


def directional_signal(
    *,
    agent_type: str,
    profile: Mapping[str, object],
    bars: Sequence[Bar],
    candidate: Mapping[str, object] | None = None,
    timeframe: str = "1D",
) -> DirectionalSignal:
    """Map a directional agent's indicator to a long/short/neutral signal.

    Reuses the existing HACO/True Momentum verdict logic (no new indicator math)
    and the ATR engine. Hybrid uses ATR as an optional directional confirmation.
    """
    agent_type = str(agent_type or "standard").strip().lower()
    candidate = candidate or {}

    if agent_type == "atr_trailing_stop":
        return evaluate_atr_signal(bars, profile=profile, timeframe=timeframe)

    if agent_type == "haco_direction":
        verdict = evaluate_haco_eligibility(
            bars, mode=str(profile.get("haco_direction_mode") or "long_only"), timeframe=timeframe
        )
        state = str(verdict.detail.get("haco_state") or "")
        direction = "long" if state == "green" else "short" if state == "red" else "neutral"
        fresh = str(verdict.detail.get("haco_flip") or "") in {"buy", "sell"}
        return DirectionalSignal(direction, fresh, HACO_DIRECTION_LABEL, verdict.reason, verdict.summary, detail=verdict.detail)

    if agent_type == "true_momentum":
        verdict = evaluate_true_momentum_eligibility(
            bars, trigger_mode=str(profile.get("true_momentum_trigger_mode") or "review_only"), timeframe=timeframe
        )
        if verdict.kind == LONG_ELIGIBLE:
            direction = "long"
        elif verdict.kind == SHORT_REVIEW:
            direction = "short"
        else:
            direction = "neutral"
        fresh = bool(verdict.detail.get("new_bull_signal") or verdict.detail.get("new_bear_signal"))
        return DirectionalSignal(direction, fresh, TRUE_MOMENTUM_LABEL, verdict.reason, verdict.summary, detail=verdict.detail)

    if agent_type == "hybrid":
        verdict = evaluate_agent_eligibility(agent_type="hybrid", profile=profile, bars=bars, candidate=candidate, timeframe=timeframe)
        direction = "long" if verdict.kind == LONG_ELIGIBLE else "short" if verdict.kind == SHORT_REVIEW else "neutral"
        if direction == "long" and bool(profile.get("use_atr_filter")):
            atr = evaluate_atr_signal(bars, profile=profile, timeframe=timeframe)
            if atr.direction != "long":
                return DirectionalSignal("neutral", False, HYBRID_LABEL, "hybrid_atr_filter_block", "Hybrid: ATR filter not long.", detail=verdict.detail)
        return DirectionalSignal(direction, False, HYBRID_LABEL, verdict.reason, verdict.summary, detail=verdict.detail)

    return DirectionalSignal("neutral", False, STANDARD_LABEL, "not_directional", "Standard agents are long-only via ranking.")


def decide_bidirectional_action(
    *,
    signal_direction: str,
    fresh_flip: bool,
    own_side: str | None,
    foreign_opposing: bool,
    allow_shorts: bool,
    allow_direction_flip: bool,
    close_opposite_before_open: bool,
    close_on_opposite_signal: bool,
    hedge_allowed: bool,
) -> dict[str, object]:
    """Pure decision engine: (own position, signal, profile flags) → intended action.

    ``own_side`` is THIS profile's own open side (long/short/None) — execution is
    profile-owned; a profile never closes manual/foreign positions. ``foreign_opposing``
    flags an opposing position owned by another profile or opened manually.

    Returns {action, open_side, close_own, short_blocked}. Risk/sizing gates may later
    downgrade an ``opened_*``/``flipped_*`` to blocked_by_risk/blocked_by_sizing.
    """
    direction = str(signal_direction or "neutral").lower()

    if direction == "neutral":
        if own_side == "long":
            return {"action": "held_long", "open_side": None, "close_own": False, "short_blocked": False}
        if own_side == "short":
            return {"action": "held_short", "open_side": None, "close_own": False, "short_blocked": False}
        return {"action": "no_signal", "open_side": None, "close_own": False, "short_blocked": False}

    # Cross-profile/manual opposing exposure: never touch the foreign position; do not
    # add opposing exposure unless an explicit hedge is allowed.
    if foreign_opposing and own_side is None and not hedge_allowed:
        return {"action": "review_opposing_external_position", "open_side": None, "close_own": False, "short_blocked": False}

    if own_side is None:
        if direction == "long":
            return {"action": "opened_long", "open_side": "long", "close_own": False, "short_blocked": False}
        if allow_shorts:
            return {"action": "opened_short", "open_side": "short", "close_own": False, "short_blocked": False}
        return {"action": "blocked_by_short_not_allowed", "open_side": None, "close_own": False, "short_blocked": True}

    if own_side == direction:
        return {"action": f"held_{direction}", "open_side": None, "close_own": False, "short_blocked": False}

    # own_side opposes the signal → flip or close-on-opposite.
    if direction == "short":  # own long, signal short
        if allow_shorts and allow_direction_flip:
            return {"action": "flipped_long_to_short", "open_side": "short", "close_own": True, "short_blocked": False}
        if close_on_opposite_signal:
            return {"action": "closed_long", "open_side": None, "close_own": True, "short_blocked": not allow_shorts}
        return {"action": "held_long", "open_side": None, "close_own": False, "short_blocked": False}
    # own short, signal long
    if allow_direction_flip:
        return {"action": "flipped_short_to_long", "open_side": "long", "close_own": True, "short_blocked": False}
    if close_on_opposite_signal:
        return {"action": "closed_short", "open_side": None, "close_own": True, "short_blocked": False}
    return {"action": "held_short", "open_side": None, "close_own": False, "short_blocked": False}

"""Bounded Momentum Intelligence ranking contribution (Phase B1).

This module is **pure**. It translates a deterministic Momentum chart payload
into a capped, audited :class:`MomentumRankingContribution`. It never:

- approves or rejects a trade,
- sizes a trade,
- routes a trade,
- changes paper-order behavior,
- changes recommendation approval behavior,
- creates a strategy family.

It only attaches an explanation/contribution that the upstream ranking
engine may apply (active mode) or surface as shadow context (shadow mode).
The ``off`` mode short-circuits: no contribution is computed.

See ``docs/momentum-intelligence-layer.md`` for the full design.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from macmarket_trader.domain.schemas import (
    MomentumChartPayload,
    MomentumRankingContribution,
    MomentumScoreSnapshot,
)

Mode = Literal["off", "shadow", "active"]
_VALID_MODES: tuple[Mode, ...] = ("off", "shadow", "active")


def resolve_momentum_ranking_mode(value: str | None, *, default: Mode = "shadow") -> Mode:
    """Return a known mode, defaulting safely on unknown input.

    Unknown values fall back to the default rather than raising — Phase B1's
    fail-open guarantee means a malformed env var must never crash startup.
    """
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in _VALID_MODES:
        return normalized  # type: ignore[return-value]
    return default


@dataclass(frozen=True)
class MomentumRankingConfig:
    """Configuration for the bounded ranking contribution.

    All bounds are absolute caps applied per-candidate. ``parity_required_for_active``
    is intentionally False at Phase B1 — it should flip to True once
    Thinkorswim parity fixtures land and have been reviewed (see
    ``tests/fixtures/thinkorswim_momentum/``).
    """

    mode: Mode = "shadow"
    max_momentum_alignment_bonus: float = 10.0
    max_trend_alignment_bonus: float = 8.0
    max_hilo_confirmation_bonus: float = 5.0
    max_reversal_warning_penalty: float = 12.0
    max_total_contribution: float = 20.0
    parity_required_for_active: bool = False
    require_score_freshness: bool = True
    fail_open: bool = True
    # Internal floor for the negative side of the cap (no-trade warning + reversal).
    min_total_contribution: float = -12.0
    # Score-units conversion factor: the Momentum Score is in [-130, +130]
    # but the ranking engine's score is in [0, 1]. Phase B1 converts the
    # bounded contribution into the same ranking-score scale by dividing by
    # 100. Tests cover this so the cap stays operator-visible.
    ranking_score_scale: float = 100.0


def momentum_ranking_config_from_settings(settings: Any) -> MomentumRankingConfig:
    """Build a MomentumRankingConfig from the application settings object."""
    raw_mode = getattr(settings, "momentum_ranking_mode", "shadow")
    return MomentumRankingConfig(mode=resolve_momentum_ranking_mode(raw_mode))


# ── Direction inference ────────────────────────────────────────────────────


_BULL_STATES = {"max_bull", "bull"}
_BEAR_STATES = {"max_bear", "bear"}


def _normalize_direction(value: Any) -> Literal["long", "short", "unknown"]:
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if text in {"long", "bull", "bullish", "buy"}:
        return "long"
    if text in {"short", "bear", "bearish", "sell"}:
        return "short"
    return "unknown"


def _infer_direction(
    context: Mapping[str, Any] | None,
) -> tuple[Literal["long", "short", "unknown"], str | None]:
    """Infer the recommendation's intended direction.

    Returns (direction, reason_code_for_unknown_or_None).
    """
    if not context:
        return "unknown", "direction_unknown"

    explicit = _normalize_direction(context.get("direction") or context.get("side"))
    if explicit != "unknown":
        return explicit, None

    strategy = str(context.get("strategy") or "").strip().lower()
    if "fade" in strategy:
        # Failed-event fades flip direction relative to the catalyst — at the
        # ranking layer we don't have catalyst polarity, so stay conservative.
        return "unknown", "direction_unknown"
    if "mean reversion" in strategy:
        return "unknown", "direction_unknown"

    # Recent-bar trend hint: ranking-engine candidates expose a 5-bar net change
    # via context["recent_trend"] (≥ 0 → long bias, < 0 → short bias). Used only
    # for momentum-aligned strategies, never for fades.
    recent = context.get("recent_trend")
    if recent is not None:
        try:
            recent_float = float(recent)
        except (TypeError, ValueError):
            recent_float = None
        else:
            if "continuation" in strategy or "pullback" in strategy:
                return ("long" if recent_float >= 0.0 else "short"), None

    return "unknown", "direction_unknown"


# ── Snapshot extraction ────────────────────────────────────────────────────


@dataclass
class _SnapshotView:
    state: str
    label: str
    total_score: int | None
    trend_score: float | None
    momo_score: float | None
    hilo_thrust: int | None
    hilo_score: int | None
    reversal_warning: bool
    pullback_signal: bool
    no_trade_warning: bool
    parity_status: str | None
    higher_timeframe_source: str | None
    notes: list[str] = field(default_factory=list)


def _extract_snapshot(
    payload_or_snapshot: MomentumChartPayload | MomentumScoreSnapshot | Mapping[str, Any] | None,
) -> _SnapshotView | None:
    """Best-effort extraction of the score state regardless of input shape."""
    if payload_or_snapshot is None:
        return None

    # Accept either a MomentumChartPayload, a MomentumScoreSnapshot, or a
    # plain dict that mirrors the payload shape.
    if isinstance(payload_or_snapshot, MomentumChartPayload):
        snap = payload_or_snapshot.latest_snapshot or (
            payload_or_snapshot.explanation.snapshot if payload_or_snapshot.explanation else None
        )
        if snap is None:
            return None
        explanation = payload_or_snapshot.explanation
        return _SnapshotView(
            state=str(snap.total_state),
            label=str(snap.total_label),
            total_score=int(snap.total_score),
            trend_score=float(snap.trend_score),
            momo_score=float(snap.momo_score),
            hilo_thrust=int(snap.hilo_thrust),
            hilo_score=int(snap.hilo_score),
            reversal_warning=bool(explanation.reversal_warning) if explanation else False,
            pullback_signal=bool(explanation.pullback_signal) if explanation else False,
            no_trade_warning=bool(explanation.no_trade_warning) if explanation else False,
            parity_status=payload_or_snapshot.parity_status,
            higher_timeframe_source=payload_or_snapshot.higher_timeframe_source,
            notes=list(payload_or_snapshot.calculation_notes),
        )

    if isinstance(payload_or_snapshot, MomentumScoreSnapshot):
        return _SnapshotView(
            state=str(payload_or_snapshot.total_state),
            label=str(payload_or_snapshot.total_label),
            total_score=int(payload_or_snapshot.total_score),
            trend_score=float(payload_or_snapshot.trend_score),
            momo_score=float(payload_or_snapshot.momo_score),
            hilo_thrust=int(payload_or_snapshot.hilo_thrust),
            hilo_score=int(payload_or_snapshot.hilo_score),
            reversal_warning=False,
            pullback_signal=False,
            no_trade_warning=False,
            parity_status=None,
            higher_timeframe_source=None,
            notes=[],
        )

    if isinstance(payload_or_snapshot, Mapping):
        explanation = payload_or_snapshot.get("explanation") or {}
        snap = (
            payload_or_snapshot.get("latest_snapshot")
            or (explanation.get("snapshot") if isinstance(explanation, Mapping) else None)
        )
        if not isinstance(snap, Mapping):
            return None
        try:
            return _SnapshotView(
                state=str(snap.get("total_state") or "neutral"),
                label=str(snap.get("total_label") or ""),
                total_score=_int_or_none(snap.get("total_score")),
                trend_score=_float_or_none(snap.get("trend_score")),
                momo_score=_float_or_none(snap.get("momo_score")),
                hilo_thrust=_int_or_none(snap.get("hilo_thrust")),
                hilo_score=_int_or_none(snap.get("hilo_score")),
                reversal_warning=bool(explanation.get("reversal_warning")) if isinstance(explanation, Mapping) else False,
                pullback_signal=bool(explanation.get("pullback_signal")) if isinstance(explanation, Mapping) else False,
                no_trade_warning=bool(explanation.get("no_trade_warning")) if isinstance(explanation, Mapping) else False,
                parity_status=str(payload_or_snapshot.get("parity_status")) if payload_or_snapshot.get("parity_status") else None,
                higher_timeframe_source=str(payload_or_snapshot.get("higher_timeframe_source")) if payload_or_snapshot.get("higher_timeframe_source") else None,
                notes=list(payload_or_snapshot.get("calculation_notes") or []),
            )
        except (TypeError, ValueError):
            return None

    return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        flt = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(flt) or math.isinf(flt):
        return None
    return flt


def _sanitize(value: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value


def _clamp(value: float, low: float, high: float) -> float:
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(low, min(high, value))


# ── Public scoring entry point ─────────────────────────────────────────────


def build_momentum_ranking_contribution(
    payload_or_snapshot: MomentumChartPayload | MomentumScoreSnapshot | Mapping[str, Any] | None,
    recommendation_context: Mapping[str, Any] | None,
    config: MomentumRankingConfig,
) -> MomentumRankingContribution:
    """Build a bounded ranking contribution from a Momentum payload + context.

    Pure function; never raises on bad input. Always returns a
    :class:`MomentumRankingContribution`. The contribution is bounded to
    ``[config.min_total_contribution, config.max_total_contribution]``.
    """
    mode: Mode = config.mode if config.mode in _VALID_MODES else "off"

    if mode == "off":
        return MomentumRankingContribution(mode="off", enabled=False, applied=False)

    reason_codes: list[str] = []
    notes: list[str] = []

    snapshot = _extract_snapshot(payload_or_snapshot)
    if snapshot is None:
        reason_codes.append("momentum_payload_unavailable")
        return MomentumRankingContribution(
            mode=mode,
            enabled=True,
            applied=False,
            total_contribution=0.0,
            shadow_contribution=0.0,
            reason_codes=reason_codes,
        )

    notes.extend(snapshot.notes)

    direction, dir_reason = _infer_direction(recommendation_context)
    if dir_reason:
        reason_codes.append(dir_reason)

    # Component computations
    momentum_alignment = _momentum_alignment(snapshot, direction, config)
    trend_alignment = _trend_alignment(snapshot, direction, config)
    hilo_confirmation = _hilo_confirmation(snapshot, direction, config)
    reversal_penalty = _reversal_penalty(snapshot, config)

    if snapshot.no_trade_warning:
        reason_codes.append("momentum_no_trade_warning")
        # No-trade warning suppresses positive contribution but does not hard-reject.
        momentum_alignment = min(0.0, momentum_alignment)
        trend_alignment = min(0.0, trend_alignment)
        hilo_confirmation = min(0.0, hilo_confirmation)

    if snapshot.reversal_warning:
        reason_codes.append("momentum_reversal_warning")

    if snapshot.pullback_signal:
        reason_codes.append("momentum_pullback_signal")

    if snapshot.parity_status == "pending_thinkorswim_fixture_validation":
        reason_codes.append("thinkorswim_parity_pending")

    if snapshot.higher_timeframe_source == "derived_from_chart_bars":
        reason_codes.append("derived_higher_timeframe")

    raw_total = (
        _sanitize(momentum_alignment)
        + _sanitize(trend_alignment)
        + _sanitize(hilo_confirmation)
        + _sanitize(reversal_penalty)
    )
    bounded_total = _clamp(raw_total, config.min_total_contribution, config.max_total_contribution)

    # parity_required_for_active gate — when set True (future), refuse to
    # apply in active mode while parity remains pending.
    can_apply_active = mode == "active"
    if mode == "active" and config.parity_required_for_active:
        if snapshot.parity_status != "validated_against_thinkorswim_fixture":
            can_apply_active = False
            reason_codes.append("active_blocked_parity_required")

    # Active-mode requires direction confidence; in unknown mode, fall back to
    # zero applied contribution but keep the breakdown for audit.
    if direction == "unknown":
        can_apply_active = False

    applied_total = bounded_total if (mode == "active" and can_apply_active) else 0.0

    return MomentumRankingContribution(
        mode=mode,
        enabled=True,
        applied=bool(applied_total != 0.0),
        total_contribution=round(applied_total, 4),
        shadow_contribution=round(bounded_total, 4),
        momentum_alignment_score=round(_sanitize(momentum_alignment), 4),
        trend_alignment_score=round(_sanitize(trend_alignment), 4),
        hilo_confirmation_bonus=round(_sanitize(hilo_confirmation), 4),
        reversal_warning_penalty=round(_sanitize(reversal_penalty), 4),
        no_trade_warning=snapshot.no_trade_warning,
        pullback_signal=snapshot.pullback_signal,
        reversal_warning=snapshot.reversal_warning,
        parity_status=snapshot.parity_status,
        higher_timeframe_source=snapshot.higher_timeframe_source,
        total_score=snapshot.total_score,
        total_label=snapshot.label or None,
        trend_score=snapshot.trend_score,
        momo_score=snapshot.momo_score,
        inferred_direction=direction,
        calculation_notes=notes,
        reason_codes=reason_codes,
    )


# ── Component scoring ──────────────────────────────────────────────────────


def _momentum_alignment(
    snapshot: _SnapshotView,
    direction: Literal["long", "short", "unknown"],
    config: MomentumRankingConfig,
) -> float:
    """0..+max for aligned bull/bear, 0 otherwise.

    Phase B1 stays non-negative for direction-aligned cases; opposed
    directional context flows through the reversal penalty (and no-trade
    suppression) rather than a negative alignment component.
    """
    if direction == "unknown":
        return 0.0

    state = snapshot.state
    if direction == "long":
        if state == "max_bull":
            return config.max_momentum_alignment_bonus
        if state == "bull":
            return config.max_momentum_alignment_bonus * 0.7
        if state == "neutral_up":
            return config.max_momentum_alignment_bonus * 0.3
        return 0.0
    # direction == "short"
    if state == "max_bear":
        return config.max_momentum_alignment_bonus
    if state == "bear":
        return config.max_momentum_alignment_bonus * 0.7
    if state == "neutral_down":
        return config.max_momentum_alignment_bonus * 0.3
    return 0.0


def _trend_alignment(
    snapshot: _SnapshotView,
    direction: Literal["long", "short", "unknown"],
    config: MomentumRankingConfig,
) -> float:
    if direction == "unknown" or snapshot.trend_score is None:
        return 0.0
    trend = float(snapshot.trend_score)
    # Trend score range is roughly [-130, +130]; we cap at ±100 for
    # normalization. Aligned direction uses the magnitude scaled by trend
    # sign agreement.
    aligned = (direction == "long" and trend > 0.0) or (direction == "short" and trend < 0.0)
    if not aligned:
        return 0.0
    magnitude = min(abs(trend), 100.0) / 100.0
    return round(config.max_trend_alignment_bonus * magnitude, 4)


def _hilo_confirmation(
    snapshot: _SnapshotView,
    direction: Literal["long", "short", "unknown"],
    config: MomentumRankingConfig,
) -> float:
    if direction == "unknown" or snapshot.hilo_score is None:
        return 0.0
    hilo = float(snapshot.hilo_score)
    aligned = (direction == "long" and hilo > 0.0) or (direction == "short" and hilo < 0.0)
    if not aligned:
        return 0.0
    # HiLo composite range is [-20, +20]; scale into [0, max_hilo].
    magnitude = min(abs(hilo), 20.0) / 20.0
    return round(config.max_hilo_confirmation_bonus * magnitude, 4)


def _reversal_penalty(snapshot: _SnapshotView, config: MomentumRankingConfig) -> float:
    """Negative-only penalty for active reversal warnings.

    The full configured cap fires on an explicit reversal warning. Otherwise
    returns 0 (no penalty in this Phase B1 surface).
    """
    if snapshot.reversal_warning:
        return -float(config.max_reversal_warning_penalty)
    return 0.0


__all__ = [
    "MomentumRankingConfig",
    "build_momentum_ranking_contribution",
    "momentum_ranking_config_from_settings",
    "resolve_momentum_ranking_mode",
]

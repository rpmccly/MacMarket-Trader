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
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from macmarket_trader.domain.schemas import (
    MomentumChartPayload,
    MomentumRankingContribution,
    MomentumRankingStatus,
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

    Phase B6 splits ``mode`` (the **effective** mode, after the safety
    guard) from ``requested_mode`` (the raw configured request). When
    ``requested_mode == "active"`` but ``active_allowed`` is False, the
    safety guard forces ``mode == "shadow"`` and the contribution
    surfaces ``active_mode_blocked_by_safety_guard``.

    All bounds are absolute caps applied per-candidate.
    ``parity_required_for_active`` is intentionally False at Phase B1 —
    it should flip to True once Thinkorswim parity fixtures land and
    have been reviewed (see ``tests/fixtures/thinkorswim_momentum/``).
    """

    mode: Mode = "shadow"
    requested_mode: Mode | None = None
    active_allowed: bool = False
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
    # Phase B6.1 — operator-tunable scale applied on top of the
    # ``ranking_score_scale`` division. Default 0.35 keeps Max Bull
    # candidates from saturating to 1.000. Always finite and clamped to
    # ``[0.0, 1.0]``.
    active_delta_scale: float = 0.35
    # Phase B6.1 — set to True when the raw env value could not be parsed
    # or was out of range. The status payload surfaces this via the
    # ``momentum_active_delta_scale_invalid`` reason code.
    active_delta_scale_invalid: bool = False


_TRUTHY_STRINGS: frozenset[str] = frozenset({"true", "1", "yes", "y", "on"})

# Phase B6.1 — default operator scale applied to the bounded Momentum
# ranking contribution when active mode is allowed. Kept as a module
# constant so tests and the docs reference the same value.
DEFAULT_ACTIVE_DELTA_SCALE: float = 0.35


def _resolve_active_delta_scale(value: Any) -> tuple[float, bool]:
    """Parse the operator-tunable active-delta scale.

    Returns ``(scale, invalid)``. ``invalid=True`` indicates the raw
    value could not be parsed as a float or was outside ``[0.0, 1.0]``.
    On invalid input the scale falls back to
    :data:`DEFAULT_ACTIVE_DELTA_SCALE` and the status layer adds the
    ``momentum_active_delta_scale_invalid`` reason code.
    """
    if value is None:
        return DEFAULT_ACTIVE_DELTA_SCALE, False
    if isinstance(value, bool):
        # bool is a subclass of int; reject because operators almost
        # certainly didn't mean "True"/"False" for a scale.
        return DEFAULT_ACTIVE_DELTA_SCALE, True
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return DEFAULT_ACTIVE_DELTA_SCALE, False
        try:
            parsed = float(text)
        except ValueError:
            return DEFAULT_ACTIVE_DELTA_SCALE, True
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return DEFAULT_ACTIVE_DELTA_SCALE, True
    if not math.isfinite(parsed):
        return DEFAULT_ACTIVE_DELTA_SCALE, True
    if parsed < 0.0 or parsed > 1.0:
        return DEFAULT_ACTIVE_DELTA_SCALE, True
    return parsed, False


def _resolve_active_allowed(value: Any) -> bool:
    """Truthy-tolerant resolution for the active-mode safety guard.

    Accepts bool ``True``, the integer ``1``, and the strings ``"true"``,
    ``"1"``, ``"yes"`` (case-insensitive). Anything else, including
    ``None`` and invalid strings, resolves to ``False``.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in _TRUTHY_STRINGS


def resolve_effective_momentum_ranking_mode(
    requested_mode: Mode | str | None,
    *,
    active_allowed: bool,
) -> tuple[Mode, Mode, bool]:
    """Resolve the effective Momentum ranking mode given the safety guard.

    Returns ``(effective_mode, requested_mode_canonical, blocked)``.
    ``blocked`` is True when active mode was requested but the safety
    guard refused to honor it.
    """
    requested = resolve_momentum_ranking_mode(requested_mode)
    if requested == "active" and not active_allowed:
        return "shadow", requested, True
    return requested, requested, False


def momentum_ranking_config_from_settings(settings: Any) -> MomentumRankingConfig:
    """Build a MomentumRankingConfig from the application settings object.

    Reads ``momentum_ranking_mode`` (Phase B1), the Phase B6 safety guard
    ``momentum_active_ranking_allowed``, and the Phase B6.1 operator
    delta-scale ``momentum_active_delta_scale``. When active is requested
    but the guard is not set, ``mode`` falls back to ``shadow`` while
    ``requested_mode`` preserves the original request for status reporting.
    """
    raw_mode = getattr(settings, "momentum_ranking_mode", "shadow")
    raw_allowed = getattr(settings, "momentum_active_ranking_allowed", False)
    raw_scale = getattr(settings, "momentum_active_delta_scale", None)
    active_allowed = _resolve_active_allowed(raw_allowed)
    active_delta_scale, scale_invalid = _resolve_active_delta_scale(raw_scale)
    effective, requested, _blocked = resolve_effective_momentum_ranking_mode(
        raw_mode, active_allowed=active_allowed
    )
    return MomentumRankingConfig(
        mode=effective,
        requested_mode=requested,
        active_allowed=active_allowed,
        active_delta_scale=active_delta_scale,
        active_delta_scale_invalid=scale_invalid,
    )


# ── Direction inference ────────────────────────────────────────────────────


_BULL_STATES = {"max_bull", "bull"}
_BEAR_STATES = {"max_bear", "bear"}

# Phase B4.2 — registry directional_profile values resolve to a canonical
# direction. Only ``bullish`` and ``bearish`` produce a directional inference;
# all other profiles (``neutral``, ``carry``, ``volatility``) explicitly stay
# unknown so the bounded contribution is never applied for ambiguous setups.
_PROFILE_TO_DIRECTION: dict[str, Literal["long", "short", "unknown"]] = {
    "bullish": "long",
    "bearish": "short",
    "long": "long",
    "short": "short",
    "neutral": "unknown",
    "carry": "unknown",
    "volatility": "unknown",
}

# Phase B4.2 — strategy_id fallbacks for callers that don't resolve the
# registry. Keep this list conservative; never infer bearish from a label
# fallback (the registry's bearish profile already covers the explicit case).
_STRATEGY_ID_LONG_BIAS: frozenset[str] = frozenset(
    {
        "event_continuation",
        "breakout_prior_day_high",
        "pullback_trend_continuation",
    }
)

# Strategy IDs that should explicitly remain unknown even when no registry
# directional_profile is available. Keeps fades / mean-reversion safe.
_STRATEGY_ID_UNKNOWN: frozenset[str] = frozenset({"mean_reversion"})

# Label fallback: normalized canonical labels that signal long bias when
# neither explicit metadata nor registry directional_profile is provided.
_LABEL_LONG_BIAS: tuple[str, ...] = (
    "event continuation",
    "breakout prior day high",
    "prior day high breakout",
    "pullback trend continuation",
)

# Label tokens that keep direction unknown regardless of other signals.
_LABEL_UNKNOWN_TOKENS: tuple[str, ...] = ("fade", "mean reversion")


def _normalize_direction(value: Any) -> Literal["long", "short", "unknown"]:
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if text in {"long", "bull", "bullish", "buy"}:
        return "long"
    if text in {"short", "bear", "bearish", "sell"}:
        return "short"
    return "unknown"


def _normalize_label(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    # Replace any non-alphanumeric with a single space, collapse runs.
    cleaned = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _direction_from_profile(value: Any) -> Literal["long", "short", "unknown"]:
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if not text:
        return "unknown"
    return _PROFILE_TO_DIRECTION.get(text, "unknown")


def _infer_direction(
    context: Mapping[str, Any] | None,
) -> tuple[Literal["long", "short", "unknown"], str | None]:
    """Infer the recommendation's intended direction.

    Priority (Phase B4.2):
      1. Explicit candidate metadata: ``direction`` / ``side`` / ``bias``.
      2. Strategy registry metadata: ``directional_profile`` resolved by the
         caller from :mod:`macmarket_trader.strategy_registry`.
      3. Known strategy IDs / labels — conservative long-bias mapping only.
      4. Unknown.

    Returns ``(direction, reason_code_or_None)``. The reason code is
    appended verbatim to ``MomentumRankingContribution.reason_codes`` by
    the caller.
    """
    if not context:
        return "unknown", "direction_unknown"

    # 1. Explicit candidate-side metadata wins.
    for key in ("direction", "side", "bias"):
        explicit = _normalize_direction(context.get(key))
        if explicit != "unknown":
            return explicit, "direction_from_candidate_metadata"

    # 2. Registry directional_profile (resolved by the caller).
    profile_raw = context.get("directional_profile")
    if isinstance(profile_raw, str) and profile_raw.strip():
        profile_direction = _direction_from_profile(profile_raw)
        if profile_direction != "unknown":
            return profile_direction, "direction_from_strategy_metadata"
        # If the registry says neutral/carry/volatility, the registry has
        # spoken — do not fall through to label inference for that profile.
        return "unknown", "direction_unknown"

    # 3a. Strategy ID fallback for callers that didn't resolve the registry.
    strategy_id = str(context.get("strategy_id") or "").strip().lower()
    if strategy_id:
        if strategy_id in _STRATEGY_ID_UNKNOWN:
            return "unknown", "direction_unknown"
        if strategy_id in _STRATEGY_ID_LONG_BIAS:
            return "long", "bullish_strategy_direction_inferred"

    # 3b. Strategy label fallback.
    strategy_label = _normalize_label(context.get("strategy"))
    if strategy_label:
        for token in _LABEL_UNKNOWN_TOKENS:
            if token in strategy_label:
                return "unknown", "direction_unknown"
        for canonical in _LABEL_LONG_BIAS:
            if canonical in strategy_label:
                return "long", "bullish_strategy_direction_inferred"

        # Backward-compatibility: legacy callers may still pass a
        # ``recent_trend`` hint together with a continuation/pullback
        # label that did not match the canonical list above. Use it only
        # when the label is clearly long-biased.
        recent = context.get("recent_trend")
        if recent is not None and ("continuation" in strategy_label or "pullback" in strategy_label):
            try:
                recent_float = float(recent)
            except (TypeError, ValueError):
                recent_float = None
            else:
                direction: Literal["long", "short"] = "long" if recent_float >= 0.0 else "short"
                return direction, "bullish_strategy_direction_inferred"

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
    # Phase B6 — the contribution shape is driven by the **effective** mode
    # (``config.mode``). If active was requested but blocked by the safety
    # guard, ``config.mode`` is already shadow and ``config.requested_mode``
    # is active. Surface ``active_mode_blocked_by_safety_guard`` so the
    # operator UI can render the blocked-active framing.
    safety_blocked = (
        getattr(config, "requested_mode", None) == "active"
        and mode != "active"
        and not getattr(config, "active_allowed", False)
    )

    if mode == "off":
        out = MomentumRankingContribution(mode="off", enabled=False, applied=False)
        if safety_blocked:  # pragma: no cover - off with blocked active is a contradiction
            out = out.model_copy(update={"reason_codes": ["active_mode_blocked_by_safety_guard"]})
        return out

    reason_codes: list[str] = []
    if safety_blocked:
        reason_codes.append("active_mode_blocked_by_safety_guard")
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

    # Phase B6.1 — surface the operator delta scale and the actual
    # ranking-score delta separately from the raw score-unit
    # contribution. Frontend renders ``raw_total_contribution`` (still in
    # ±20 score units) alongside ``applied_score_delta`` (in [0, 1]
    # ranking-score units) so operators can see the scale in effect.
    raw_total_contribution = bounded_total
    ranking_scale = max(getattr(config, "ranking_score_scale", 100.0) or 100.0, 1.0)
    active_delta_scale = float(getattr(config, "active_delta_scale", DEFAULT_ACTIVE_DELTA_SCALE))
    if not math.isfinite(active_delta_scale) or active_delta_scale < 0.0 or active_delta_scale > 1.0:
        active_delta_scale = DEFAULT_ACTIVE_DELTA_SCALE
    if mode == "active" and can_apply_active:
        applied_score_delta = round(applied_total / ranking_scale * active_delta_scale, 6)
    else:
        applied_score_delta = 0.0

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
        active_delta_scale=active_delta_scale,
        raw_total_contribution=round(raw_total_contribution, 4),
        applied_score_delta=applied_score_delta,
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


# ── Phase B3 status builder ────────────────────────────────────────────────


_DEFAULT_PARITY_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "thinkorswim_momentum"
    / "manifest.json"
)


_GUARDRAILS = (
    "Shadow mode computes contribution but does not alter final ranking.",
    "Active mode applies a bounded contribution only.",
    "This does not approve, reject, size, or route trades.",
)


def build_momentum_ranking_status(
    settings: Any,
    *,
    manifest_path: Path | None = None,
    config: MomentumRankingConfig | None = None,
) -> MomentumRankingStatus:
    """Build the operator-facing Momentum ranking status payload.

    Pure / read-only:

    - never mutates settings,
    - never opens network sockets,
    - never reads market data,
    - never raises on bad env input.

    ``manifest_path`` defaults to the canonical
    ``tests/fixtures/thinkorswim_momentum/manifest.json`` location used by
    the parity scaffold. The status only reports presence — it never
    parses or validates the fixture content from this surface.
    """
    raw_value = getattr(settings, "momentum_ranking_mode", None)
    raw_str: str | None = None
    if raw_value is not None:
        raw_str = str(raw_value)

    invalid_env = False
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized and normalized not in _VALID_MODES:
            invalid_env = True

    raw_active_allowed = getattr(settings, "momentum_active_ranking_allowed", False)
    active_allowed = _resolve_active_allowed(raw_active_allowed)
    raw_active_delta_scale = getattr(settings, "momentum_active_delta_scale", None)
    active_delta_scale, active_delta_scale_invalid = _resolve_active_delta_scale(
        raw_active_delta_scale
    )
    effective_mode, requested_mode, active_mode_blocked = resolve_effective_momentum_ranking_mode(
        raw_value, active_allowed=active_allowed
    )
    mode = effective_mode

    resolved_config = config or MomentumRankingConfig(
        mode=effective_mode,
        requested_mode=requested_mode,
        active_allowed=active_allowed,
        active_delta_scale=active_delta_scale,
        active_delta_scale_invalid=active_delta_scale_invalid,
    )

    manifest_resolved = (manifest_path or _DEFAULT_PARITY_MANIFEST_PATH).resolve()
    try:
        manifest_present = manifest_resolved.exists()
    except OSError:
        manifest_present = False

    # Resolve the richer Thinkorswim parity workflow status from the
    # fixture folder. This only inspects manifest + report files — it
    # never runs the indicator math or touches the database. Status
    # reads must stay cheap; the full parity comparison belongs in the
    # CLI / test path.
    fixture_dir = manifest_resolved.parent
    try:
        from macmarket_trader.indicators.thinkorswim_parity import (
            build_thinkorswim_momentum_parity_status,
        )

        parity_workflow = build_thinkorswim_momentum_parity_status(fixture_dir)
    except Exception:  # pragma: no cover - defensive; status must not raise.
        parity_workflow = {
            "status": "missing",
            "fixture_dir": str(fixture_dir),
            "manifest_present": manifest_present,
            "manifest_valid": False,
            "fixtures_total": 0,
            "fixtures_ready": 0,
            "fixtures_passed": None,
            "fixtures_failed": None,
            "fixtures_skipped": None,
            "last_report_generated_at": None,
            "report_path": None,
            "report_markdown_path": None,
            "report_present": False,
            "reason_codes": ["thinkorswim_manifest_missing"],
            "summary": None,
            "overall_status_from_report": None,
        }

    workflow_status = parity_workflow.get("status") or "missing"

    if workflow_status == "passed":
        parity_status = "validated_against_thinkorswim_fixture"
    elif workflow_status == "failed":
        parity_status = "thinkorswim_fixture_validation_failed"
    elif manifest_present:
        parity_status = "thinkorswim_fixture_present_pending_validation"
    else:
        parity_status = "pending_thinkorswim_fixture_validation"

    # ``real_thinkorswim_parity_pending`` is the legacy gate: it stays
    # True until parity has actually passed (workflow_status == "passed").
    real_thinkorswim_parity_pending = workflow_status != "passed"

    enabled = mode in {"shadow", "active"}
    applied_by_default = mode == "active"

    reason_codes: list[str] = []
    if invalid_env:
        reason_codes.append("invalid_env_value_resolved_to_shadow")
    if active_mode_blocked:
        reason_codes.append("active_mode_blocked_by_safety_guard")
    if resolved_config.active_delta_scale_invalid:
        reason_codes.append("momentum_active_delta_scale_invalid")
    if real_thinkorswim_parity_pending:
        reason_codes.append("thinkorswim_parity_pending")
    if mode == "active" and real_thinkorswim_parity_pending:
        reason_codes.append("active_mode_with_parity_pending")
    if mode == "active" and resolved_config.parity_required_for_active and real_thinkorswim_parity_pending:
        reason_codes.append("active_blocked_parity_required")

    active_mode_block_reason: str | None = None
    active_mode_warning: str | None = None
    if active_mode_blocked:
        active_mode_block_reason = (
            "Active Momentum ranking was requested but blocked because "
            "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING is not enabled."
        )
        active_mode_warning = active_mode_block_reason
    elif mode == "active":
        if real_thinkorswim_parity_pending and resolved_config.parity_required_for_active:
            active_mode_warning = (
                "Active mode is configured but blocked: parity_required_for_active=True "
                "and Thinkorswim parity fixtures are still pending."
            )
        elif real_thinkorswim_parity_pending:
            active_mode_warning = (
                "Active mode is applying a bounded momentum contribution while "
                "Thinkorswim parity fixtures are still pending review."
            )

    guardrails = list(_GUARDRAILS)
    guardrails.append("Approval, sizing, and paper-order creation remain manual.")
    guardrails.append(
        "Active mode changes ranking order only; it does not approve, reject, size, or route trades."
    )
    guardrails.append(
        "Active Momentum ranking requires MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING=true."
    )
    if real_thinkorswim_parity_pending:
        guardrails.append("Thinkorswim parity fixtures are still pending.")

    active_delta_scale_warning: str | None = None
    if resolved_config.active_delta_scale_invalid:
        active_delta_scale_warning = (
            "Configured MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE was unparseable or out of "
            "range [0.0, 1.0]; falling back to the deterministic default 0.35."
        )

    return MomentumRankingStatus(
        mode=mode,
        default_mode="shadow",
        env_var="MACMARKET_MOMENTUM_RANKING_MODE",
        raw_env_value=raw_str,
        invalid_env_value=invalid_env,
        enabled=enabled,
        applied_by_default=applied_by_default,
        parity_status=parity_status,
        parity_fixture_manifest_present=manifest_present,
        parity_fixture_manifest_path=str(manifest_resolved) if manifest_present else None,
        parity_required_for_active=resolved_config.parity_required_for_active,
        real_thinkorswim_parity_pending=real_thinkorswim_parity_pending,
        active_mode_warning=active_mode_warning,
        reason_codes=reason_codes,
        guardrails=guardrails,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        active_allowed=active_allowed,
        active_guard_env_var="MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING",
        active_mode_blocked=active_mode_blocked,
        active_mode_block_reason=active_mode_block_reason,
        active_delta_scale=resolved_config.active_delta_scale,
        active_delta_scale_env_var="MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE",
        active_delta_scale_invalid=resolved_config.active_delta_scale_invalid,
        active_delta_scale_warning=active_delta_scale_warning,
        active_delta_formula_version=ACTIVE_DELTA_FORMULA_VERSION,
        ranking_score_consistency_guard=RANKING_SCORE_CONSISTENCY_GUARD,
        queue_response_consistency_guard=QUEUE_RESPONSE_CONSISTENCY_GUARD,
        thinkorswim_parity_workflow_status=workflow_status,
        thinkorswim_parity_fixture_count=int(parity_workflow.get("fixtures_total") or 0),
        thinkorswim_parity_fixtures_ready=int(parity_workflow.get("fixtures_ready") or 0),
        thinkorswim_parity_fixtures_passed=parity_workflow.get("fixtures_passed"),
        thinkorswim_parity_fixtures_failed=parity_workflow.get("fixtures_failed"),
        thinkorswim_parity_report_available=bool(parity_workflow.get("report_present")),
        thinkorswim_parity_report_path=parity_workflow.get("report_path"),
        thinkorswim_parity_last_report_generated_at=parity_workflow.get("last_report_generated_at"),
        thinkorswim_parity_summary=parity_workflow.get("summary"),
        thinkorswim_parity_reason_codes=list(parity_workflow.get("reason_codes") or []),
    )


# ── Phase B6.2 score-delta helper ──────────────────────────────────────────


def _clamp_unit(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def apply_momentum_score_delta(
    base_score: float, contribution: MomentumRankingContribution
) -> tuple[float, float]:
    """Return ``(score_after, applied_delta)`` for the bounded Momentum delta.

    Phase B6.2 centralizes the active-mode score wiring so the engine and
    any caller route through the same scaled formula:

        applied_delta      = contribution.applied_score_delta
        score_after        = clamp01(base_score + applied_delta)

    Falls back to ``raw / 100 × scale`` only when the contribution payload
    pre-dates Phase B6.1 and ``applied_score_delta`` is missing. Never
    uses the un-scaled ``total_contribution / 100`` math — that was the
    Phase B6 wiring that caused queue saturation under high baselines.

    Returns ``(base_score, 0.0)`` whenever the contribution is None,
    disabled, off mode, or shadow mode — i.e. the queue score must not
    change.
    """
    if contribution is None or contribution.enabled is False:
        return _clamp_unit(base_score), 0.0
    if contribution.mode != "active" or not contribution.applied:
        return _clamp_unit(base_score), 0.0

    applied_delta = contribution.applied_score_delta
    if applied_delta is None or not math.isfinite(float(applied_delta)):
        # Backward-compatibility fallback for payloads predating Phase B6.1.
        raw = contribution.raw_total_contribution
        if raw is None:
            raw = contribution.total_contribution
        scale = contribution.active_delta_scale
        if scale is None or not math.isfinite(float(scale)) or float(scale) < 0.0 or float(scale) > 1.0:
            scale = DEFAULT_ACTIVE_DELTA_SCALE
        applied_delta = float(raw) / 100.0 * float(scale)
    if not math.isfinite(float(applied_delta)):
        applied_delta = 0.0

    score_after = _clamp_unit(base_score + float(applied_delta))
    return score_after, float(applied_delta)


# ── Phase B6.3 single-source-of-truth output guard ─────────────────────────


# Operator-visible marker that the deployed build is running the post-B6.1
# scaled active-delta formula. Surfaced in MomentumRankingStatus so a stale
# deploy is obvious from the Settings card without grepping git history.
ACTIVE_DELTA_FORMULA_VERSION: str = "scaled_v1"

# Always-on Phase B6.3 consistency guard. Kept as a module constant so the
# status payload, tests, and docs reference the same source of truth.
RANKING_SCORE_CONSISTENCY_GUARD: bool = True

# Floating-point tolerance for the consistency check. A divergence wider
# than this (post-clamp) is treated as a real mismatch that the guard had
# to correct rather than a rounding artifact.
_SCORE_CONSISTENCY_EPSILON: float = 1e-6


@dataclass(frozen=True)
class MomentumScoreConsistencyResult:
    """Output of :func:`enforce_score_consistency`.

    ``intended_applied_delta`` is the **scaled** ranking-score delta from
    ``contribution.applied_score_delta`` (Phase B6.1). It is the value the
    operator UI should label "Applied delta @ scale" / "Intended delta".

    ``realized_score_delta`` is ``final_score - score_before_momentum``
    after the [0, 1] clamp. When the clamp does not engage it equals
    ``intended_applied_delta``; when the clamp truncates (e.g. baseline
    0.97 + intended +0.07 → 1.000) it shrinks to fit and is therefore
    the right value for any "what actually happened to the score" UI.

    ``corrected`` is True only when the observed score diverged from the
    Phase B6.1 formula by more than the floating-point tolerance — i.e.
    a legacy code path applied a different delta. The contribution's
    reason codes pick up ``momentum_score_consistency_corrected``.
    """

    final_score: float
    intended_applied_delta: float
    realized_score_delta: float
    corrected: bool


def enforce_score_consistency(
    *,
    observed_score: float,
    score_before_momentum: float | None,
    contribution: MomentumRankingContribution | None,
) -> MomentumScoreConsistencyResult:
    """Enforce the Phase B6.3 single source of truth for active scores.

    Recomputes ``expected_score = clamp01(score_before + applied_delta)``
    from the contribution payload, compares it against ``observed_score``,
    and returns the corrected score plus the intended/realized delta
    split. Off / shadow / blocked-active / disabled contributions
    pass-through unchanged (final = observed, intended = realized = 0).

    Never raises; sanitizes NaN/inf inputs to deterministic defaults so a
    malformed payload cannot crash the queue endpoint.
    """
    observed = _sanitize(float(observed_score))
    if contribution is None or contribution.enabled is False:
        clean = _clamp_unit(observed)
        return MomentumScoreConsistencyResult(
            final_score=clean,
            intended_applied_delta=0.0,
            realized_score_delta=0.0,
            corrected=False,
        )
    if contribution.mode != "active" or not contribution.applied:
        clean = _clamp_unit(observed)
        return MomentumScoreConsistencyResult(
            final_score=clean,
            intended_applied_delta=0.0,
            realized_score_delta=0.0,
            corrected=False,
        )

    base = (
        _sanitize(float(score_before_momentum))
        if score_before_momentum is not None
        else 0.0
    )
    # apply_momentum_score_delta already handles the
    # backward-compatibility fallback when ``applied_score_delta`` is
    # missing on legacy payloads, so the guard delegates to it for the
    # intended value rather than duplicating the fallback logic.
    expected_score, intended_delta = apply_momentum_score_delta(base, contribution)
    realized_delta = expected_score - base
    corrected = abs(observed - expected_score) > _SCORE_CONSISTENCY_EPSILON
    return MomentumScoreConsistencyResult(
        final_score=expected_score,
        intended_applied_delta=float(intended_delta),
        realized_score_delta=float(realized_delta),
        corrected=corrected,
    )


# ── Phase B6.4 response-boundary queue consistency guard ───────────────────


# Always-on Phase B6.4 queue-response consistency guard. Surfaced in the
# status payload so a stale deploy is obvious: when this is True, the
# queue route is wrapping its output through ``apply_queue_response_consistency``.
QUEUE_RESPONSE_CONSISTENCY_GUARD: bool = True


def _coerce_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        flt = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(flt) or math.isinf(flt):
        return None
    return flt


def _coerce_contribution(value: Any) -> MomentumRankingContribution | None:
    """Best-effort revival of a contribution dict into the typed model.

    The queue route hands us already-serialized dicts (engine output is
    ``asdict(...)``). We re-validate so the guard can read typed fields
    without dict-key footguns. Returns None when the payload is missing
    or malformed.
    """
    if value is None:
        return None
    if isinstance(value, MomentumRankingContribution):
        return value
    if isinstance(value, Mapping):
        try:
            return MomentumRankingContribution.model_validate(dict(value))
        except Exception:  # noqa: BLE001 - never raise from a sanitizer
            return None
    return None


def apply_queue_response_consistency(
    queue_items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Phase B6.4 — last-boundary correction for queue-row score consistency.

    Walks each item dict and, for active + applied contributions, forces:

        expected_score              = clamp01(score_before + applied_score_delta)
        candidate.score             = expected_score
        candidate.score_after_momentum     = expected_score
        candidate.momentum_score_delta     = applied_score_delta (intended)
        candidate.momentum_realized_score_delta = expected_score - score_before

    When the original observed score differed from ``expected_score`` by
    more than the Phase B6.3 floating-point tolerance, the row picks up
    ``score_consistency_status="corrected"`` and the
    ``momentum_score_consistency_corrected`` reason code on the
    contribution. Otherwise the status is ``"ok"``.

    Rows whose contribution is None, off, shadow, blocked-active, or
    disabled are passed through with ``score_consistency_status="ok"``
    and no score modification. The helper is pure-defensive: never
    changes raw ranking math, never raises, never changes approval /
    sizing / routing fields, and is safe to call on already-correct
    payloads (the only effect is the diagnostic field).

    Returns ``(items, corrected_count)``. The list is mutated in place
    **and** returned for ergonomic chaining with route code.
    """
    if not queue_items:
        return queue_items, 0

    corrected_count = 0
    for item in queue_items:
        if not isinstance(item, dict):
            continue
        contribution_value = item.get("momentum_contribution")
        contribution = _coerce_contribution(contribution_value)
        if (
            contribution is None
            or contribution.enabled is False
            or contribution.mode != "active"
            or not contribution.applied
        ):
            # Defensive default: a present momentum_contribution that is
            # not active/applied is still tagged 'ok' so the frontend
            # can rely on the field being present.
            if contribution_value is not None:
                item.setdefault("score_consistency_status", "ok")
            continue

        score_before = _coerce_float_or_none(item.get("score_before_momentum"))
        observed_score = _coerce_float_or_none(item.get("score"))
        if observed_score is None:
            # Treat missing as 0 so the consistency check still runs.
            observed_score = 0.0

        guard = enforce_score_consistency(
            observed_score=observed_score,
            score_before_momentum=score_before,
            contribution=contribution,
        )

        # Always-on: re-stamp the canonical fields from the guard so the
        # response payload cannot disagree with the contribution payload.
        item["score"] = round(guard.final_score, 3)
        item["score_after_momentum"] = round(guard.final_score, 4)
        item["momentum_score_delta"] = round(guard.intended_applied_delta, 6)
        item["momentum_realized_score_delta"] = round(guard.realized_score_delta, 6)
        item["momentum_rank_mode"] = "active"

        if guard.corrected:
            corrected_count += 1
            item["score_consistency_status"] = "corrected"
            reason_codes = list(contribution.reason_codes or [])
            if "momentum_score_consistency_corrected" not in reason_codes:
                reason_codes.append("momentum_score_consistency_corrected")
            updated_contribution = contribution.model_copy(
                update={"reason_codes": reason_codes}
            )
            item["momentum_contribution"] = updated_contribution.model_dump(mode="json")
        else:
            item["score_consistency_status"] = "ok"
            # Round-trip the contribution dict so any non-finite floats are
            # sanitized by the Pydantic model_dump.
            item["momentum_contribution"] = contribution.model_dump(mode="json")

    return queue_items, corrected_count


__all__ = [
    "ACTIVE_DELTA_FORMULA_VERSION",
    "DEFAULT_ACTIVE_DELTA_SCALE",
    "MomentumRankingConfig",
    "MomentumScoreConsistencyResult",
    "QUEUE_RESPONSE_CONSISTENCY_GUARD",
    "RANKING_SCORE_CONSISTENCY_GUARD",
    "apply_momentum_score_delta",
    "apply_queue_response_consistency",
    "build_momentum_ranking_contribution",
    "build_momentum_ranking_status",
    "enforce_score_consistency",
    "momentum_ranking_config_from_settings",
    "resolve_effective_momentum_ranking_mode",
    "resolve_momentum_ranking_mode",
]

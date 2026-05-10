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
    mode = resolve_momentum_ranking_mode(raw_value)

    invalid_env = False
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized and normalized not in _VALID_MODES:
            invalid_env = True

    resolved_config = config or MomentumRankingConfig(mode=mode)

    manifest_resolved = (manifest_path or _DEFAULT_PARITY_MANIFEST_PATH).resolve()
    try:
        manifest_present = manifest_resolved.exists()
    except OSError:
        manifest_present = False

    parity_status = (
        "validated_against_thinkorswim_fixture"
        if manifest_present
        else "pending_thinkorswim_fixture_validation"
    )
    real_thinkorswim_parity_pending = not manifest_present

    enabled = mode in {"shadow", "active"}
    applied_by_default = mode == "active"

    reason_codes: list[str] = []
    if invalid_env:
        reason_codes.append("invalid_env_value_resolved_to_shadow")
    if real_thinkorswim_parity_pending:
        reason_codes.append("thinkorswim_parity_pending")
    if mode == "active" and real_thinkorswim_parity_pending:
        reason_codes.append("active_mode_with_parity_pending")
    if mode == "active" and resolved_config.parity_required_for_active and real_thinkorswim_parity_pending:
        reason_codes.append("active_blocked_parity_required")

    active_mode_warning: str | None = None
    if mode == "active":
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
    if real_thinkorswim_parity_pending:
        guardrails.append("Real Thinkorswim parity fixtures are still pending.")

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
    )


__all__ = [
    "MomentumRankingConfig",
    "build_momentum_ranking_contribution",
    "build_momentum_ranking_status",
    "momentum_ranking_config_from_settings",
    "resolve_momentum_ranking_mode",
]

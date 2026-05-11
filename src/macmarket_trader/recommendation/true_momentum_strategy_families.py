"""Phase C0 — True Momentum strategy-family scaffolding.

This module is **scaffold-only**. It defines pure specs and a read-only
status builder for the three planned True Momentum strategy families.
It deliberately does not:

- generate recommendations,
- create queue candidates,
- approve, reject, size, route, open, close, or settle trades,
- attach itself to ``DeterministicRankingEngine`` or
  ``build_momentum_ranking_contribution``,
- mutate state, hit a provider, or call market data,
- call an LLM,
- read or require Thinkorswim parity fixtures.

The frontend may render the resolved status as a read-only card under
Settings. Nothing in this module is wired into the active recommendation
or paper-order flow. See ``docs/true-momentum-strategy-families.md``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

TrueMomentumStrategyMode = Literal["disabled", "research_preview", "active"]

_VALID_MODES: tuple[TrueMomentumStrategyMode, ...] = (
    "disabled",
    "research_preview",
    "active",
)

MODE_ENV_VAR = "MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE"
GUARD_ENV_VAR = "MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES"
PHASE = "C0"
IMPLEMENTATION_STATUS = "scaffold_only"

# Reason codes are stable identifiers a frontend can map to copy.
REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD = (
    "true_momentum_strategy_mode_blocked_by_guard"
)
REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED = (
    "true_momentum_strategy_active_mode_not_implemented"
)
REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED = (
    "true_momentum_strategy_invalid_env_value_resolved_to_disabled"
)
REASON_THINKORSWIM_PARITY_PENDING = "thinkorswim_parity_pending"

_GUARDRAILS: tuple[str, ...] = (
    "Phase C0 is scaffold-only — no queue candidates are generated.",
    "True Momentum strategy families do not approve, reject, size, or route trades.",
    "Paper-order creation remains manual and unaffected by this layer.",
    "Active mode is reserved; it is not implemented in Phase C0.",
    "Thinkorswim parity fixtures are still pending.",
)


@dataclass(frozen=True)
class TrueMomentumStrategyFamilySpec:
    """Pure specification for a planned True Momentum strategy family.

    These are descriptions of *future* deterministic engines. The fields
    are intentionally documentation-shaped — they list inputs and
    guardrails rather than thresholds or actions. Nothing on this spec
    is consumed by the ranking engine, the recommendation generator,
    the paper-order layer, or any execution path.
    """

    id: str
    label: str
    description: str
    status: Literal["planned", "research_preview", "disabled"]
    intended_direction: Literal["long", "short", "watch"]
    required_inputs: tuple[str, ...]
    deterministic_signals: tuple[str, ...]
    guardrails: tuple[str, ...]
    not_allowed_actions: tuple[str, ...] = field(
        default=(
            "approve_trade",
            "reject_trade",
            "size_trade",
            "route_order",
            "open_position",
            "close_position",
            "settle_position",
        )
    )
    phase: str = PHASE
    implementation_status: str = IMPLEMENTATION_STATUS


# ── Planned families (Phase C0 — research/specs only) ─────────────────

_FAMILY_SPECS: tuple[TrueMomentumStrategyFamilySpec, ...] = (
    TrueMomentumStrategyFamilySpec(
        id="true_momentum_continuation",
        label="True Momentum Continuation",
        description=(
            "Planned bullish continuation family: triggers a research "
            "preview when Momentum score, trend alignment, HiLo "
            "confirmation, and inferred direction all align on the same "
            "long side without an active no-trade or reversal warning."
        ),
        status="planned",
        intended_direction="long",
        required_inputs=(
            "momentum_score_snapshot",
            "trend_alignment_score",
            "hilo_confirmation_state",
            "inferred_direction",
            "regime_state",
            "risk_calendar_decision",
            "liquidity_spread_context",
        ),
        deterministic_signals=(
            "momentum_total_label_in_bull_or_max_bull",
            "trend_alignment_long_confirmed",
            "hilo_confirmation_long",
            "no_active_no_trade_or_reversal_warning",
        ),
        guardrails=(
            "Continuation only when Thinkorswim parity is reviewed.",
            "Risk calendar must permit new entries.",
            "Manual operator confirmation required before any paper-order action.",
        ),
    ),
    TrueMomentumStrategyFamilySpec(
        id="true_momentum_pullback",
        label="True Momentum Pullback",
        description=(
            "Planned bullish pullback family: triggers a research "
            "preview when overall Momentum remains strong but price has "
            "pulled back near deterministic EMA / ATR support, with no "
            "reversal warning."
        ),
        status="planned",
        intended_direction="long",
        required_inputs=(
            "momentum_score_snapshot",
            "trend_alignment_score",
            "ema_pullback_distance",
            "atr_pullback_distance",
            "pullback_signal_flag",
            "regime_state",
            "risk_calendar_decision",
        ),
        deterministic_signals=(
            "momentum_total_label_remains_bull_or_max_bull",
            "deterministic_pullback_signal_active",
            "no_active_reversal_warning",
            "structure_or_ema_support_within_pullback_band",
        ),
        guardrails=(
            "Pullback band thresholds are placeholders pending C1 design.",
            "No automatic re-entry — operator confirms each preview.",
        ),
    ),
    TrueMomentumStrategyFamilySpec(
        id="true_momentum_reversal_watch",
        label="True Momentum Reversal / Weakening Watch",
        description=(
            "Planned warning/watch family: surfaces transitions out of "
            "Bull/Max Bull or Bear/Max Bear regimes and active reversal "
            "or no-trade warnings. Watch-only; never proposes an entry."
        ),
        status="planned",
        intended_direction="watch",
        required_inputs=(
            "momentum_score_snapshot",
            "total_label_history",
            "reversal_warning_flag",
            "no_trade_warning_flag",
            "regime_transition_context",
            "risk_calendar_decision",
        ),
        deterministic_signals=(
            "total_label_transition_from_bull_or_max_bull",
            "total_label_transition_from_bear_or_max_bear",
            "active_reversal_or_no_trade_warning",
        ),
        guardrails=(
            "Watch-only — never proposes entries, stops, or targets.",
            "No order routing; no paper-order creation.",
        ),
    ),
)


def _normalize_mode(value: Any) -> tuple[TrueMomentumStrategyMode, bool]:
    """Return (mode, invalid_env_value). Unknown values resolve to disabled."""
    if value is None:
        return "disabled", False
    if not isinstance(value, str):
        return "disabled", True
    candidate = value.strip().lower()
    if not candidate:
        return "disabled", False
    if candidate in _VALID_MODES:
        return candidate, False  # type: ignore[return-value]
    return "disabled", True


def _resolve_guard_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        try:
            return bool(int(value)) and not isinstance(value, bool)
        except (TypeError, ValueError):
            return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


@dataclass(frozen=True)
class TrueMomentumStrategyStatus:
    """Pure status describing the resolved Phase C0 mode + guard.

    Returned from :func:`build_true_momentum_strategy_status`. Mirrors
    the Pydantic ``TrueMomentumStrategyFamilyStatusPayload`` returned
    from the read-only HTTP endpoint, but stays dataclass-shaped for
    internal pure helpers and tests that do not need pydantic.
    """

    requested_mode: TrueMomentumStrategyMode
    effective_mode: TrueMomentumStrategyMode
    enabled: bool
    guard_enabled: bool
    invalid_env_value: bool
    mode_env_var: str
    guard_env_var: str
    reason_codes: tuple[str, ...]
    guardrails: tuple[str, ...]
    family_specs: tuple[TrueMomentumStrategyFamilySpec, ...]
    phase: str
    implementation_status: str
    parity_status: str
    parity_required_for_active: bool


def list_true_momentum_strategy_family_specs(
    config: Any = None,
) -> list[TrueMomentumStrategyFamilySpec]:
    """Return the planned Phase C0 family specs.

    ``config`` is accepted for forward-compatibility (a future C1 may
    filter by mode); the Phase C0 implementation ignores it and always
    returns the same three planned specs.
    """
    _ = config  # forward-compat placeholder
    return list(_FAMILY_SPECS)


def build_true_momentum_strategy_status(
    settings: Any,
) -> TrueMomentumStrategyStatus:
    """Resolve the configured mode + guard into a pure status object.

    Pure / read-only:

    - never mutates settings,
    - never opens a network socket,
    - never reads market data,
    - never raises on bad env input — invalid values fall back to
      ``disabled`` with the
      ``true_momentum_strategy_invalid_env_value_resolved_to_disabled``
      reason code.
    """
    raw_mode = getattr(settings, "true_momentum_strategy_mode", None)
    raw_guard = getattr(settings, "allow_true_momentum_strategy_families", None)
    requested_mode, invalid_env_value = _normalize_mode(raw_mode)
    guard_enabled = _resolve_guard_truthy(raw_guard)

    reason_codes: list[str] = []
    if invalid_env_value:
        reason_codes.append(REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED)

    if requested_mode == "disabled":
        effective_mode: TrueMomentumStrategyMode = "disabled"
    elif not guard_enabled:
        # research_preview or active without the explicit guard → disabled.
        effective_mode = "disabled"
        reason_codes.append(REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD)
    elif requested_mode == "active":
        # Active is reserved — Phase C0 always degrades it to research_preview.
        effective_mode = "research_preview"
        reason_codes.append(REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED)
    else:
        effective_mode = "research_preview"

    enabled = effective_mode != "disabled"

    # Phase C0 inherits the same "Thinkorswim parity pending" posture
    # as Phase B. The closeout doc treats parity as a precondition for
    # any future C1 implementation.
    parity_status = "pending_thinkorswim_fixture_validation"
    reason_codes.append(REASON_THINKORSWIM_PARITY_PENDING)

    return TrueMomentumStrategyStatus(
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        enabled=enabled,
        guard_enabled=guard_enabled,
        invalid_env_value=invalid_env_value,
        mode_env_var=MODE_ENV_VAR,
        guard_env_var=GUARD_ENV_VAR,
        reason_codes=tuple(reason_codes),
        guardrails=_GUARDRAILS,
        family_specs=_FAMILY_SPECS,
        phase=PHASE,
        implementation_status=IMPLEMENTATION_STATUS,
        parity_status=parity_status,
        parity_required_for_active=True,
    )


TrueMomentumStrategyPreviewFamilyId = Literal[
    "true_momentum_continuation",
    "true_momentum_pullback",
    "true_momentum_reversal_watch",
]

TrueMomentumStrategyPreviewMatchStrength = Literal[
    "strong", "moderate", "watch", "blocked"
]

PREVIEW_PHASE = "C1"
PREVIEW_IMPLEMENTATION_STATUS = "research_preview"

PREVIEW_DETERMINISTIC_NOTE = (
    "True Momentum strategy previews are research-only. They do not generate "
    "queue candidates, approve, reject, size, or route trades."
)

REASON_TRUE_MOMENTUM_STRATEGY_MODE_DISABLED = "true_momentum_strategy_mode_disabled"
REASON_TRUE_MOMENTUM_PREVIEW_NO_CANDIDATES = "true_momentum_preview_no_candidates"
REASON_TRUE_MOMENTUM_CONTINUATION_MATCH = "true_momentum_continuation_match"
REASON_TRUE_MOMENTUM_PULLBACK_MATCH = "true_momentum_pullback_match"
REASON_TRUE_MOMENTUM_REVERSAL_WATCH_MATCH = "true_momentum_reversal_watch_match"
REASON_TRUE_MOMENTUM_NO_FAMILY_MATCH = "true_momentum_no_family_match"


@dataclass(frozen=True)
class TrueMomentumStrategyPreviewCandidate:
    """A single non-actionable preview row.

    Phase C1 surface. Describes how the planned True Momentum families
    would *classify* an already-loaded recommendation queue candidate.
    Never proposes an entry / stop / target / size / approval / order.
    """

    preview_id: str
    family_id: TrueMomentumStrategyPreviewFamilyId
    family_label: str
    symbol: str
    strategy: str
    rank: int
    baseline_score: float
    active_score: float
    raw_contribution: float
    applied_delta: float
    total_score: int | None
    total_label: str | None
    trend_score: float | None
    momo_score: float | None
    inferred_direction: Literal["long", "short", "unknown"]
    pullback_signal: bool
    reversal_warning: bool
    no_trade_warning: bool
    reason_codes: tuple[str, ...]
    operational_caveats: tuple[str, ...]
    match_strength: TrueMomentumStrategyPreviewMatchStrength
    research_notes: tuple[str, ...]
    non_actionable: bool = True


@dataclass(frozen=True)
class TrueMomentumStrategyPreviewSummary:
    candidate_count: int
    preview_count: int
    continuation_count: int
    pullback_count: int
    reversal_watch_count: int
    strong_count: int
    moderate_count: int
    watch_count: int
    blocked_count: int
    parity_pending_count: int
    derived_higher_timeframe_count: int
    operational_caveat_count: int


@dataclass(frozen=True)
class TrueMomentumStrategyPreviewResult:
    status: TrueMomentumStrategyStatus
    previews: tuple[TrueMomentumStrategyPreviewCandidate, ...]
    previews_generated: bool
    summary: TrueMomentumStrategyPreviewSummary
    guardrails: tuple[str, ...]
    phase: str
    implementation_status: str
    preview_phase: str
    preview_implementation_status: str
    deterministic_note: str


_FAMILY_LABELS: dict[str, str] = {
    "true_momentum_continuation": "True Momentum Continuation",
    "true_momentum_pullback": "True Momentum Pullback",
    "true_momentum_reversal_watch": "True Momentum Reversal / Weakening Watch",
}


# ── Candidate adapter ────────────────────────────────────────────────


def _get(candidate: Any, key: str, default: Any = None) -> Any:
    if candidate is None:
        return default
    if isinstance(candidate, Mapping):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def _finite_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return int(out)


def _finite_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def _clamp_unit(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(v) for v in value if isinstance(v, str)]
    except TypeError:
        return []


def _bool(value: Any) -> bool:
    return bool(value) if value is not None else False


@dataclass(frozen=True)
class _NormalizedCandidate:
    symbol: str
    strategy: str
    rank: int
    baseline_score: float
    active_score: float
    raw_contribution: float
    applied_delta: float
    total_score: int | None
    total_label: str | None
    trend_score: float | None
    momo_score: float | None
    inferred_direction: Literal["long", "short", "unknown"]
    pullback_signal: bool
    reversal_warning: bool
    no_trade_warning: bool
    contribution_mode: Literal["off", "shadow", "active"]
    contribution_applied: bool
    reason_codes: tuple[str, ...]
    operational_caveats: tuple[str, ...]
    strategy_lower: str
    active_delta_scale: float | None


_STRATEGY_LONG_HINTS: tuple[str, ...] = (
    "event continuation",
    "event_continuation",
    "breakout",
    "pullback",
    "trend",
    "haco",
    "continuation",
)


def _normalize_candidate(candidate: Any) -> _NormalizedCandidate | None:
    if candidate is None:
        return None
    symbol_raw = _get(candidate, "symbol", "")
    strategy_raw = _get(candidate, "strategy", "")
    symbol = str(symbol_raw).strip() if symbol_raw else ""
    strategy = str(strategy_raw).strip() if strategy_raw else ""
    if not symbol or not strategy:
        return None
    rank = int(_finite_float(_get(candidate, "rank", 0), 0.0))
    score_after = _get(candidate, "score_after_momentum")
    score = _get(candidate, "score")
    score_before = _get(candidate, "score_before_momentum")
    contribution = _get(candidate, "momentum_contribution")

    active_score = _clamp_unit(
        _finite_float(score_after if score_after is not None else score, 0.0)
    )
    baseline_score = _clamp_unit(
        _finite_float(score_before, active_score)
    )
    applied_delta = _finite_float(
        _get(candidate, "momentum_score_delta", 0.0), 0.0
    )

    raw_contribution = 0.0
    total_score = None
    total_label = None
    trend_score = None
    momo_score = None
    inferred_direction: Literal["long", "short", "unknown"] = "unknown"
    pullback_signal = False
    reversal_warning = False
    no_trade_warning = False
    contribution_mode: Literal["off", "shadow", "active"] = "off"
    contribution_applied = False
    reason_codes: list[str] = []
    operational_caveats: list[str] = []
    active_delta_scale: float | None = None

    if contribution is not None:
        raw_contribution = _finite_float(
            _get(contribution, "raw_total_contribution",
                 _get(contribution, "shadow_contribution", 0.0)),
            0.0,
        )
        applied_delta_from_contribution = _finite_float_or_none(
            _get(contribution, "applied_score_delta")
        )
        if applied_delta_from_contribution is not None:
            applied_delta = applied_delta_from_contribution
        total_score = _finite_int_or_none(_get(contribution, "total_score"))
        total_label_raw = _get(contribution, "total_label")
        total_label = (
            str(total_label_raw).strip() if isinstance(total_label_raw, str) else None
        )
        trend_score = _finite_float_or_none(_get(contribution, "trend_score"))
        momo_score = _finite_float_or_none(_get(contribution, "momo_score"))
        direction_raw = _get(contribution, "inferred_direction", "unknown")
        if isinstance(direction_raw, str) and direction_raw.lower() in (
            "long",
            "short",
            "unknown",
        ):
            inferred_direction = direction_raw.lower()  # type: ignore[assignment]
        pullback_signal = _bool(_get(contribution, "pullback_signal"))
        reversal_warning = _bool(_get(contribution, "reversal_warning"))
        no_trade_warning = _bool(_get(contribution, "no_trade_warning"))
        mode_raw = _get(contribution, "mode", "off")
        if isinstance(mode_raw, str) and mode_raw.lower() in ("off", "shadow", "active"):
            contribution_mode = mode_raw.lower()  # type: ignore[assignment]
        contribution_applied = _bool(_get(contribution, "applied"))
        reason_codes = _string_list(_get(contribution, "reason_codes"))
        active_delta_scale = _finite_float_or_none(
            _get(contribution, "active_delta_scale")
        )
        # Track per-candidate operational caveats so the preview row can
        # surface the same data-quality / parity caveats Phase B7.1 ships.
        if "thinkorswim_parity_pending" in reason_codes:
            operational_caveats.append("thinkorswim_parity_pending")
        if "derived_higher_timeframe" in reason_codes:
            operational_caveats.append("derived_higher_timeframe")
        if "direction_unknown" in reason_codes:
            operational_caveats.append("direction_unknown")
        if "active_mode_blocked_by_safety_guard" in reason_codes:
            operational_caveats.append("active_mode_blocked_by_safety_guard")
        status_tag = _get(candidate, "score_consistency_status")
        if isinstance(status_tag, str) and status_tag == "corrected":
            operational_caveats.append("score_consistency_corrected")

    return _NormalizedCandidate(
        symbol=symbol,
        strategy=strategy,
        rank=rank,
        baseline_score=baseline_score,
        active_score=active_score,
        raw_contribution=raw_contribution,
        applied_delta=applied_delta,
        total_score=total_score,
        total_label=total_label,
        trend_score=trend_score,
        momo_score=momo_score,
        inferred_direction=inferred_direction,
        pullback_signal=pullback_signal,
        reversal_warning=reversal_warning,
        no_trade_warning=no_trade_warning,
        contribution_mode=contribution_mode,
        contribution_applied=contribution_applied,
        reason_codes=tuple(reason_codes),
        operational_caveats=tuple(operational_caveats),
        strategy_lower=strategy.lower(),
        active_delta_scale=active_delta_scale,
    )


# ── Classification helpers ───────────────────────────────────────────


_BULLISH_LABELS = {"bull", "max bull"}
_BEARISH_LABELS = {"bear", "max bear"}


def _label_is_bullish(label: str | None) -> bool:
    return bool(label) and label.strip().lower() in _BULLISH_LABELS


def _label_is_bearish(label: str | None) -> bool:
    return bool(label) and label.strip().lower() in _BEARISH_LABELS


def _strategy_is_long_biased(strategy_lower: str) -> bool:
    if not strategy_lower:
        return False
    for hint in _STRATEGY_LONG_HINTS:
        if hint in strategy_lower:
            return True
    return False


def _strategy_is_pullback(strategy_lower: str) -> bool:
    return "pullback" in strategy_lower or "trend continuation" in strategy_lower


def _classify_reversal_watch(
    norm: _NormalizedCandidate,
) -> tuple[bool, list[str], list[str]]:
    """Returns (matches, reason_codes, research_notes)."""
    notes: list[str] = []
    reasons: list[str] = []
    long_biased = (
        norm.inferred_direction == "long" or _strategy_is_long_biased(norm.strategy_lower)
    )
    matched = False
    if norm.reversal_warning:
        matched = True
        reasons.append("momentum_reversal_warning")
        notes.append("Reversal warning is active on the source candidate.")
    if norm.no_trade_warning:
        matched = True
        reasons.append("momentum_no_trade_warning")
        notes.append("No-trade warning is active on the source candidate.")
    if long_biased and _label_is_bearish(norm.total_label):
        matched = True
        reasons.append("bear_total_label_long_strategy_contradiction")
        notes.append(
            "Long-biased strategy carries a Bear / Max Bear Momentum total label."
        )
    if (
        long_biased
        and norm.total_score is not None
        and norm.total_score <= -50
    ):
        matched = True
        reasons.append("bear_total_score_long_strategy_contradiction")
        notes.append(
            "Long-biased strategy carries a deeply bearish Momentum total score "
            f"({norm.total_score})."
        )
    if matched:
        reasons.append(REASON_TRUE_MOMENTUM_REVERSAL_WATCH_MATCH)
        notes.append("Watch-only — never proposes an entry, stop, or order.")
    return matched, reasons, notes


def _classify_pullback(
    norm: _NormalizedCandidate,
) -> tuple[bool, list[str], list[str], TrueMomentumStrategyPreviewMatchStrength]:
    notes: list[str] = []
    reasons: list[str] = []
    if norm.no_trade_warning or norm.reversal_warning:
        return False, [], [], "blocked"
    if norm.inferred_direction != "long":
        return False, [], [], "blocked"
    if _label_is_bearish(norm.total_label):
        return False, [], [], "blocked"
    label_bullish = _label_is_bullish(norm.total_label)
    score_strong = norm.total_score is not None and norm.total_score >= 80
    if not (label_bullish or score_strong):
        return False, [], [], "blocked"
    if norm.raw_contribution <= 0:
        return False, [], [], "blocked"
    pullback_by_strategy = _strategy_is_pullback(norm.strategy_lower)
    if not (norm.pullback_signal or pullback_by_strategy):
        return False, [], [], "blocked"
    reasons.append(REASON_TRUE_MOMENTUM_PULLBACK_MATCH)
    if norm.pullback_signal:
        reasons.append("momentum_pullback_signal_active")
        notes.append("Deterministic pullback signal is active.")
    if pullback_by_strategy:
        reasons.append("strategy_is_pullback_or_trend_continuation")
        notes.append("Source strategy is Pullback / Trend Continuation aligned.")
    if label_bullish:
        notes.append(f"Momentum total label is {norm.total_label}.")
    if score_strong:
        notes.append(f"Momentum total score is {norm.total_score} (≥ 80).")
    notes.append("Research preview only — no entry / stop / target is proposed.")
    # Strength: strong when the deterministic pullback signal AND a
    # bullish total label both fire. Moderate otherwise.
    strength: TrueMomentumStrategyPreviewMatchStrength = (
        "strong" if norm.pullback_signal and label_bullish else "moderate"
    )
    return True, reasons, notes, strength


def _classify_continuation(
    norm: _NormalizedCandidate,
) -> tuple[bool, list[str], list[str], TrueMomentumStrategyPreviewMatchStrength]:
    notes: list[str] = []
    reasons: list[str] = []
    if norm.no_trade_warning or norm.reversal_warning:
        return False, [], [], "blocked"
    if norm.inferred_direction == "short":
        return False, [], [], "blocked"
    long_biased = (
        norm.inferred_direction == "long" or _strategy_is_long_biased(norm.strategy_lower)
    )
    if not long_biased:
        return False, [], [], "blocked"
    if _label_is_bearish(norm.total_label):
        return False, [], [], "blocked"
    label_bullish = _label_is_bullish(norm.total_label)
    score_strong = norm.total_score is not None and norm.total_score >= 80
    if not (label_bullish or score_strong):
        return False, [], [], "blocked"
    if norm.raw_contribution <= 0:
        return False, [], [], "blocked"
    reasons.append(REASON_TRUE_MOMENTUM_CONTINUATION_MATCH)
    if label_bullish:
        reasons.append("momentum_total_label_bullish")
        notes.append(f"Momentum total label is {norm.total_label}.")
    if score_strong:
        reasons.append("momentum_total_score_strong")
        notes.append(f"Momentum total score is {norm.total_score} (≥ 80).")
    trend_strong = norm.trend_score is not None and norm.trend_score >= 70
    momo_strong = norm.momo_score is not None and norm.momo_score >= 70
    if trend_strong:
        reasons.append("trend_alignment_long_confirmed")
        notes.append(f"Trend score is {norm.trend_score:.0f} (≥ 70).")
    if momo_strong:
        reasons.append("momo_score_long_confirmed")
        notes.append(f"Momo score is {norm.momo_score:.0f} (≥ 70).")
    notes.append("Research preview only — no entry / stop / target is proposed.")
    # Strong when both trend AND momo confirm; moderate otherwise.
    strength: TrueMomentumStrategyPreviewMatchStrength = (
        "strong" if trend_strong and momo_strong else "moderate"
    )
    return True, reasons, notes, strength


def _build_preview_row(
    norm: _NormalizedCandidate,
    family_id: TrueMomentumStrategyPreviewFamilyId,
    reasons: list[str],
    notes: list[str],
    match_strength: TrueMomentumStrategyPreviewMatchStrength,
) -> TrueMomentumStrategyPreviewCandidate:
    preview_id = (
        f"preview::{family_id}::{norm.symbol}::{norm.strategy}::{norm.rank}"
    )
    return TrueMomentumStrategyPreviewCandidate(
        preview_id=preview_id,
        family_id=family_id,
        family_label=_FAMILY_LABELS[family_id],
        symbol=norm.symbol,
        strategy=norm.strategy,
        rank=norm.rank,
        baseline_score=norm.baseline_score,
        active_score=norm.active_score,
        raw_contribution=norm.raw_contribution,
        applied_delta=norm.applied_delta,
        total_score=norm.total_score,
        total_label=norm.total_label,
        trend_score=norm.trend_score,
        momo_score=norm.momo_score,
        inferred_direction=norm.inferred_direction,
        pullback_signal=norm.pullback_signal,
        reversal_warning=norm.reversal_warning,
        no_trade_warning=norm.no_trade_warning,
        reason_codes=tuple(dict.fromkeys(reasons)),
        operational_caveats=norm.operational_caveats,
        match_strength=match_strength,
        research_notes=tuple(notes),
        non_actionable=True,
    )


def _summarize_previews(
    candidates: Sequence[Any],
    previews: Sequence[TrueMomentumStrategyPreviewCandidate],
) -> TrueMomentumStrategyPreviewSummary:
    continuation = sum(
        1 for p in previews if p.family_id == "true_momentum_continuation"
    )
    pullback = sum(1 for p in previews if p.family_id == "true_momentum_pullback")
    reversal_watch = sum(
        1 for p in previews if p.family_id == "true_momentum_reversal_watch"
    )
    strong = sum(1 for p in previews if p.match_strength == "strong")
    moderate = sum(1 for p in previews if p.match_strength == "moderate")
    watch = sum(1 for p in previews if p.match_strength == "watch")
    blocked = sum(1 for p in previews if p.match_strength == "blocked")
    parity_pending = sum(
        1 for p in previews if "thinkorswim_parity_pending" in p.operational_caveats
    )
    derived_htf = sum(
        1 for p in previews if "derived_higher_timeframe" in p.operational_caveats
    )
    operational_caveat_count = sum(
        1 for p in previews if len(p.operational_caveats) > 0
    )
    return TrueMomentumStrategyPreviewSummary(
        candidate_count=len(candidates),
        preview_count=len(previews),
        continuation_count=continuation,
        pullback_count=pullback,
        reversal_watch_count=reversal_watch,
        strong_count=strong,
        moderate_count=moderate,
        watch_count=watch,
        blocked_count=blocked,
        parity_pending_count=parity_pending,
        derived_higher_timeframe_count=derived_htf,
        operational_caveat_count=operational_caveat_count,
    )


def evaluate_true_momentum_strategy_preview(
    settings: Any,
    *,
    candidates: Any = None,
) -> dict[str, Any]:
    """Return a non-actionable preview payload.

    Phase C1: when effective mode is ``research_preview`` the existing
    queue candidates are *classified* into the three planned True
    Momentum strategy families (continuation, pullback, reversal /
    weakening watch). Disabled / active modes return no preview rows
    and the appropriate reason code.

    Pure / read-only:

    - never mutates ``candidates`` or ``settings``,
    - never opens a network socket,
    - never reads market data,
    - never raises on bad input — invalid rows degrade to no preview.
    """
    status = build_true_momentum_strategy_status(settings)
    safe_candidates: list[Any] = []
    if candidates is not None:
        try:
            iterator = list(candidates)
        except TypeError:
            iterator = []
        for raw in iterator:
            if raw is None:
                continue
            safe_candidates.append(raw)

    extra_reason_codes: list[str] = []
    previews: list[TrueMomentumStrategyPreviewCandidate] = []

    if status.effective_mode == "disabled":
        extra_reason_codes.append(REASON_TRUE_MOMENTUM_STRATEGY_MODE_DISABLED)
        if status.requested_mode == "active":
            extra_reason_codes.append(REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED)
        previews_generated = False
    else:
        # research_preview effective mode (including degraded active).
        for raw in safe_candidates:
            norm = _normalize_candidate(raw)
            if norm is None:
                continue
            # Precedence: reversal_watch > pullback > continuation.
            matched_rw, reasons_rw, notes_rw = _classify_reversal_watch(norm)
            if matched_rw:
                previews.append(
                    _build_preview_row(
                        norm,
                        "true_momentum_reversal_watch",
                        reasons_rw,
                        notes_rw,
                        "watch",
                    )
                )
                continue
            matched_pb, reasons_pb, notes_pb, strength_pb = _classify_pullback(norm)
            if matched_pb:
                previews.append(
                    _build_preview_row(
                        norm,
                        "true_momentum_pullback",
                        reasons_pb,
                        notes_pb,
                        strength_pb,
                    )
                )
                continue
            matched_ct, reasons_ct, notes_ct, strength_ct = _classify_continuation(norm)
            if matched_ct:
                previews.append(
                    _build_preview_row(
                        norm,
                        "true_momentum_continuation",
                        reasons_ct,
                        notes_ct,
                        strength_ct,
                    )
                )
                continue
            # No family matched — record as a non-emitted "no match" row?
            # Phase C1 keeps the preview list tight; we surface this
            # via the summary's candidate_count vs preview_count gap.
        previews_generated = True
        if status.requested_mode == "active":
            extra_reason_codes.append(REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED)
        if len(previews) == 0:
            extra_reason_codes.append(REASON_TRUE_MOMENTUM_PREVIEW_NO_CANDIDATES)

    summary = _summarize_previews(safe_candidates, previews)
    guardrails = _GUARDRAILS + (
        "Phase C1 only classifies already-loaded queue candidates; it does not "
        "generate new queue candidates.",
    )
    # Re-dump the status with the additional Phase C1 reason codes
    # appended so the result's status block is self-describing.
    augmented_status = TrueMomentumStrategyStatus(
        requested_mode=status.requested_mode,
        effective_mode=status.effective_mode,
        enabled=status.enabled,
        guard_enabled=status.guard_enabled,
        invalid_env_value=status.invalid_env_value,
        mode_env_var=status.mode_env_var,
        guard_env_var=status.guard_env_var,
        reason_codes=tuple(list(status.reason_codes) + extra_reason_codes),
        guardrails=guardrails,
        family_specs=status.family_specs,
        phase=status.phase,
        implementation_status=status.implementation_status,
        parity_status=status.parity_status,
        parity_required_for_active=status.parity_required_for_active,
    )

    result = TrueMomentumStrategyPreviewResult(
        status=augmented_status,
        previews=tuple(previews),
        previews_generated=previews_generated,
        summary=summary,
        guardrails=guardrails,
        phase=PHASE,
        implementation_status=IMPLEMENTATION_STATUS,
        preview_phase=PREVIEW_PHASE,
        preview_implementation_status=PREVIEW_IMPLEMENTATION_STATUS,
        deterministic_note=PREVIEW_DETERMINISTIC_NOTE,
    )

    # Preserve the Phase C0 dict shape callers and existing tests expect
    # while exposing the new typed result via the ``"result"`` key. The
    # dict view keeps ``previews`` flat for backward compat.
    return {
        "status": augmented_status,
        "previews": list(previews),
        "previews_generated": previews_generated,
        "summary": summary,
        "guardrails": list(guardrails),
        "phase": PHASE,
        "implementation_status": IMPLEMENTATION_STATUS,
        "preview_phase": PREVIEW_PHASE,
        "preview_implementation_status": PREVIEW_IMPLEMENTATION_STATUS,
        "deterministic_note": PREVIEW_DETERMINISTIC_NOTE,
        "result": result,
    }


__all__ = [
    "TrueMomentumStrategyMode",
    "TrueMomentumStrategyFamilySpec",
    "TrueMomentumStrategyStatus",
    "TrueMomentumStrategyPreviewCandidate",
    "TrueMomentumStrategyPreviewSummary",
    "TrueMomentumStrategyPreviewResult",
    "TrueMomentumStrategyPreviewFamilyId",
    "TrueMomentumStrategyPreviewMatchStrength",
    "PREVIEW_PHASE",
    "PREVIEW_IMPLEMENTATION_STATUS",
    "PREVIEW_DETERMINISTIC_NOTE",
    "MODE_ENV_VAR",
    "GUARD_ENV_VAR",
    "PHASE",
    "IMPLEMENTATION_STATUS",
    "REASON_TRUE_MOMENTUM_STRATEGY_MODE_BLOCKED_BY_GUARD",
    "REASON_TRUE_MOMENTUM_ACTIVE_NOT_IMPLEMENTED",
    "REASON_INVALID_ENV_VALUE_RESOLVED_TO_DISABLED",
    "REASON_THINKORSWIM_PARITY_PENDING",
    "list_true_momentum_strategy_family_specs",
    "build_true_momentum_strategy_status",
    "evaluate_true_momentum_strategy_preview",
]

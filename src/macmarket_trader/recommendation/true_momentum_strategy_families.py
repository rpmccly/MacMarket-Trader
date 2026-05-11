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


def evaluate_true_momentum_strategy_preview(
    settings: Any,
    *,
    candidates: Any = None,
) -> dict[str, Any]:
    """Return a non-actionable preview payload for Phase C0.

    In every Phase C0 mode this returns an empty list of previews
    alongside the resolved status. It never emits entry / stop / target
    / size / approval / routing fields, and it never reads market data.

    ``candidates`` is accepted only so future C1 work can pass the
    Recommendations queue in without changing the call site signature;
    Phase C0 ignores it.
    """
    _ = candidates  # forward-compat placeholder; never consumed in C0.
    status = build_true_momentum_strategy_status(settings)
    return {
        "status": status,
        "previews": [],
        "previews_generated": False,
        "phase": PHASE,
        "implementation_status": IMPLEMENTATION_STATUS,
        "deterministic_note": (
            "Phase C0 is scaffold-only. No entries, stops, targets, "
            "or approvals are produced. No queue candidates are emitted."
        ),
    }


__all__ = [
    "TrueMomentumStrategyMode",
    "TrueMomentumStrategyFamilySpec",
    "TrueMomentumStrategyStatus",
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

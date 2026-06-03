"""Phase C6 True Momentum applicability annotations for reviews.

This module is pure and read-only. It classifies already-built
recommendation / symbol-analysis rows into True Momentum research
families for operator review surfaces. It does not generate candidates,
rank strategies, approve, size, route, or create paper orders.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace
from typing import Any, Literal

from macmarket_trader.recommendation.true_momentum_strategy_families import (
    TrueMomentumStrategyPreviewCandidate,
    evaluate_true_momentum_strategy_preview,
)

TrueMomentumApplicabilityFamilyId = Literal[
    "true_momentum_continuation",
    "true_momentum_pullback",
    "true_momentum_reversal_watch",
]

TrueMomentumApplicabilityStatus = Literal[
    "applicable_research_preview",
    "watch_only",
    "blocked_by_warning",
    "blocked_by_parity",
    "blocked_by_composite_mismatch",
    "insufficient_evidence",
    "not_applicable",
]

FAMILY_LABELS: dict[TrueMomentumApplicabilityFamilyId, str] = {
    "true_momentum_continuation": "True Momentum Continuation",
    "true_momentum_pullback": "True Momentum Pullback",
    "true_momentum_reversal_watch": "True Momentum Reversal / Weakening Watch",
}

FAMILY_ORDER: tuple[TrueMomentumApplicabilityFamilyId, ...] = (
    "true_momentum_continuation",
    "true_momentum_pullback",
    "true_momentum_reversal_watch",
)

PHASE = "C6"
IMPLEMENTATION_STATUS = "research_applicability_only"
DETERMINISTIC_NOTE = (
    "True Momentum applicability is non-actionable review context. It does "
    "not create queue candidates, approve, size, route, or create orders."
)

_PREVIEW_SETTINGS = SimpleNamespace(
    true_momentum_strategy_mode="research_preview",
    allow_true_momentum_strategy_families=True,
)

_COMPOSITE_MISMATCH_MARKERS = (
    "composite_mismatch",
    "xlp_composite_mismatch",
    "oscillator_aligned_composite_mismatch",
    "momentum_composite_mismatch",
)
_PARITY_FAILURE_MARKERS = (
    "parity_failed",
    "parity_mismatch",
    "tos_reference_mismatch",
    "thinkorswim_mismatch",
)


@dataclass(frozen=True)
class TrueMomentumApplicability:
    """Non-actionable applicability row surfaced in review payloads."""

    family_id: TrueMomentumApplicabilityFamilyId
    label: str
    status: TrueMomentumApplicabilityStatus
    match_strength: str
    direction: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    non_actionable: bool = True
    symbol: str | None = None
    strategy: str | None = None
    rank: int | None = None
    preview_id: str | None = None
    research_notes: tuple[str, ...] = field(default_factory=tuple)
    source_phase: str = PHASE
    implementation_status: str = IMPLEMENTATION_STATUS
    deterministic_note: str = DETERMINISTIC_NOTE

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        payload["blockers"] = list(self.blockers)
        payload["research_notes"] = list(self.research_notes)
        return payload


def _get(candidate: Any, key: str, default: Any = None) -> Any:
    if candidate is None:
        return default
    if isinstance(candidate, Mapping):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    try:
        return [str(item) for item in value if item is not None]
    except TypeError:
        return []


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item) for item in values if str(item).strip()))


def _safe_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _candidate_identity(candidate: Any) -> tuple[str | None, str | None, int | None]:
    symbol_raw = _get(candidate, "symbol")
    strategy_raw = _get(candidate, "strategy")
    symbol = str(symbol_raw).upper() if symbol_raw else None
    strategy = str(strategy_raw).strip() if strategy_raw else None
    return symbol, strategy, _safe_int_or_none(_get(candidate, "rank"))


def _momentum_contribution(candidate: Any) -> Any:
    return _get(candidate, "momentum_contribution")


def _has_momentum_evidence(candidate: Any) -> bool:
    contribution = _momentum_contribution(candidate)
    if contribution is None:
        return False
    evidence_keys = (
        "total_score",
        "total_label",
        "trend_score",
        "momo_score",
        "inferred_direction",
        "raw_total_contribution",
        "shadow_contribution",
    )
    for key in evidence_keys:
        value = _get(contribution, key)
        if value not in (None, "", "unknown"):
            return True
    return False


def _candidate_reason_codes(candidate: Any) -> list[str]:
    contribution = _momentum_contribution(candidate)
    reasons = _string_list(_get(contribution, "reason_codes"))
    reasons.extend(_string_list(_get(candidate, "reason_codes")))
    return reasons


def _warning_blockers(candidate: Any, risk_context: Any = None) -> tuple[str, ...]:
    blockers: list[str] = []
    contribution = _momentum_contribution(candidate)
    if bool(_get(contribution, "reversal_warning")):
        blockers.append("momentum_reversal_warning")
    if bool(_get(contribution, "no_trade_warning")):
        blockers.append("momentum_no_trade_warning")

    risk = risk_context if risk_context is not None else _get(candidate, "risk_calendar")
    decision = _get(risk, "decision", {}) if risk is not None else {}
    allow_new = _get(decision, "allow_new_entries")
    decision_state = str(_get(decision, "decision_state", "") or "").lower()
    risk_level = str(_get(decision, "risk_level", "") or "").lower()
    block_reason = _get(decision, "block_reason") or _get(decision, "warning_summary")
    if allow_new is False:
        blockers.append("risk_calendar_disallows_new_entries")
    if decision_state and decision_state != "normal":
        blockers.append(f"risk_calendar_{decision_state}")
    if risk_level in {"warning", "restricted", "caution"}:
        blockers.append(f"risk_level_{risk_level}")
    if block_reason:
        blockers.append(str(block_reason)[:120])
    return _dedupe(blockers)


def _parity_blockers(
    candidate: Any,
    parity_context: Any = None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    reasons = _candidate_reason_codes(candidate)
    for reason in reasons:
        lower = reason.lower()
        if any(marker in lower for marker in _PARITY_FAILURE_MARKERS):
            blockers.append(reason)
    if parity_context is not None:
        verdict = str(_get(parity_context, "verdict", "") or "").lower()
        status = str(_get(parity_context, "status", "") or "").lower()
        if verdict in {"mismatch", "tos_reference_mismatch", "failed"}:
            blockers.append(f"parity_{verdict}")
        if status in {"failed", "mismatch"}:
            blockers.append(f"parity_{status}")
    return _dedupe(blockers)


def _composite_blockers(candidate: Any) -> tuple[str, ...]:
    blockers: list[str] = []
    for reason in _candidate_reason_codes(candidate):
        lower = reason.lower()
        if any(marker in lower for marker in _COMPOSITE_MISMATCH_MARKERS):
            blockers.append(reason)
    return _dedupe(blockers)


def _status_for_preview(
    preview: TrueMomentumStrategyPreviewCandidate,
    *,
    warning_blockers: tuple[str, ...],
    parity_blockers: tuple[str, ...],
    composite_blockers: tuple[str, ...],
) -> tuple[TrueMomentumApplicabilityStatus, tuple[str, ...]]:
    if composite_blockers:
        return "blocked_by_composite_mismatch", composite_blockers
    if parity_blockers:
        return "blocked_by_parity", parity_blockers
    if warning_blockers and preview.family_id != "true_momentum_reversal_watch":
        return "blocked_by_warning", warning_blockers
    if preview.family_id == "true_momentum_reversal_watch":
        return "watch_only", _dedupe((*warning_blockers, "watch_only"))
    return "applicable_research_preview", ()


def _row_for_family(
    family_id: TrueMomentumApplicabilityFamilyId,
    *,
    status: TrueMomentumApplicabilityStatus,
    match_strength: str,
    direction: str,
    symbol: str | None,
    strategy: str | None,
    rank: int | None,
    reason_codes: Sequence[str] = (),
    blockers: Sequence[str] = (),
    preview_id: str | None = None,
    research_notes: Sequence[str] = (),
) -> TrueMomentumApplicability:
    return TrueMomentumApplicability(
        family_id=family_id,
        label=FAMILY_LABELS[family_id],
        status=status,
        match_strength=match_strength,
        direction=direction,
        reason_codes=_dedupe(reason_codes),
        blockers=_dedupe(blockers),
        symbol=symbol,
        strategy=strategy,
        rank=rank,
        preview_id=preview_id,
        research_notes=_dedupe(research_notes),
        non_actionable=True,
    )


def _preview_rows(candidate: Any) -> dict[str, TrueMomentumStrategyPreviewCandidate]:
    result = evaluate_true_momentum_strategy_preview(
        _PREVIEW_SETTINGS,
        candidates=[candidate],
    )
    previews = result.get("previews") if isinstance(result, dict) else []
    rows: dict[str, TrueMomentumStrategyPreviewCandidate] = {}
    for preview in previews or []:
        if isinstance(preview, TrueMomentumStrategyPreviewCandidate):
            rows[preview.family_id] = preview
    return rows


def evaluate_true_momentum_applicability(
    candidate: Any,
    *,
    risk_context: Any = None,
    parity_context: Any = None,
) -> list[TrueMomentumApplicability]:
    """Return non-actionable C6 applicability rows for one review item."""

    symbol, strategy, rank = _candidate_identity(candidate)
    warning_blockers = _warning_blockers(candidate, risk_context)
    parity_blockers = _parity_blockers(candidate, parity_context)
    composite_blockers = _composite_blockers(candidate)
    has_evidence = _has_momentum_evidence(candidate)
    previews = _preview_rows(candidate) if has_evidence else {}

    rows: list[TrueMomentumApplicability] = []
    for family_id in FAMILY_ORDER:
        preview = previews.get(family_id)
        if preview is not None:
            status, blockers = _status_for_preview(
                preview,
                warning_blockers=warning_blockers,
                parity_blockers=parity_blockers,
                composite_blockers=composite_blockers,
            )
            rows.append(
                _row_for_family(
                    family_id,
                    status=status,
                    match_strength=preview.match_strength,
                    direction=(
                        "watch"
                        if family_id == "true_momentum_reversal_watch"
                        else preview.inferred_direction
                    ),
                    symbol=preview.symbol,
                    strategy=preview.strategy,
                    rank=preview.rank,
                    reason_codes=preview.reason_codes,
                    blockers=blockers,
                    preview_id=preview.preview_id,
                    research_notes=preview.research_notes,
                )
            )
            continue
        if not has_evidence:
            status = "insufficient_evidence"
            match_strength = "none"
            direction = "unknown"
            reasons = ("true_momentum_evidence_missing",)
            blockers = ("momentum_contribution_missing",)
        elif warning_blockers and family_id != "true_momentum_reversal_watch":
            status = "blocked_by_warning"
            match_strength = "blocked"
            direction = "long" if family_id != "true_momentum_reversal_watch" else "watch"
            reasons = ("warning_blocks_family_applicability",)
            blockers = warning_blockers
        elif parity_blockers:
            status = "blocked_by_parity"
            match_strength = "blocked"
            direction = "unknown"
            reasons = ("parity_blocks_family_applicability",)
            blockers = parity_blockers
        elif composite_blockers:
            status = "blocked_by_composite_mismatch"
            match_strength = "blocked"
            direction = "unknown"
            reasons = ("composite_mismatch_blocks_family_applicability",)
            blockers = composite_blockers
        else:
            status = "not_applicable"
            match_strength = "none"
            direction = "watch" if family_id == "true_momentum_reversal_watch" else "unknown"
            reasons = ("true_momentum_no_family_match",)
            blockers = ()
        rows.append(
            _row_for_family(
                family_id,
                status=status,
                match_strength=match_strength,
                direction=direction,
                symbol=symbol,
                strategy=strategy,
                rank=rank,
                reason_codes=reasons,
                blockers=blockers,
            )
        )
    return rows


def evaluate_true_momentum_applicability_payload(
    candidate: Any,
    *,
    risk_context: Any = None,
    parity_context: Any = None,
) -> list[dict[str, Any]]:
    return [
        row.to_payload()
        for row in evaluate_true_momentum_applicability(
            candidate,
            risk_context=risk_context,
            parity_context=parity_context,
        )
    ]


def attach_true_momentum_applicability(
    candidates: Sequence[dict[str, Any]],
) -> None:
    """Annotate already-ranked candidate dicts in place.

    The mutation is limited to adding review metadata to existing rows.
    It never creates new candidate rows and never touches ranking fields.
    """

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate["true_momentum_applicability"] = (
            evaluate_true_momentum_applicability_payload(
                candidate,
                risk_context=candidate.get("risk_calendar"),
            )
        )


__all__ = [
    "DETERMINISTIC_NOTE",
    "FAMILY_LABELS",
    "FAMILY_ORDER",
    "IMPLEMENTATION_STATUS",
    "PHASE",
    "TrueMomentumApplicability",
    "TrueMomentumApplicabilityFamilyId",
    "TrueMomentumApplicabilityStatus",
    "attach_true_momentum_applicability",
    "evaluate_true_momentum_applicability",
    "evaluate_true_momentum_applicability_payload",
]

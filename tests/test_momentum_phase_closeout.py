"""Static closeout tests for Momentum Intelligence Phase A/B.

These tests are documentation contracts. They pin the operator-facing
closeout copy so that:

- Phase A/B closeout is explicitly named,
- the three active-mode env vars are documented,
- Thinkorswim parity is recorded as still pending,
- Phase C is recorded as not active and not generating recommendations,
- the deterministic safety posture (no approval / order behavior change,
  paper-order creation remains manual) is preserved, and
- no actionable trade-direction or order-routing language appears in
  the operator-facing docs.

They do not exercise ranking math, indicator math, or paper-order
behavior.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
LAYER_DOC = DOCS_DIR / "momentum-intelligence-layer.md"
CLOSEOUT_DOC = DOCS_DIR / "momentum-phase-closeout.md"
PHASE_C_DOC = DOCS_DIR / "true-momentum-strategy-families.md"

ACTIVE_MODE_ENV_VARS = (
    "MACMARKET_MOMENTUM_RANKING_MODE",
    "MACMARKET_ALLOW_MOMENTUM_ACTIVE_RANKING",
    "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE",
)

FORBIDDEN_ACTION_PHRASES = (
    "auto approve",
    "auto-approve",
    "buy now",
    "sell now",
    "enter now",
    "short now",
    "route order",
    "place order",
    "submit order",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize_whitespace(text: str) -> str:
    """Collapse newlines / runs of whitespace so phrase checks survive
    Markdown soft wraps (e.g. "remains\nmanual" → "remains manual")."""
    return " ".join(text.split())


def _layer_closeout_section() -> str:
    body = _read(LAYER_DOC)
    start_marker = "## Phase A/B Closeout"
    end_marker = "## Phase C0"  # the immediately following section
    if end_marker not in body:
        end_marker = "## Future phases"
    start = body.index(start_marker)
    end = body.index(end_marker, start) if end_marker in body[start:] else len(body)
    return body[start:end]


# ── Phase A/B closeout copy lives in the canonical doc ─────────────────


def test_layer_doc_contains_phase_a_b_closeout_section() -> None:
    body = _read(LAYER_DOC)
    assert "## Phase A/B Closeout" in body


def test_layer_doc_documents_all_three_active_mode_env_vars() -> None:
    body = _read(LAYER_DOC)
    for env_var in ACTIVE_MODE_ENV_VARS:
        assert env_var in body, f"{env_var} must be documented in {LAYER_DOC}"


def test_layer_doc_records_thinkorswim_parity_pending() -> None:
    body = _read(LAYER_DOC).lower()
    assert "thinkorswim" in body
    assert "parity" in body
    assert "pending" in body


def test_layer_doc_records_phase_c_is_not_active() -> None:
    body = _read(LAYER_DOC)
    # Both the strong copy + the explicit-statement bullets.
    assert "Phase C is not active." in body
    assert "Phase C strategies are not generating queue candidates." in body
    assert "Phase C does not approve, reject, size, or route trades." in body


def test_layer_doc_records_no_approval_or_order_behavior_change() -> None:
    section = _normalize_whitespace(_layer_closeout_section().lower())
    assert "no approval behavior change" in section
    assert "no paper-order behavior change" in section
    assert "paper-order creation remains manual" in section


def test_layer_doc_records_active_delta_scale_default() -> None:
    body = _read(LAYER_DOC)
    # Both the active-mode env var line and the recommended-values
    # codeblock mention 0.35.
    assert "0.35" in body
    assert "MACMARKET_MOMENTUM_ACTIVE_DELTA_SCALE" in body


def test_layer_doc_records_active_queue_consistency_guard() -> None:
    body = _read(LAYER_DOC).lower()
    assert "queue-response consistency guard" in body or "queue response consistency guard" in body


def test_layer_doc_records_active_trial_journal() -> None:
    body = _read(LAYER_DOC)
    assert "Active Momentum Trial Journal" in body


def test_layer_doc_phase_a_b_closeout_section_has_no_action_language() -> None:
    # Narrow to the new Phase A/B closeout section. Earlier sections
    # legitimately enumerate the forbidden phrase list when describing
    # the operator-note sanitizer ("the journal can never publish
    # trade-direction action language even through an operator note");
    # those references are anti-action copy, not action incentives.
    section = _layer_closeout_section().lower()
    for phrase in FORBIDDEN_ACTION_PHRASES:
        assert phrase not in section, (
            f"forbidden phrase {phrase!r} appears in the Phase A/B closeout section"
        )


# ── Operator-friendly companion doc ───────────────────────────────────


def test_closeout_doc_exists_and_records_closeout_scope() -> None:
    body = _read(CLOSEOUT_DOC)
    assert "Phase A/B Closeout" in body
    # Operator-friendly knobs must appear.
    for env_var in ACTIVE_MODE_ENV_VARS:
        assert env_var in body
    # Outstanding items must include the Thinkorswim parity work.
    body_lower = body.lower()
    assert "thinkorswim" in body_lower
    assert "parity" in body_lower
    # Phase C posture must remain explicit.
    assert "Phase C is **not active**" in body
    assert "Phase C strategies do **not** generate queue candidates." in body


def test_closeout_doc_documents_active_delta_scale_default() -> None:
    body = _read(CLOSEOUT_DOC)
    assert "0.35" in body


def test_closeout_doc_records_paper_order_manual() -> None:
    body = _read(CLOSEOUT_DOC).lower()
    assert "paper-order creation remains manual" in body


def test_closeout_doc_has_no_action_language() -> None:
    body = _read(CLOSEOUT_DOC).lower()
    for phrase in FORBIDDEN_ACTION_PHRASES:
        assert phrase not in body


# ── Phase C0 doc must exist and stay scaffold-only ─────────────────────


def test_phase_c_doc_exists_and_records_scaffold_only_posture() -> None:
    body = _read(PHASE_C_DOC)
    assert "Phase C0" in body
    assert "scaffolding only" in body.lower()
    # All three planned families must be named.
    assert "True Momentum Continuation" in body
    assert "True Momentum Pullback" in body
    assert "True Momentum Reversal / Weakening Watch" in body
    # Env vars are documented.
    assert "MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE" in body
    assert "MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES" in body
    # Non-goals are explicit.
    body_lower = body.lower()
    assert "no queue generation" in body_lower
    assert "no paper-order creation" in body_lower
    assert "no live trading" in body_lower


def test_phase_c_doc_links_back_to_layer_charter() -> None:
    body = _read(PHASE_C_DOC)
    assert "momentum-intelligence-layer.md" in body
    assert "momentum-phase-closeout.md" in body


def test_phase_c_doc_has_no_action_language() -> None:
    body = _read(PHASE_C_DOC).lower()
    for phrase in FORBIDDEN_ACTION_PHRASES:
        assert phrase not in body


def test_layer_doc_links_to_phase_c_doc() -> None:
    body = _read(LAYER_DOC)
    assert "true-momentum-strategy-families.md" in body
    assert "momentum-phase-closeout.md" in body


# ── Phase B8.1 copy polish: B8 feature implemented, evidence corpus pending ──


def test_layer_doc_records_b8_feature_implemented() -> None:
    body = _read(LAYER_DOC)
    lowered = _normalize_whitespace(body.lower())
    # The Phase B8 section names the feature explicitly and the
    # Outstanding-items list must not claim the active trial outcome
    # review itself is unimplemented.
    assert "phase b8 — active momentum trial outcome review" in lowered
    assert (
        "accumulated b8 outcome evidence" in lowered
        or ("accumulated corpus" in lowered and "phase b8" in lowered)
    )


def test_layer_doc_does_not_imply_b8_feature_is_missing() -> None:
    # After B8.1 the Outstanding section must not include a bullet that
    # implies the review feature itself is still TODO.
    section = _layer_closeout_section().lower()
    assert "active trial outcome tagging" not in section
    assert "may add operator-side tagging" not in section


def test_closeout_doc_records_b8_feature_implemented() -> None:
    body = _read(CLOSEOUT_DOC)
    assert "Phase B8 Active Momentum Trial Outcome Review (feature" in body
    # Outstanding items must name the *corpus*, not the feature.
    lowered = body.lower()
    assert "accumulated b8 outcome evidence corpus" in lowered
    # Implemented bucket must mention B8.
    assert "## Implemented" in body


def test_closeout_doc_does_not_imply_b8_feature_is_missing() -> None:
    lowered = _read(CLOSEOUT_DOC).lower()
    # The previous stale strikethrough / pending wording is gone.
    assert "active-trial outcome tagging / review of the trial journal" not in lowered
    assert "active trial outcome review" not in lowered or (
        "feature implemented" in lowered
    )


def test_phase_c_doc_records_b8_feature_implemented() -> None:
    body = _read(PHASE_C_DOC)
    lowered = _normalize_whitespace(body.lower())
    # The Phase C0 doc's "Prerequisites before C1" section must
    # acknowledge B7+B8 already ship and name the corpus as pending.
    assert "phase b8" in lowered
    assert "outcome review" in lowered
    assert "accumulated corpus" in lowered
    # The "feature already implemented" framing is present so a reader
    # of the C0 doc does not interpret outcome-review as TODO.
    assert "already implemented" in lowered


# ── Phase C research closeout doc contract ─────────────────────────────────


PHASE_C_CLOSEOUT_DOC = DOCS_DIR / "true-momentum-phase-c-closeout.md"
PARITY_DOC = DOCS_DIR / "thinkorswim-momentum-parity.md"


def test_phase_c_closeout_doc_exists_and_records_research_only_posture() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC)
    lowered = _normalize_whitespace(body.lower())
    # Doc explicitly names the research-only closeout posture.
    assert "research-only" in lowered or "research only" in lowered
    # Active Phase C is not implemented.
    assert "active phase c strategy generation remains reserved" in lowered
    assert "not implemented" in lowered
    # No queue candidates are generated.
    assert (
        "no queue candidates are generated" in lowered
        or "no true momentum queue candidates are generated" in lowered
        or "true momentum queue candidate generation" in lowered
    )
    # Approval / paper-order behavior unchanged. Permissive: accept
    # any of the three idiomatic phrasings, with or without markdown
    # emphasis markers around "unchanged".
    stripped = lowered.replace("**", "")
    assert (
        "recommendation approval and paper-order behavior remain" in stripped
        or "recommendation approval and paper-order behavior are unchanged" in stripped
        or "paper-order behavior: unchanged" in stripped
    )


def test_phase_c_closeout_doc_records_xlp_oscillator_aligned_composite_mismatch() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC)
    lowered = _normalize_whitespace(body.lower())
    assert "xlp" in lowered
    assert "oscillator_aligned" in lowered or "oscillator aligned" in lowered
    assert "composite_mismatch" in lowered or "composite mismatch" in lowered


def test_phase_c_closeout_doc_records_b8_and_c3_prerequisites() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC)
    lowered = _normalize_whitespace(body.lower())
    assert "b8 outcome evidence" in lowered
    assert "c3 cohort" in lowered
    assert "operator authorization" in lowered


def test_phase_c_closeout_doc_has_no_live_trading_language() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC).lower()
    forbidden = (
        "ready for live",
        "approve trade",
        "auto approve",
        "route order",
        "place order",
        "buy now",
        "sell now",
        "enter now",
        "short now",
    )
    for phrase in forbidden:
        assert phrase not in body, (
            f"phase C closeout doc must not contain {phrase!r}"
        )


def test_phase_c_closeout_doc_recommends_c5_research_candidate_proposal_only() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC)
    lowered = _normalize_whitespace(body.lower())
    assert "c5" in lowered
    assert "research candidate proposal" in lowered
    assert "non-active" in lowered
    assert "non-ordering" in lowered


def test_related_docs_link_back_to_phase_c_closeout_doc() -> None:
    for doc in (LAYER_DOC, CLOSEOUT_DOC, PHASE_C_DOC, PARITY_DOC):
        body = _read(doc).lower()
        assert "true-momentum-phase-c-closeout.md" in body, (
            f"{doc.name} must link to true-momentum-phase-c-closeout.md"
        )


def test_phase_c_closeout_doc_lists_canonical_shipped_phases() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC)
    for phase in ("C0", "C1", "C2", "C2.1", "C2.2", "C3", "C4", "C4.1"):
        assert phase in body, f"closeout doc must list shipped phase {phase}"


# ── Phase C5 research candidate proposal doc contract ──────────────────


def test_phase_c_closeout_doc_records_c5_research_candidate_proposal_shipped() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC)
    lowered = _normalize_whitespace(body.lower())
    assert "c5" in lowered
    # The next-allowed-phase section preserves the C5 description.
    assert "research candidate proposal" in lowered
    # Research-only / non-active / non-ordering remain explicit.
    assert "non-active" in lowered
    assert "non-ordering" in lowered


def test_phase_c_closeout_doc_records_c5_does_not_change_queue_or_orders() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC).lower()
    # Either the canonical "C5 must not generate queue candidates"
    # statement or a paraphrase that names queue / orders / paper.
    assert (
        "must not generate queue candidates" in body
        or "do not enter the ranked queue" in body
        or "non-active and non-ordering" in body
    )


def test_phase_c_closeout_doc_has_no_live_trading_language_around_c5() -> None:
    body = _read(PHASE_C_CLOSEOUT_DOC).lower()
    for forbidden in FORBIDDEN_ACTION_PHRASES:
        assert forbidden not in body, (
            f"phase C closeout doc (incl. C5 section) must not contain {forbidden!r}"
        )

# True Momentum — Phase C research closeout

This document records the **research-only** closeout of the True
Momentum Phase C work in the Momentum Intelligence Layer. Phase C is
explicitly **not** ready for active trading. Active Phase C strategy
generation remains reserved and is not implemented.

## What shipped (research-only)

| Phase | Surface | Purpose |
|---|---|---|
| **C0** | `true_momentum_strategy_families` Pydantic spec + status endpoint | Scaffolding only — three planned families, all `status: research_preview`, `generates_candidates: false`, `activation: reserved`. |
| **C1** | `apps/web/lib/true-momentum-strategy-preview.ts` + preview panel | Read-only classifier that labels the existing Recommendations queue as `true_momentum_continuation` / `true_momentum_pullback` / `true_momentum_reversal_watch`. No queue mutation. |
| **C2** | `apps/web/lib/true-momentum-preview-evidence.ts` + evidence panel | Local/export-only preview evidence bundle (JSON / Markdown) for a single research session. |
| **C2.1** | B7 trial snapshot + B8 outcome linkage on the evidence bundle | Captures the deterministic state of the queue + outcomes tagged by the operator. |
| **C2.2** | Live B7/B8 lift into the Recommendations page | Snapshot and outcome review are lifted to the page so the C2 bundle reads live state without localStorage round-trips. |
| **C3** | `apps/web/lib/true-momentum-cohort-review.ts` + cohort panel | Local cohort archive across sessions; emits a readiness label (`insufficient_evidence` / `parity_blocked` / `promising_research` / …). Strongest positive is `promising_research`. |
| **C4** | `apps/web/lib/true-momentum-strategy-context.ts` + context card | Selected-candidate True Momentum context: family-fit badge, match strength, trigger-readiness checklist, parity/evidence caveats, activation-readiness classification. Activation readiness is research context only. |
| **C4.1** | Recommendations page UX consolidation | C4 card is now the primary selected-candidate surface; C1/C2/C3 + B7/B8 live in a collapsible "True Momentum research evidence" section; Shadow Impact Review collapses under "Momentum ranking diagnostics". |
| **C4.2** | Composite-mismatch drilldown on the C4 card | When the selected symbol's parity summary carries `oscillator_aligned` + `composite_mismatch`, the card surfaces a dedicated "Composite score mismatch under review" diagnostic block with ToS/MM totals, MM component attribution (when captured), and the suggested interpretation. Diagnostic-only — never alters readiness logic for unrelated symbols. |
| **C (closeout)** | `apps/web/lib/true-momentum-phase-c-closeout.ts` + closeout card | Operator-readable summary of the closeout posture, blockers, and the next allowed research phase. |

## What is explicitly NOT shipped

- **Active True Momentum strategy generation.** No active generator function exists. The three planned families remain `status: research_preview`, `generates_candidates: false`, `activation: reserved`.
- **True Momentum queue candidate generation.** Phase C surfaces never mutate or extend the Recommendations queue.
- **Auto approval.** Operator approval remains manual.
- **Auto sizing.** Sizing remains operator-controlled per the deterministic Phase A/B risk path.
- **Order routing.** Order intent / OMS / paper broker behavior is unchanged.

The closeout helper / card / docs all carry the deterministic note:

> Phase C research closeout is operator readiness context only. It
> does not generate queue candidates, and does not approve, reject,
> size, or route trades. It also does not activate Phase C strategy
> families.

## Current parity state

| Symbol | Status | Notes |
|---|---|---|
| SPY | `visual_attested` | Oscillator + composite aligned. |
| XLK | `visual_attested` | Oscillator + composite aligned. |
| XLE | `visual_attested` | Oscillator + composite aligned. |
| XLP | `visual_failed` | `oscillator_aligned` + `composite_mismatch` — True Momentum / EMA align within tolerance, but the composite total score differs (ToS 35 Neutral vs MM 65 Neutral Up). |

The XLP composite mismatch is a research item — **not** a reason to widen tolerances. See [`thinkorswim-momentum-parity.md`](thinkorswim-momentum-parity.md) for the composite attribution diagnostic and the recommended next capture (MM `true_momentum_score` / `hilo_score` / `atr_bias` / `macd_bias` / `ma_bias` plus close-price context). The C4.2 drilldown surfaces this for the operator directly on the Recommendations page when the XLP candidate is selected.

## Blockers before active Phase C is even considered

1. **Resolve / document the XLP composite mismatch.** Capture MM's composite breakdown + close-price context, then either reconcile or record the divergence as a known research delta.
2. **Accumulate the B8 outcome evidence corpus.** A representative cross-sector / cross-regime corpus of tagged outcomes must exist before any activation decision.
3. **Accumulate C3 cohort evidence.** The cohort archive must reach a representative sector / regime mix.
4. **Operator authorization.** Explicit, per-family operator authorization is required. Activation is never automatic.

The closeout helper enumerates these as `parity_mixed`, `insufficient_b8_evidence`, `insufficient_c3_cohort`, `operator_authorization_required`, and `active_generation_not_implemented` blockers.

## Recommended next phase — C5 research candidate proposal

The next allowed research phase is **C5 — research candidate proposal**:

- Still **non-active** and **non-ordering**.
- May propose research candidates surfaced separately from the live queue (no queue mutation).
- Still gated behind operator authorization, an accumulated B8 outcome evidence corpus, and a representative C3 cohort review.

C5 must not generate queue candidates, and must not approve, reject, size, or route trades.

## Behavior guarantees

- Ranking math: **unchanged**.
- Queue sorting: **unchanged**.
- Recommendation approval behavior: **unchanged**.
- Paper-order behavior: **unchanged**.
- Backend scoring: **unchanged**.
- Momentum indicator math: **unchanged**.
- Active Phase C: **not implemented** — reserved behind the existing C0 mode + safety guard env vars.

## Related documents

- [`momentum-intelligence-layer.md`](momentum-intelligence-layer.md) — full Momentum charter.
- [`true-momentum-strategy-families.md`](true-momentum-strategy-families.md) — Phase C charter, family specs, C4 contract, C4.1 UX consolidation.
- [`momentum-phase-closeout.md`](momentum-phase-closeout.md) — operator checklist summary across the Phase A/B/C0/C1/C2/C3/C4/C4.1/C closeout work.
- [`thinkorswim-momentum-parity.md`](thinkorswim-momentum-parity.md) — visual-attestation parity workflow + XLP composite-mismatch interpretation.

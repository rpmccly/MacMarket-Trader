# True Momentum Strategy Families — Phase C0 (scaffolding only)

Phase C0 is the **scaffolding-only** introduction of the True Momentum
strategy-family concept. It exists to:

- pin a stable set of family specs the operator can review,
- expose a read-only resolved-mode status (with guardrails and reason
  codes), and
- keep the Recommendations / paper-order / approval / replay surfaces
  byte-identical to Phase B closeout.

It explicitly does **not**:

- generate recommendations,
- create queue candidates,
- approve, reject, size, route, open, close, or settle trades,
- mutate state, hit a provider, or call market data,
- call an LLM,
- add or require Thinkorswim parity fixture CSVs,
- change ranking math, queue sorting, recommendation approval, or
  paper-order behavior.

## C0 purpose

Phase C0 records what the future True Momentum strategy families will
look like so that:

1. operator authorization can be obtained against an explicit list,
2. the dependency graph between Phase B closeout, Thinkorswim parity,
   and Phase C1 activation is visible, and
3. the frontend can render a "planned families" status card without
   any actionable copy or queue impact.

## Planned families

| Family ID | Label | Intent |
|---|---|---|
| `true_momentum_continuation` | True Momentum Continuation | Bullish continuation when Momentum score, trend, HiLo, and inferred direction align |
| `true_momentum_pullback` | True Momentum Pullback | Bullish pullback near deterministic EMA / ATR support while overall Momentum remains strong |
| `true_momentum_reversal_watch` | True Momentum Reversal / Weakening Watch | Warning / watch family for weakening Bull/Max Bull or Bear/Max Bear transitions |

All three are at `status: "planned"`, `phase: "C0"`,
`implementation_status: "scaffold_only"`.

## Required future inputs

When Phase C1 is authorized, the planned implementations will need:

- Momentum score snapshot (current `total_score`, `total_label`,
  trend / momo components).
- Trend / HiLo state and inferred direction.
- Reversal / no-trade / pullback flags from the Phase B Momentum
  contribution.
- Risk calendar decision (`allow_new_entries`, blocker level).
- Liquidity / spread context.
- Regime / catalyst context.
- Operator authorization checkpoint per active trial cohort.

## Explicit non-goals (Phase C0)

- No queue generation.
- No approval / order behavior.
- No paper-order creation.
- No live trading.
- No active-mode behavior (`active` resolves to `research_preview`
  with the `true_momentum_strategy_active_mode_not_implemented` reason
  code).

## Prerequisites before C1

1. **Accumulated Phase B8 outcome evidence corpus.** The Phase B7
   Active Momentum Trial Journal and the Phase B8 Active Momentum
   Trial Outcome Review are both already implemented — the trial
   journal captures a deterministic snapshot of the queue, and the
   outcome review lets the operator tag each captured candidate
   (worked, missed, too aggressive, good warning, false warning,
   watchlist only, needs ToS parity check, ignored, unclear) and
   export the review as Markdown / JSON. What still remains pending
   here is the *accumulated corpus* of exported B8 reviews across a
   representative sector / regime mix.
2. **Thinkorswim spot-check / parity review.** Real Thinkorswim fixtures
   landing in `tests/fixtures/thinkorswim_momentum/` and the
   `parity_required_for_active` flag flipping to `True`.
3. **Operator authorization.** Explicit go-ahead per family.

## Env vars

| Env var | Purpose | Default |
|---|---|---|
| `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE` | `disabled` / `research_preview` / `active` | `disabled` |
| `MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES` | explicit guard for non-disabled modes | `false` |

Allowed truthy values for the guard: `true`, `1`, `yes`, `on`
(case-insensitive). Any non-truthy value forces the effective mode
back to `disabled` with the
`true_momentum_strategy_mode_blocked_by_guard` reason code.

Even with the guard truthy, `active` is reserved in Phase C0 and
resolves to `research_preview` with the
`true_momentum_strategy_active_mode_not_implemented` reason code.

## Read-only status endpoint

`GET /user/true-momentum-strategy-families/status` returns the resolved
status payload:

- `requested_mode`, `effective_mode`, `enabled`, `guard_enabled`,
  `invalid_env_value`
- `mode_env_var`, `guard_env_var`
- `reason_codes`, `guardrails`
- `family_specs` (three planned families)
- `phase: "C0"`, `implementation_status: "scaffold_only"`
- `parity_status`, `parity_required_for_active`

Requires an approved user. No DB writes. No provider / market-data
calls. No recommendation generation.

## Phase C1 — read-only research-preview classifier

Phase C1 layers a **read-only research-preview classifier** on top of
the Phase C0 scaffolding. It classifies the already-loaded
Recommendations queue into the three planned True Momentum families
without generating new queue candidates and without changing ranking,
queue sorting, approval, paper-order, replay, or options behavior.

### What it does

- Reads the current Recommendations queue (already loaded in memory).
- Normalizes each candidate's Momentum contribution (total score,
  total label, trend / momo / direction / pullback / reversal flags,
  raw contribution, applied delta, parity / derived-HTF caveats).
- Applies family rules with precedence
  **reversal_watch > pullback > continuation**:
  - `true_momentum_reversal_watch` when any of: `reversal_warning`,
    `no_trade_warning`, bear total label on a long-biased strategy, or
    `total_score ≤ -50` on a long-biased strategy. Match strength is
    always `watch`.
  - `true_momentum_pullback` when a long-biased candidate is bullish
    (`Bull` / `Max Bull` or `total_score ≥ 80`), `raw_contribution > 0`,
    no warnings, and either the `pullback_signal` flag is active or the
    source strategy is "Pullback / Trend Continuation". Strength is
    `strong` if both pullback signal and bullish label fire, otherwise
    `moderate`.
  - `true_momentum_continuation` when a long-biased candidate is
    bullish (`Bull` / `Max Bull` or `total_score ≥ 80`),
    `raw_contribution > 0`, no warnings, and not bearish. Strength is
    `strong` if both `trend_score ≥ 70` and `momo_score ≥ 70` confirm,
    otherwise `moderate`.
- Surfaces operational caveats (`thinkorswim_parity_pending`,
  `derived_higher_timeframe`, `direction_unknown`,
  `active_mode_blocked_by_safety_guard`, `score_consistency_corrected`)
  per preview row.
- Always marks every preview row `non_actionable: true` and never
  includes entry / stop / target / size / approval / order fields.

### What it does NOT do

- **No new queue candidates.** Phase C1 only *labels* existing rows.
- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 / B6 / B6.x wiring are
  byte-identical.
- **No queue sorting change.**
- **No approval, promote, save, paper-order, settle, replay, or
  options-preview behavior change.**
- **No backend mutation.** No DB write, no migration, no LLM call, no
  provider / market-data call.
- **No Phase C active behavior.** `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=active`
  is still reserved — the resolved effective mode degrades to
  `research_preview` with the
  `true_momentum_strategy_active_mode_not_implemented` reason code.

### Env to enable the read-only research preview

```env
MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=research_preview
MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES=true
```

Both env vars are required. The guard alone with `mode=disabled` is a
no-op; the mode alone without the guard forces the effective mode back
to `disabled` with the `true_momentum_strategy_mode_blocked_by_guard`
reason code.

### Surfaces

- **Backend pure evaluator** —
  `src/macmarket_trader/recommendation/true_momentum_strategy_families.py`
  exposes `evaluate_true_momentum_strategy_preview(settings, *,
  candidates)`. Returns a dict carrying `status`, `previews`,
  `previews_generated`, `summary`, `guardrails`, `phase`,
  `implementation_status`, `preview_phase`,
  `preview_implementation_status`, `deterministic_note`, and a typed
  `TrueMomentumStrategyPreviewResult` under `result`.
- **Read-only endpoint** —
  `POST /user/true-momentum-strategy-families/preview` (approved-user
  auth). Request: `{ "candidates": [...] }`. Response: the typed
  `TrueMomentumStrategyPreviewResultPayload` (status + summary +
  previews + guardrails + deterministic note). No DB writes, no
  provider calls, no market-data calls.
- **Frontend pure helper** —
  `apps/web/lib/true-momentum-strategy-preview.ts`
  (`buildTrueMomentumStrategyPreview`,
  `summarizeTrueMomentumStrategyPreview`,
  `trueMomentumPreviewReasonLabels`, `trueMomentumPreviewTone`,
  `familyPreviewLabel`).
- **Frontend panel** —
  `apps/web/components/recommendations/true-momentum-strategy-preview-panel.tsx`
  is mounted on the Recommendations page directly after the Momentum
  Trial Journal. Renders the disabled empty state with env
  instructions, the research-preview summary cards + preview table,
  the active-reserved copy, and the deterministic guardrail note.

### Still pending

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim fixture parity.
- Operator authorization before any active Phase C.

## Phase C2 — research-preview evidence bundle

Phase C2 wraps the Phase C1 classification into an operator-facing
**evidence bundle workflow**. It captures whatever rows Phase C1
matched, lets the operator overlay a global research conclusion plus
per-family and per-candidate notes / tags, and exports the result as
deterministic Markdown / JSON. Everything is local/export-only — no
backend write, no DB row, no migration, no LLM call.

### What it does

- Builds a `TrueMomentumPreviewEvidenceBundle` from an existing
  Phase C1 `TrueMomentumStrategyPreviewResult` and the already-loaded
  queue candidates.
- Records the resolved ranking mode and active delta scale from the
  Phase C1 result (no recomputation).
- Surfaces `evaluated_universe` (when the page passes
  `universeSymbols`) or falls back to `captured_symbols` derived from
  the loaded queue.
- Groups the matched preview rows per family (continuation /
  pullback / reversal-watch), with per-family preview / strong /
  moderate / watch / blocked counts plus per-row trade warnings and
  operational caveats (`thinkorswim_parity_pending`,
  `derived_higher_timeframe`, `score_consistency_corrected`, …).
- Records whether a Phase B7 trial snapshot and Phase B8 outcome
  review are linked (presence flags only — no shared mutable state).
- Lets the operator attach a global conclusion, per-family notes, and
  per-candidate notes / review tags
  (`research_candidate`, `watchlist_only`, `needs_tos_parity_check`,
  `needs_b8_outcome_evidence`, `too_noisy`, `defer`).
- Exports as **Markdown** (Copy + Download) and **JSON**, both
  carrying the deterministic guardrail copy and the "Active Phase C
  True Momentum strategy families are not implemented" reminder.
- Persists the latest captured bundle to
  `macmarket.trueMomentumPreviewEvidence.latest`, keyed by the queue
  signature so stale caches across different queues are discarded.

### What it does NOT do

- **No new queue candidates.** The bundle only re-frames already
  matched Phase C1 rows.
- **No ranking math change.** `build_momentum_ranking_contribution`,
  `DeterministicRankingEngine`, Phase B1 / B6 / B6.x wiring are
  byte-identical.
- **No queue sorting change.**
- **No approval / promote / save / paper-order / settle / replay /
  options-preview behavior change.**
- **No backend mutation.** No DB write, no migration, no LLM call, no
  provider / market-data call. Phase C2 is frontend-only.
- **No Phase C active behavior.** `MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE=active`
  remains reserved — Phase C1 still degrades it to
  `research_preview` with the
  `true_momentum_strategy_active_mode_not_implemented` reason code.

### Surfaces

- **Pure helpers** —
  `apps/web/lib/true-momentum-preview-evidence.ts`
  (`buildTrueMomentumPreviewEvidenceBundle`,
  `summarizeTrueMomentumPreviewEvidence`,
  `partitionTrueMomentumPreviewEvidenceByFamily`,
  `topTrueMomentumPreviewEvidence`,
  `trueMomentumPreviewEvidenceWarnings`,
  `sanitizeTrueMomentumPreviewEvidenceNote`,
  `buildTrueMomentumPreviewEvidenceMarkdown`,
  `buildTrueMomentumPreviewEvidenceJson`,
  `validateTrueMomentumPreviewEvidenceBundle`,
  `trueMomentumPreviewEvidenceTagLabel`,
  `trueMomentumPreviewEvidenceTagTone`,
  `TRUE_MOMENTUM_PREVIEW_EVIDENCE_DETERMINISTIC_NOTE`,
  `TRUE_MOMENTUM_PREVIEW_EVIDENCE_STORAGE_KEY`).
- **Reusable component** —
  `apps/web/components/recommendations/true-momentum-preview-evidence-panel.tsx`
  (`<TrueMomentumPreviewEvidencePanel candidates previewResult
  universeSymbols b8Snapshot b8OutcomeReview persistLatest
  initialBundle />`).
- **C1 integration** —
  `apps/web/components/recommendations/true-momentum-strategy-preview-panel.tsx`
  mounts the evidence panel below its preview table whenever Phase C1
  produced at least one preview row.

### Recommended workflow

1. Run the active Momentum queue from Recommendations.
2. Review the Phase C1 family preview panel.
3. Press **Capture True Momentum Preview Evidence** to record the
   current C1 classification + operator notes / tags into a Phase C2
   evidence bundle.
4. Capture a Phase B7 trial-journal snapshot and a Phase B8 outcome
   review for the same session.
5. Compare the exported Phase C2 preview evidence (Markdown / JSON)
   against the Phase B8 outcome reviews before any Phase C3 / active
   Phase C authorization.

### Still pending (carried forward)

- Accumulated B8 outcome evidence corpus.
- Real Thinkorswim fixture parity.
- Operator authorization before any active Phase C.

## Related documents

- [`momentum-intelligence-layer.md`](momentum-intelligence-layer.md) —
  full Momentum charter, Phase A/B specifications, Phase A/B closeout.
- [`momentum-phase-closeout.md`](momentum-phase-closeout.md) — operator
  checklist summarizing what shipped, current env knobs, outstanding
  items, and Phase C posture.

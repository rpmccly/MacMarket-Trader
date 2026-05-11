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

## Related documents

- [`momentum-intelligence-layer.md`](momentum-intelligence-layer.md) —
  full Momentum charter, Phase A/B specifications, Phase A/B closeout.
- [`momentum-phase-closeout.md`](momentum-phase-closeout.md) — operator
  checklist summarizing what shipped, current env knobs, outstanding
  items, and Phase C posture.

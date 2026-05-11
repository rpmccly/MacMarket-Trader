import { fetchWorkflowApi, type NormalizedApiResult } from "@/lib/api-client";

// Phase C0 — True Momentum strategy-family scaffolding types + read-only
// fetch helper. The endpoint never generates queue candidates, mutates
// state, or approves / rejects / sizes / routes trades. It is rendered
// as a read-only Settings status card alongside the Phase B Momentum
// ranking status card.

export type TrueMomentumStrategyMode = "disabled" | "research_preview" | "active";

export type TrueMomentumStrategyFamilyStatusValue =
  | "planned"
  | "research_preview"
  | "disabled";

export type TrueMomentumStrategyFamilyDirection = "long" | "short" | "watch";

export type TrueMomentumStrategyFamilySpec = {
  id: string;
  label: string;
  description: string;
  status: TrueMomentumStrategyFamilyStatusValue;
  intended_direction: TrueMomentumStrategyFamilyDirection;
  required_inputs: string[];
  deterministic_signals: string[];
  guardrails: string[];
  not_allowed_actions: string[];
  phase: string;
  implementation_status: string;
};

export type TrueMomentumStrategyFamilyStatus = {
  requested_mode: TrueMomentumStrategyMode;
  effective_mode: TrueMomentumStrategyMode;
  enabled: boolean;
  guard_enabled: boolean;
  invalid_env_value?: boolean;
  mode_env_var: string;
  guard_env_var: string;
  reason_codes: string[];
  guardrails: string[];
  family_specs: TrueMomentumStrategyFamilySpec[];
  phase: string;
  implementation_status: string;
  parity_status: string;
  parity_required_for_active: boolean;
};

export const TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE =
  "Phase C0 is scaffold-only. These family specs do not approve, reject, size, or route trades, and they do not generate queue candidates.";

/**
 * Phase C0 — fetch the read-only True Momentum strategy-family status.
 * Returns the same `NormalizedApiResult` shape used by the project's
 * other protected API helpers.
 */
export async function fetchTrueMomentumStrategyFamilyStatus(): Promise<
  NormalizedApiResult<TrueMomentumStrategyFamilyStatus>
> {
  return fetchWorkflowApi<TrueMomentumStrategyFamilyStatus>(
    "/api/user/true-momentum-strategy-families/status",
  );
}

const MODE_LABELS: Record<TrueMomentumStrategyMode, string> = {
  disabled: "Disabled",
  research_preview: "Research preview",
  active: "Active",
};

export function trueMomentumStrategyModeLabel(
  mode: TrueMomentumStrategyMode | string | null | undefined,
): string {
  if (mode == null) return "Unknown";
  if (mode in MODE_LABELS) return MODE_LABELS[mode as TrueMomentumStrategyMode];
  const normalized = String(mode).trim().toLowerCase();
  if (normalized in MODE_LABELS) {
    return MODE_LABELS[normalized as TrueMomentumStrategyMode];
  }
  return String(mode);
}

const REASON_LABELS: Record<string, string> = {
  true_momentum_strategy_mode_blocked_by_guard:
    "Mode blocked — MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES not enabled",
  true_momentum_strategy_active_mode_not_implemented:
    "Active mode not implemented — resolved to research preview",
  true_momentum_strategy_invalid_env_value_resolved_to_disabled:
    "Invalid env value — resolved to disabled",
  thinkorswim_parity_pending: "Thinkorswim parity pending",
};

export function trueMomentumStrategyReasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code.replaceAll("_", " ");
}

export function trueMomentumStrategyDirectionLabel(
  direction: TrueMomentumStrategyFamilyDirection | string | null | undefined,
): string {
  if (direction === "long") return "Long";
  if (direction === "short") return "Short";
  if (direction === "watch") return "Watch only";
  return "Unknown";
}

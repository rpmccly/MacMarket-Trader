import { fetchWorkflowApi, type NormalizedApiResult } from "@/lib/api-client";
import type { MomentumRankingMode } from "@/lib/recommendations";

export type MomentumRankingStatus = {
  mode: MomentumRankingMode;
  default_mode: MomentumRankingMode;
  env_var: string;
  raw_env_value?: string | null;
  invalid_env_value?: boolean;
  enabled: boolean;
  applied_by_default: boolean;
  parity_status: string;
  parity_fixture_manifest_present: boolean;
  parity_fixture_manifest_path?: string | null;
  parity_required_for_active: boolean;
  real_thinkorswim_parity_pending: boolean;
  active_mode_warning?: string | null;
  reason_codes: string[];
  guardrails: string[];
  // Phase B6 safety-guard fields. ``mode`` mirrors ``effective_mode``
  // for backward compatibility with existing renderers; new clients
  // should prefer the explicit pair.
  requested_mode?: MomentumRankingMode;
  effective_mode?: MomentumRankingMode;
  active_allowed?: boolean;
  active_guard_env_var?: string;
  active_mode_blocked?: boolean;
  active_mode_block_reason?: string | null;
  // Phase B6.1 — operator-tunable active-mode delta scale.
  active_delta_scale?: number;
  active_delta_scale_env_var?: string;
  active_delta_scale_invalid?: boolean;
  active_delta_scale_warning?: string | null;
};

/**
 * Phase B3 — fetch the read-only Momentum ranking operator status.
 *
 * Returns the same {@link NormalizedApiResult} shape as the project's
 * existing protected API helpers so callers can read `authPending`,
 * `status`, and `error` without inventing a new contract.
 *
 * The endpoint never approves trades, mutates state, or touches market
 * data — it surfaces the resolved mode, parity state, and guardrails so
 * the Settings/Admin UI can render operator status.
 */
export async function fetchMomentumRankingStatus(): Promise<NormalizedApiResult<MomentumRankingStatus>> {
  return fetchWorkflowApi<MomentumRankingStatus>("/api/user/momentum-ranking-status");
}

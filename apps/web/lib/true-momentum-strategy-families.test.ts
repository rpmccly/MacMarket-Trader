import { describe, expect, it } from "vitest";

import {
  TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE,
  trueMomentumStrategyDirectionLabel,
  trueMomentumStrategyModeLabel,
  trueMomentumStrategyReasonLabel,
  type TrueMomentumStrategyFamilyStatus,
} from "@/lib/true-momentum-strategy-families";

describe("trueMomentumStrategyModeLabel", () => {
  it("labels disabled / research_preview / active modes", () => {
    expect(trueMomentumStrategyModeLabel("disabled")).toBe("Disabled");
    expect(trueMomentumStrategyModeLabel("research_preview")).toBe("Research preview");
    expect(trueMomentumStrategyModeLabel("active")).toBe("Active");
  });

  it("normalizes case and falls back gracefully", () => {
    expect(trueMomentumStrategyModeLabel("DISABLED")).toBe("Disabled");
    expect(trueMomentumStrategyModeLabel(null)).toBe("Unknown");
    expect(trueMomentumStrategyModeLabel(undefined)).toBe("Unknown");
    expect(trueMomentumStrategyModeLabel("something_else")).toBe("something_else");
  });
});

describe("trueMomentumStrategyReasonLabel", () => {
  it("translates known reason codes to operator copy", () => {
    expect(
      trueMomentumStrategyReasonLabel("true_momentum_strategy_mode_blocked_by_guard"),
    ).toContain("Mode blocked");
    expect(
      trueMomentumStrategyReasonLabel("true_momentum_strategy_active_mode_not_implemented"),
    ).toContain("Active mode not implemented");
    expect(
      trueMomentumStrategyReasonLabel(
        "true_momentum_strategy_invalid_env_value_resolved_to_disabled",
      ),
    ).toContain("Invalid env value");
    expect(trueMomentumStrategyReasonLabel("thinkorswim_parity_pending")).toBe(
      "Thinkorswim parity pending",
    );
  });

  it("falls back to a sentence-cased label for unknown codes", () => {
    expect(trueMomentumStrategyReasonLabel("totally_new_reason_code")).toBe(
      "totally new reason code",
    );
  });
});

describe("trueMomentumStrategyDirectionLabel", () => {
  it("labels long / short / watch", () => {
    expect(trueMomentumStrategyDirectionLabel("long")).toBe("Long");
    expect(trueMomentumStrategyDirectionLabel("short")).toBe("Short");
    expect(trueMomentumStrategyDirectionLabel("watch")).toBe("Watch only");
    expect(trueMomentumStrategyDirectionLabel(undefined)).toBe("Unknown");
  });
});

describe("deterministic note", () => {
  it("never contains forbidden trade-action language", () => {
    const note = TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE.toLowerCase();
    for (const phrase of [
      "buy now",
      "sell now",
      "enter now",
      "short now",
      "auto approve",
      "route order",
    ]) {
      expect(note).not.toContain(phrase);
    }
  });

  it("explicitly disclaims approval / sizing / routing", () => {
    expect(TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE).toContain(
      "do not approve, reject, size, or route trades",
    );
    expect(TRUE_MOMENTUM_STRATEGY_DETERMINISTIC_NOTE).toContain(
      "do not generate queue candidates",
    );
  });
});

describe("TrueMomentumStrategyFamilyStatus shape", () => {
  it("the typed shape never includes order/approval fields", () => {
    const example: TrueMomentumStrategyFamilyStatus = {
      requested_mode: "disabled",
      effective_mode: "disabled",
      enabled: false,
      guard_enabled: false,
      mode_env_var: "MACMARKET_TRUE_MOMENTUM_STRATEGY_MODE",
      guard_env_var: "MACMARKET_ALLOW_TRUE_MOMENTUM_STRATEGY_FAMILIES",
      reason_codes: [],
      guardrails: [],
      family_specs: [],
      phase: "C0",
      implementation_status: "scaffold_only",
      parity_status: "pending_thinkorswim_fixture_validation",
      parity_required_for_active: true,
    };
    const keys = Object.keys(example);
    const forbidden = ["entry", "stop", "target", "size", "order_id", "approved"];
    for (const key of forbidden) {
      expect(keys).not.toContain(key);
    }
  });
});

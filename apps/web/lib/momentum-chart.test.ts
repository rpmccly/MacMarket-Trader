import { describe, expect, it } from "vitest";

import {
  buildMomentumLegendValues,
  formatMomentumScore,
  formatMomentumValue,
  getLatestMomentumSnapshot,
  hasMomentumWarning,
  momentumScoreTone,
  normalizeMomentumTimeKey,
  summarizeMomentumSnapshot,
} from "@/lib/momentum-chart";
import type { MomentumChartPayload, MomentumScoreSnapshot } from "@/lib/momentum-api";

function snapshot(overrides: Partial<MomentumScoreSnapshot> = {}): MomentumScoreSnapshot {
  const breakdown = {
    true_momentum_score: 15,
    hilo_thrust: 5,
    bull_ma: 30,
    bear_ma: 0,
    atr_value: 5,
    macd_bias: 5,
    intraday_penalty: 0,
    base_score: 60,
    ...(overrides.component_breakdown ?? {}),
  };
  const { component_breakdown: _ignored, ...rest } = overrides;
  return {
    total_score: 90,
    total_label: "Bull",
    total_state: "bull",
    trend_score: 80,
    momo_score: 60,
    true_momentum: 65.5,
    true_momentum_ema: 60.1,
    true_momentum_score: breakdown.true_momentum_score,
    hilo_thrust: 1,
    hilo_score: breakdown.hilo_thrust,
    atr_bias: breakdown.atr_value,
    macd_bias: breakdown.macd_bias,
    ma_bias: breakdown.bull_ma + breakdown.bear_ma,
    ...rest,
    component_breakdown: breakdown,
  };
}

function payload(overrides: Partial<MomentumChartPayload> = {}): MomentumChartPayload {
  const snap = overrides.latest_snapshot ?? snapshot();
  return {
    symbol: "AAPL",
    timeframe: "1D",
    candles: [],
    true_momentum_line: [],
    true_momentum_ema_line: [],
    hilo_slowd_line: [],
    hilo_slowd_x_line: [],
    hilo_thrust_strip: [],
    score_strip: [],
    markers: [],
    latest_snapshot: snap,
    explanation: {
      snapshot: snap,
      reversal_warning: false,
      pullback_signal: false,
      no_trade_warning: false,
      notes: [],
    },
    data_source: "polygon",
    fallback_mode: false,
    higher_timeframe_source: "derived_from_chart_bars",
    higher_timeframe: "weekly",
    parity_status: "pending_thinkorswim_fixture_validation",
    calculation_notes: [],
    ...overrides,
  };
}

describe("momentumScoreTone", () => {
  it("returns good for bull-zone scores", () => {
    expect(momentumScoreTone(90)).toBe("good");
    expect(momentumScoreTone(75)).toBe("good");
    expect(momentumScoreTone(120)).toBe("good");
  });

  it("returns bad for bear-zone scores", () => {
    expect(momentumScoreTone(-90)).toBe("bad");
    expect(momentumScoreTone(-100)).toBe("bad");
  });

  it("returns warn for neutral_up / neutral_down", () => {
    expect(momentumScoreTone(60)).toBe("warn");
    expect(momentumScoreTone(-60)).toBe("warn");
  });

  it("returns neutral for inner band and missing values", () => {
    expect(momentumScoreTone(0)).toBe("neutral");
    expect(momentumScoreTone(null)).toBe("neutral");
    expect(momentumScoreTone(undefined)).toBe("neutral");
    expect(momentumScoreTone(Number.NaN)).toBe("neutral");
  });
});

describe("formatMomentumScore / formatMomentumValue", () => {
  it("returns em dash for null/undefined/NaN", () => {
    expect(formatMomentumScore(null)).toBe("—");
    expect(formatMomentumScore(undefined)).toBe("—");
    expect(formatMomentumScore(Number.NaN)).toBe("—");
    expect(formatMomentumValue(null)).toBe("—");
    expect(formatMomentumValue(undefined)).toBe("—");
    expect(formatMomentumValue(Number.NaN)).toBe("—");
  });

  it("prefixes positive scores with '+'", () => {
    expect(formatMomentumScore(75)).toBe("+75");
    expect(formatMomentumScore(-12)).toBe("-12");
    expect(formatMomentumScore(0)).toBe("0");
  });

  it("formats decimal values with two decimals", () => {
    expect(formatMomentumValue(50.123)).toBe("50.12");
    expect(formatMomentumValue(60)).toBe("60.00");
  });
});

describe("summarizeMomentumSnapshot", () => {
  it("describes a bull snapshot", () => {
    expect(summarizeMomentumSnapshot(snapshot({ total_label: "Bull", total_score: 80, trend_score: 75, momo_score: 60 }))).toBe(
      "Bull +80 · Trend +75 · Momo +60",
    );
  });

  it("describes a bear snapshot", () => {
    expect(
      summarizeMomentumSnapshot(snapshot({ total_label: "Bear", total_score: -85, trend_score: -75, momo_score: -50, total_state: "bear" })),
    ).toBe("Bear -85 · Trend -75 · Momo -50");
  });

  it("describes a neutral snapshot", () => {
    expect(
      summarizeMomentumSnapshot(snapshot({ total_label: "Neutral", total_score: 0, trend_score: 0, momo_score: 0, total_state: "neutral" })),
    ).toBe("Neutral 0 · Trend 0 · Momo 0");
  });

  it("returns a clear unavailable message for missing snapshots", () => {
    expect(summarizeMomentumSnapshot(null)).toBe("Momentum context unavailable.");
    expect(summarizeMomentumSnapshot(undefined)).toBe("Momentum context unavailable.");
  });
});

describe("hasMomentumWarning", () => {
  it("is true when reversal warning is set", () => {
    const data = payload();
    data.explanation = { ...data.explanation!, reversal_warning: true };
    expect(hasMomentumWarning(data)).toBe(true);
  });

  it("is true when no_trade_warning is set", () => {
    const data = payload();
    data.explanation = { ...data.explanation!, no_trade_warning: true };
    expect(hasMomentumWarning(data)).toBe(true);
  });

  it("is false for clean payload", () => {
    expect(hasMomentumWarning(payload())).toBe(false);
    expect(hasMomentumWarning(null)).toBe(false);
    expect(hasMomentumWarning(undefined)).toBe(false);
  });
});

describe("getLatestMomentumSnapshot", () => {
  it("prefers latest_snapshot when present", () => {
    const data = payload();
    expect(getLatestMomentumSnapshot(data)?.total_score).toBe(90);
  });

  it("falls back to explanation.snapshot when latest_snapshot is null", () => {
    const data = payload();
    const expected = snapshot({ total_score: 42 });
    data.latest_snapshot = null;
    data.explanation = { ...data.explanation!, snapshot: expected };
    expect(getLatestMomentumSnapshot(data)?.total_score).toBe(42);
  });

  it("returns null when no snapshot is available", () => {
    expect(getLatestMomentumSnapshot(null)).toBeNull();
  });
});

describe("buildMomentumLegendValues", () => {
  it("returns labelled, toned legend rows from a snapshot", () => {
    const rows = buildMomentumLegendValues(payload());
    const labels = rows.map((row) => row.label);
    expect(labels).toContain("Total Score");
    expect(labels).toContain("Trend Score");
    expect(labels).toContain("Momo Score");
    expect(labels).toContain("True Momentum");
    expect(labels).toContain("HiLo Thrust");
    expect(labels).toContain("ATR Bias");
    expect(labels).toContain("MACD Bias");
    expect(labels).toContain("MA Bias");
    expect(rows[0]).toMatchObject({ label: "Total Score", value: "+90", tone: "good" });
  });

  it("returns neutral placeholders when no snapshot is available", () => {
    expect(buildMomentumLegendValues(null)).toEqual([
      { label: "Total Score", value: "—", tone: "neutral" },
      { label: "Trend Score", value: "—", tone: "neutral" },
      { label: "Momo Score", value: "—", tone: "neutral" },
    ]);
  });
});

describe("normalizeMomentumTimeKey", () => {
  it("returns string for numeric and string time", () => {
    expect(normalizeMomentumTimeKey(1)).toBe("1");
    expect(normalizeMomentumTimeKey("2026-04-01")).toBe("2026-04-01");
    expect(normalizeMomentumTimeKey(null)).toBe("");
    expect(normalizeMomentumTimeKey(undefined)).toBe("");
  });
});

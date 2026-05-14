import { describe, expect, it } from "vitest";

import {
  buildCandleStatusBadges,
  buildHiloPanelBadges,
  buildMomentumLegendValues,
  buildTrueMomentumPanelBadges,
  buildVisualParityFields,
  describeHigherTimeframeSource,
  describeParityStatus,
  findVisualParityForTime,
  formatMomentumScore,
  formatMomentumValue,
  formatPanelMarkerLabel,
  formatPercent,
  getLatestMomentumSnapshot,
  hasMomentumWarning,
  MOMENTUM_DETERMINISTIC_NOTE,
  momentumScoreTone,
  normalizeMomentumTimeKey,
  panelMarkerTone,
  splitMomentumLineByDirection,
  summarizeMomentumSnapshot,
} from "@/lib/momentum-chart";
import type {
  MomentumChartPayload,
  MomentumPanelMarker,
  MomentumScoreSnapshot,
  MomentumVisualParityPoint,
  MomentumVisualParitySnapshot,
} from "@/lib/momentum-api";

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
    expect(getLatestMomentumSnapshot(payload())?.total_score).toBe(90);
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

describe("describeHigherTimeframeSource / describeParityStatus", () => {
  it("labels provided-HTF as good and pending-parity as neutral (visible but not alarming)", () => {
    expect(describeHigherTimeframeSource("provided_higher_timeframe_bars")).toEqual({ label: "Provided HTF bars", tone: "good" });
    expect(describeHigherTimeframeSource("derived_from_chart_bars")).toEqual({ label: "HTF derived from chart bars", tone: "neutral" });
    expect(describeHigherTimeframeSource("insufficient_data")).toEqual({ label: "HTF insufficient data", tone: "warn" });

    expect(describeParityStatus("validated_against_thinkorswim_fixture")).toEqual({ label: "Parity validated", tone: "good" });
    expect(describeParityStatus("pending_thinkorswim_fixture_validation")).toEqual({
      label: "Parity pending Thinkorswim fixtures",
      tone: "neutral",
    });
  });
});

describe("MOMENTUM_DETERMINISTIC_NOTE", () => {
  it("frames the score as context only and never trade approval", () => {
    expect(MOMENTUM_DETERMINISTIC_NOTE).toContain("deterministic context only");
    expect(MOMENTUM_DETERMINISTIC_NOTE).toContain("does not approve, reject, size, or rank");
  });
});

// ── Visual parity chart polish helpers ──────────────────────────────

function paritySnapshot(
  overrides: Partial<MomentumVisualParitySnapshot> = {},
): MomentumVisualParitySnapshot {
  return {
    as_of: "2026-05-10",
    symbol: "SPY",
    timeframe: "1D",
    history_range: "1Y",
    total_score: 80,
    total_label: "Bull",
    trend_score: 70,
    momo_score: 60,
    true_momentum: 67.25,
    true_momentum_ema: 61.4,
    hilo_slowd: 78.91,
    hilo_slowd_x: 76.42,
    tos_hilo_elite_scalar: null,
    hilo_thrust_state: "bullish",
    hilo_score: 10,
    pullback_signal: false,
    reversal_warning: false,
    no_trade_warning: false,
    iv_percent: null,
    source_notes: ["computed from existing indicator state"],
    unavailable_fields: ["iv_percent", "tos_hilo_elite_scalar"],
    ...overrides,
  };
}

function parityPoint(
  overrides: Partial<MomentumVisualParityPoint> = {},
): MomentumVisualParityPoint {
  return {
    index: 0,
    time: "2026-05-10",
    total_score: 80,
    total_label: "Bull",
    total_state: "bull",
    trend_score: 70,
    momo_score: 60,
    true_momentum: 67.25,
    true_momentum_ema: 61.4,
    hilo_slowd: 78.91,
    hilo_slowd_x: 76.42,
    hilo_thrust_state: "bullish",
    hilo_score: 10,
    pullback_signal: false,
    reversal_warning: false,
    no_trade_warning: false,
    ...overrides,
  };
}

describe("buildCandleStatusBadges", () => {
  it("renders Total / Trend / Momo / IV% from a parity snapshot", () => {
    const badges = buildCandleStatusBadges(paritySnapshot());
    const labels = badges.map((b) => b.label);
    expect(labels).toEqual(["IV%", "Total", "Trend", "Momo"]);
    expect(badges[0]).toMatchObject({ id: "iv", value: "—", tone: "neutral", unavailable: true });
    expect(badges[1].value).toContain("Bull");
    expect(badges[1].tone).toBe("good");
    expect(badges[2].value).toBe("+70");
    expect(badges[3].value).toBe("+60");
  });

  it("falls back to placeholder badges with unavailable=true when snapshot is null", () => {
    const badges = buildCandleStatusBadges(null);
    expect(badges.every((b) => b.unavailable)).toBe(true);
    expect(badges.every((b) => b.value === "—")).toBe(true);
  });

  it("renders IV% when a deterministic IV value is present", () => {
    const badges = buildCandleStatusBadges(paritySnapshot({ iv_percent: 27.5, unavailable_fields: [] }));
    const iv = badges.find((b) => b.id === "iv");
    expect(iv?.value).toBe("27.5%");
    expect(iv?.unavailable).toBe(false);
  });
});

describe("buildTrueMomentumPanelBadges", () => {
  it("flags bullish state when true_momentum > ema", () => {
    const [state] = buildTrueMomentumPanelBadges(paritySnapshot());
    expect(state.value).toBe("Bullish");
    expect(state.tone).toBe("good");
  });

  it("flags bearish state when true_momentum < ema", () => {
    const [state] = buildTrueMomentumPanelBadges(
      paritySnapshot({ true_momentum: 40, true_momentum_ema: 55 }),
    );
    expect(state.value).toBe("Bearish");
    expect(state.tone).toBe("bad");
  });

  it("flags neutral when values are equal or missing", () => {
    const [stateEqual] = buildTrueMomentumPanelBadges(
      paritySnapshot({ true_momentum: 50, true_momentum_ema: 50 }),
    );
    expect(stateEqual.value).toBe("Neutral");
    const [stateMissing] = buildTrueMomentumPanelBadges(
      paritySnapshot({ true_momentum: null, true_momentum_ema: null }),
    );
    expect(stateMissing.value).toBe("—");
  });

  it("renders True Momentum and EMA numeric values", () => {
    const badges = buildTrueMomentumPanelBadges(paritySnapshot());
    expect(badges.find((b) => b.id === "tm_value")?.value).toBe("67.25");
    expect(badges.find((b) => b.id === "tm_ema")?.value).toBe("61.40");
  });
});

describe("buildHiloPanelBadges", () => {
  it("maps bullish thrust to Confirmed/good tone, bearish to Deconfirmed/bad, neutral to Neutral/neutral", () => {
    const bullish = buildHiloPanelBadges(paritySnapshot({ hilo_thrust_state: "bullish" }));
    const bearish = buildHiloPanelBadges(paritySnapshot({ hilo_thrust_state: "bearish" }));
    const neutral = buildHiloPanelBadges(paritySnapshot({ hilo_thrust_state: "neutral" }));
    expect(bullish[0]).toMatchObject({ id: "hilo_state", value: "Confirmed", tone: "good" });
    expect(bearish[0]).toMatchObject({ id: "hilo_state", value: "Deconfirmed", tone: "bad" });
    expect(neutral[0]).toMatchObject({ id: "hilo_state", value: "Neutral", tone: "neutral" });
  });

  it("renders HiLo SlowD and HiLo SlowD_X as separate badges instead of a misleading 'HiLo Elite' label", () => {
    const badges = buildHiloPanelBadges(
      paritySnapshot({ hilo_slowd: 42.5, hilo_slowd_x: 39.1, hilo_score: -5 }),
    );
    const slowd = badges.find((b) => b.id === "hilo_slowd");
    const slowdX = badges.find((b) => b.id === "hilo_slowd_x");
    const score = badges.find((b) => b.id === "hilo_score");
    expect(slowd?.label).toBe("HiLo SlowD");
    expect(slowd?.value).toBe("42.50");
    expect(slowdX?.label).toBe("HiLo SlowD_X");
    expect(slowdX?.value).toBe("39.10");
    expect(score?.value).toBe("-5");
    // Each id is distinct so the UI never collapses SlowD and the score
    // into a single cell.
    expect(new Set([slowd?.id, slowdX?.id, score?.id]).size).toBe(3);
  });

  it("never renders a 'HiLo Elite' badge when tos_hilo_elite_scalar is unavailable", () => {
    const badges = buildHiloPanelBadges(paritySnapshot());
    const tosBadge = badges.find((b) => b.id === "tos_hilo_elite");
    expect(tosBadge).toBeUndefined();
    expect(badges.every((b) => b.label !== "HiLo Elite")).toBe(true);
  });

  it("renders ToS HiLo Elite badge only when a real value is provided and not flagged unavailable", () => {
    const badges = buildHiloPanelBadges(
      paritySnapshot({ tos_hilo_elite_scalar: 98.18, unavailable_fields: ["iv_percent"] }),
    );
    const tosBadge = badges.find((b) => b.id === "tos_hilo_elite");
    expect(tosBadge).toBeDefined();
    expect(tosBadge?.label).toBe("ToS HiLo Elite");
    expect(tosBadge?.value).toBe("98.18");
    expect(tosBadge?.unavailable).toBe(false);
  });
});

describe("buildVisualParityFields", () => {
  it("renders every ToS-comparable field from the snapshot", () => {
    const fields = buildVisualParityFields(paritySnapshot());
    const ids = fields.map((f) => f.id);
    expect(ids).toContain("total_score");
    expect(ids).toContain("total_label");
    expect(ids).toContain("true_momentum");
    expect(ids).toContain("true_momentum_ema");
    expect(ids).toContain("hilo_slowd");
    expect(ids).toContain("hilo_slowd_x");
    expect(ids).toContain("tos_hilo_elite_scalar");
    expect(ids).toContain("hilo_thrust_state");
    expect(ids).toContain("hilo_score");
    expect(ids).toContain("pullback_signal");
    expect(ids).toContain("reversal_warning");
    expect(ids).toContain("no_trade_warning");
    expect(ids).toContain("iv_percent");
    const iv = fields.find((f) => f.id === "iv_percent");
    expect(iv?.value).toBe("—");
    expect(iv?.unavailable).toBe(true);
    const tos = fields.find((f) => f.id === "tos_hilo_elite_scalar");
    expect(tos?.value).toBe("—");
    expect(tos?.unavailable).toBe(true);
    expect(tos?.label).toBe("ToS HiLo Elite");
  });

  it("returns no rows when the snapshot is null", () => {
    expect(buildVisualParityFields(null)).toEqual([]);
  });

  it("never emits hilo_elite_value (renamed to hilo_slowd / tos_hilo_elite_scalar)", () => {
    const ids = buildVisualParityFields(paritySnapshot()).map((f) => f.id);
    expect(ids).not.toContain("hilo_elite_value");
  });
});

describe("findVisualParityForTime", () => {
  function payloadWithSeries(): MomentumChartPayload {
    const series = [
      parityPoint({ time: "2026-05-08", index: 0, total_score: 50 }),
      parityPoint({ time: "2026-05-09", index: 1, total_score: 70 }),
      parityPoint({ time: "2026-05-10", index: 2, total_score: 80 }),
    ];
    return {
      symbol: "SPY",
      timeframe: "1D",
      candles: [],
      true_momentum_line: [],
      true_momentum_ema_line: [],
      hilo_slowd_line: [],
      hilo_slowd_x_line: [],
      hilo_thrust_strip: [],
      score_strip: [],
      markers: [],
      latest_snapshot: null,
      explanation: null,
      data_source: "polygon",
      fallback_mode: false,
      higher_timeframe_source: "derived_from_chart_bars",
      higher_timeframe: "weekly",
      parity_status: "pending_thinkorswim_fixture_validation",
      calculation_notes: [],
      visual_parity_snapshot: paritySnapshot({ total_score: 80 }),
      visual_parity_series: series,
      true_momentum_panel_markers: [],
      hilo_panel_markers: [],
    };
  }

  it("returns the per-bar point matching the hovered time", () => {
    const data = payloadWithSeries();
    const hovered = findVisualParityForTime(data, "2026-05-09");
    expect(hovered).not.toBeNull();
    expect((hovered as MomentumVisualParityPoint).total_score).toBe(70);
  });

  it("falls back to the latest snapshot when no time is provided", () => {
    const data = payloadWithSeries();
    const latest = findVisualParityForTime(data, null);
    expect(latest).not.toBeNull();
    expect((latest as MomentumVisualParitySnapshot).total_score).toBe(80);
  });

  it("returns null when payload is null", () => {
    expect(findVisualParityForTime(null, "2026-05-10")).toBeNull();
  });
});

describe("splitMomentumLineByDirection", () => {
  it("splits a primary series into bullish and bearish segments by reference comparison", () => {
    const primary = [
      { index: 0, time: "2026-05-08", value: 50 },
      { index: 1, time: "2026-05-09", value: 60 },
      { index: 2, time: "2026-05-10", value: 55 },
    ];
    const reference = [
      { index: 0, time: "2026-05-08", value: 48 },
      { index: 1, time: "2026-05-09", value: 65 },
      { index: 2, time: "2026-05-10", value: 53 },
    ];
    const { bullSeries, bearSeries } = splitMomentumLineByDirection(primary, reference);
    expect(bullSeries.map((p) => p.value)).toEqual([50, 55]);
    expect(bearSeries.map((p) => p.value)).toEqual([60]);
    // Inputs are not mutated.
    expect(primary[1].value).toBe(60);
    expect(reference[0].value).toBe(48);
  });

  it("returns empty series when the primary series is missing or empty", () => {
    expect(splitMomentumLineByDirection(null, null)).toEqual({ bullSeries: [], bearSeries: [] });
    expect(splitMomentumLineByDirection([], null)).toEqual({ bullSeries: [], bearSeries: [] });
  });

  it("treats NaN/Inf values as bullish (no false bear) so the chart never throws", () => {
    const primary = [
      { index: 0, time: "2026-05-08", value: Number.NaN },
      { index: 1, time: "2026-05-09", value: Number.POSITIVE_INFINITY },
      { index: 2, time: "2026-05-10", value: 55 },
    ];
    const reference = [
      { index: 0, time: "2026-05-08", value: 60 },
      { index: 1, time: "2026-05-09", value: 60 },
      { index: 2, time: "2026-05-10", value: 60 },
    ];
    const { bullSeries, bearSeries } = splitMomentumLineByDirection(primary, reference);
    expect(bullSeries.some((p) => Number.isNaN(p.value))).toBe(true);
    expect(bearSeries.find((p) => p.value === 55)).toBeDefined();
  });
});

describe("formatPanelMarkerLabel + panelMarkerTone", () => {
  function marker(overrides: Partial<MomentumPanelMarker> = {}): MomentumPanelMarker {
    return {
      index: 0,
      time: "2026-05-10",
      panel: "true_momentum",
      marker_type: "bullish_cross",
      direction: "up",
      label: "Cross up",
      value: 67.25,
      reason: "True Momentum crossed above EMA",
      ...overrides,
    };
  }

  it("returns canonical labels for known marker types", () => {
    expect(formatPanelMarkerLabel(marker())).toBe("Cross up");
    expect(formatPanelMarkerLabel(marker({ marker_type: "bearish_cross" }))).toBe("Cross down");
    expect(formatPanelMarkerLabel(marker({ marker_type: "hilo_confirmed" }))).toBe("HiLo confirmed");
    expect(formatPanelMarkerLabel(marker({ marker_type: "hilo_deconfirmed" }))).toBe("HiLo deconfirmed");
  });

  it("returns good for up direction, bad for down, neutral otherwise", () => {
    expect(panelMarkerTone(marker({ direction: "up" }))).toBe("good");
    expect(panelMarkerTone(marker({ direction: "down" }))).toBe("bad");
    expect(panelMarkerTone(marker({ direction: "neutral" }))).toBe("neutral");
  });

  it("never returns NaN-style markers", () => {
    const m = marker({ value: Number.NaN });
    // The formatter doesn't inspect value; just confirm no throw.
    expect(formatPanelMarkerLabel(m)).toBeTruthy();
  });
});

describe("formatPercent", () => {
  it("formats numeric values with one decimal + %", () => {
    expect(formatPercent(25)).toBe("25.0%");
    expect(formatPercent(27.5)).toBe("27.5%");
    expect(formatPercent(33.34)).toBe("33.3%");
  });

  it("returns em dash for null/undefined/NaN", () => {
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatPercent(Number.NaN)).toBe("—");
  });
});

import { expect, test } from "@playwright/test";

// Phase A3 smoke: verify /charts/momentum mounts cleanly with the deterministic
// context-only framing, the symbol/timeframe controls are present, and the
// console nav link points back at the workspace. Network is intercepted so no
// call proxies to the Python backend during e2e.

function emptyMomentumPayload() {
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
    squeeze_pro: {
      enabled: true,
      status: "unavailable",
      reason: "no chart bars provided",
      parameters: { length: 20, nBB: 2, nK_High: 1, nK_Mid: 1.5, nK_Low: 2, price: "close" },
      version: "macmarket_squeeze_pro.v1",
      histogram_mode: "macmarket_linear_regression_momentum_approximation",
      arrow_mode: "disabled_pending_approved_arrow_rules",
      show_arrows: false,
      series: [],
    },
  };
}

function populatedMomentumPayload() {
  const times = Array.from({ length: 80 }, (_, index) => {
    const day = new Date(Date.UTC(2026, 0, index + 1));
    return day.toISOString().slice(0, 10);
  });
  const snapshot = {
    total_score: 48,
    total_label: "Bullish context",
    total_state: "bull",
    trend_score: 22,
    momo_score: 26,
    true_momentum: 1.4,
    true_momentum_ema: 1.1,
    true_momentum_score: 62,
    hilo_thrust: 64,
    hilo_score: 16,
    atr_bias: 0,
    macd_bias: 0,
    ma_bias: 6,
    component_breakdown: {
      true_momentum_score: 62,
      hilo_thrust: 16,
      bull_ma: 6,
      bear_ma: 0,
      atr_value: 0,
      macd_bias: 0,
      intraday_penalty: 0,
      base_score: 48,
    },
  };

  return {
    ...emptyMomentumPayload(),
    candles: times.map((time, index) => ({
      index,
      time,
      open: 100 + index * 0.2,
      high: 101 + index * 0.2,
      low: 99 + index * 0.2,
      close: 100.5 + index * 0.2,
      volume: 1_000_000 + index,
    })),
    true_momentum_line: times.map((time, index) => ({
      index,
      time,
      value: Math.sin(index / 8) * 2,
    })),
    true_momentum_ema_line: times.map((time, index) => ({
      index,
      time,
      value: Math.sin(index / 8) * 1.6,
    })),
    hilo_slowd_line: times.map((time, index) => ({
      index,
      time,
      value: 45 + Math.sin(index / 6) * 18,
    })),
    hilo_slowd_x_line: times.map((time, index) => ({
      index,
      time,
      value: 50 + Math.cos(index / 7) * 16,
    })),
    hilo_thrust_strip: times.map((time, index) => ({
      index,
      time,
      value: index % 2 === 0 ? 64 : 42,
      state: index % 2 === 0 ? "bullish" : "neutral",
    })),
    score_strip: times.map((time, index) => ({
      index,
      time,
      total_score: 30 + Math.sin(index / 9) * 28,
      state: index % 3 === 0 ? "bull" : "neutral",
    })),
    latest_snapshot: snapshot,
    explanation: {
      snapshot,
      reversal_warning: false,
      pullback_signal: false,
      no_trade_warning: false,
      notes: [],
    },
    visual_parity_snapshot: null,
    visual_parity_series: [],
    true_momentum_panel_markers: [],
    hilo_panel_markers: [],
    squeeze_pro: {
      enabled: true,
      status: "ok",
      reason: null,
      parameters: { length: 20, nBB: 2, nK_High: 1, nK_Mid: 1.5, nK_Low: 2, price: "close" },
      version: "macmarket_squeeze_pro.v1",
      histogram_mode: "macmarket_linear_regression_momentum_approximation",
      arrow_mode: "disabled_pending_approved_arrow_rules",
      show_arrows: false,
      series: times.map((time, index) =>
        index < 38
          ? {
              index,
              time,
              oscillator_value: null,
              oscillator_state: null,
              oscillator_color: null,
              squeeze_state: "unavailable",
              squeeze_color: "#5a6b7c",
              delta_high: null,
              delta_mid: null,
              delta_low: null,
              arrow: null,
              arrow_reason: null,
              status: "unavailable",
              reason: "insufficient_bars_for_squeeze_pro",
            }
          : {
              index,
              time,
              oscillator_value: Math.sin(index / 5) * 4,
              oscillator_state: index % 4 === 0 ? "up_decreasing" : "up",
              oscillator_color: index % 4 === 0 ? "#4d8dff" : "#4dd9ff",
              squeeze_state: index % 12 === 0 ? "mid" : "none",
              squeeze_color: index % 12 === 0 ? "#d14b4b" : "#21c06e",
              delta_high: 1,
              delta_mid: 2,
              delta_low: 3,
              arrow: null,
              arrow_reason: null,
              status: "ok",
              reason: null,
            },
      ),
    },
  };
}

let mockedMomentumPayload = emptyMomentumPayload();

test.beforeEach(async ({ page }) => {
  mockedMomentumPayload = emptyMomentumPayload();
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: { app_role: null, approval_status: "approved" } });
  });
  await page.route("**/api/charts/momentum", async (route) => {
    await route.fulfill({ json: mockedMomentumPayload });
  });
});

test("/charts/momentum mounts the workspace with deterministic-context framing", async ({ page }) => {
  await page.goto("/charts/momentum");

  // Workspace mounts.
  const workspace = page.getByTestId("momentum-workspace");
  await expect(workspace).toBeVisible();

  // Deterministic-context framing is visible (Phase A copy guardrail).
  await expect(page.getByTestId("momentum-workspace-deterministic-note")).toContainText(
    "Momentum Intelligence is deterministic context only in Phase A",
  );

  // Symbol input + timeframe selector + load button.
  await expect(page.getByTestId("momentum-symbol-input")).toBeVisible();
  await expect(page.getByTestId("momentum-timeframe-select")).toBeVisible();
  await expect(page.getByTestId("momentum-load-button")).toBeVisible();
  await expect(page.getByTestId("squeeze-pro-panel")).toBeVisible();
  await expect(page.getByTestId("squeeze-pro-legend")).toContainText("Squeeze Pro");
  await expect(page.getByTestId("squeeze-pro-unavailable")).toContainText("Squeeze Pro unavailable");
});

test("Console shell exposes the Momentum Intelligence Research nav link", async ({ page }) => {
  await page.goto("/charts/momentum");
  // Nav link should exist with the expected label and href.
  const navLink = page.getByRole("link", { name: "Momentum Intelligence" });
  await expect(navLink.first()).toBeVisible();
  await expect(navLink.first()).toHaveAttribute("href", "/charts/momentum");
});

test("Squeeze Pro panel keeps the same chart width as the Momentum Intelligence stack", async ({ page }) => {
  mockedMomentumPayload = populatedMomentumPayload();

  await page.goto("/charts/momentum");
  await page.getByTestId("momentum-load-button").click();
  await expect(page.getByTestId("squeeze-pro-panel").locator("canvas").first()).toBeVisible();

  const priceBox = await page.getByTestId("momentum-price-panel").boundingBox();
  expect(priceBox).not.toBeNull();
  const priceCanvasBox = await page.getByTestId("momentum-price-panel").locator("canvas").first().boundingBox();
  expect(priceCanvasBox).not.toBeNull();

  for (const testId of ["squeeze-pro-panel", "momentum-true-panel", "momentum-hilo-panel", "momentum-score-panel"]) {
    const panelBox = await page.getByTestId(testId).boundingBox();
    expect(panelBox).not.toBeNull();
    expect(Math.abs(panelBox!.x - priceBox!.x)).toBeLessThanOrEqual(2);
    expect(Math.abs(panelBox!.width - priceBox!.width)).toBeLessThanOrEqual(2);

    const canvasBox = await page.getByTestId(testId).locator("canvas").first().boundingBox();
    expect(canvasBox).not.toBeNull();
    expect(Math.abs(canvasBox!.x - priceCanvasBox!.x)).toBeLessThanOrEqual(2);
    expect(Math.abs(canvasBox!.width - priceCanvasBox!.width)).toBeLessThanOrEqual(2);
  }

  await expect(page.getByTestId("squeeze-pro-legend")).not.toContainText(/arrow/i);
});

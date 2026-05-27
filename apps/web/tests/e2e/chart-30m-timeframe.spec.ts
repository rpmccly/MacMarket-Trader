import { expect, test } from "@playwright/test";

function hacoPayload(timeframe: string) {
  return {
    symbol: "SPY",
    timeframe,
    candles: [],
    heikin_ashi_candles: [],
    markers: [],
    haco_strip: [],
    hacolt_strip: [],
    explanation: {
      current_haco_state: "neutral",
      latest_flip: "none",
      latest_flip_bars_ago: null,
      current_hacolt_direction: "flat",
    },
    data_source: "polygon",
    fallback_mode: false,
  };
}

function momentumPayload(timeframe: string) {
  return {
    symbol: "SPY",
    timeframe,
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
    higher_timeframe: "daily",
    parity_status: "pending_thinkorswim_fixture_validation",
    calculation_notes: [],
    squeeze_pro: {
      enabled: true,
      status: "unavailable",
      reason: "no chart bars provided",
      parameters: {},
      version: "macmarket_squeeze_pro.v1",
      histogram_mode: "macmarket_linear_regression_momentum_approximation",
      arrow_mode: "disabled_pending_approved_arrow_rules",
      show_arrows: false,
      series: [],
    },
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: { app_role: null, approval_status: "approved" } });
  });
});

test("HACO Context sends the selected 30M timeframe to the chart API", async ({ page }) => {
  const requests: unknown[] = [];
  await page.route("**/api/charts/haco", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    requests.push(body);
    await route.fulfill({ json: hacoPayload(String(body.timeframe ?? "1D")) });
  });

  await page.goto("/charts/haco");
  await expect.poll(() => requests.length).toBeGreaterThan(0);
  await expect(page.getByTestId("haco-load-button")).toHaveText("Run HACO analysis");
  const timeframeSelect = page.getByTestId("haco-timeframe-select");
  await expect(async () => {
    await timeframeSelect.selectOption({ value: "30M" });
    await expect(timeframeSelect).toHaveValue("30M", { timeout: 1000 });
  }).toPass({ timeout: 10_000 });
  await page.getByTestId("haco-load-button").click();

  await expect.poll(() => requests.some((body) => (body as { timeframe?: string }).timeframe === "30M")).toBe(true);
});

test("Momentum Intelligence sends the selected 30M timeframe to the chart API", async ({ page }) => {
  const requests: unknown[] = [];
  await page.route("**/api/charts/momentum", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    requests.push(body);
    await route.fulfill({ json: momentumPayload(String(body.timeframe ?? "1D")) });
  });

  await page.goto("/charts/momentum");
  await page.getByTestId("momentum-timeframe-select").selectOption("30M");
  await page.getByTestId("momentum-load-button").click();

  await expect.poll(() => requests.some((body) => (body as { timeframe?: string }).timeframe === "30M")).toBe(true);
});

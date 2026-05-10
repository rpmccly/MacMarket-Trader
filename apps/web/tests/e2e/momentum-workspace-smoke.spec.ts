import { expect, test } from "@playwright/test";

// Phase A3 smoke: verify /charts/momentum mounts cleanly with the deterministic
// context-only framing, the symbol/timeframe controls are present, and the
// console nav link points back at the workspace. Network is intercepted so no
// call proxies to the Python backend during e2e.

function emptyMomentumPayload() {
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
    latest_snapshot: null,
    explanation: null,
    data_source: "polygon",
    fallback_mode: false,
    higher_timeframe_source: "derived_from_chart_bars",
    higher_timeframe: "weekly",
    parity_status: "pending_thinkorswim_fixture_validation",
    calculation_notes: [],
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: { app_role: null, approval_status: "approved" } });
  });
  await page.route("**/api/charts/momentum", async (route) => {
    await route.fulfill({ json: emptyMomentumPayload() });
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
});

test("Console shell exposes the Momentum Intelligence Research nav link", async ({ page }) => {
  await page.goto("/charts/momentum");
  // Nav link should exist with the expected label and href.
  const navLink = page.getByRole("link", { name: "Momentum Intelligence" });
  await expect(navLink.first()).toBeVisible();
  await expect(navLink.first()).toHaveAttribute("href", "/charts/momentum");
});

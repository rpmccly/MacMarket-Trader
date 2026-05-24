import { expect, test } from "@playwright/test";

const profile = {
  id: "hm-profile-default",
  profileId: "hm-profile-default",
  name: "Default Momentum Heatmap",
  categories: [
    {
      categoryId: "indexes",
      categoryLabel: "INDEXES",
      included: true,
      collapsed: false,
      rows: [
        { id: "indexes:SPY", categoryId: "indexes", categoryLabel: "INDEXES", symbol: "SPY", displayName: "SPY", providerSymbol: "SPY", workbookOrder: 0, enabled: true },
        { id: "indexes:MAG7", categoryId: "indexes", categoryLabel: "INDEXES", symbol: "MAG7", displayName: "MAG7", providerSymbol: "MAG7", workbookOrder: 1, enabled: true, unsupported: true, unsupportedReason: "composite_symbol_deferred" },
      ],
    },
  ],
  colorRanges: [
    { id: "bright-green", min: 75, max: 100, label: "Bright green", color: "#56f08a" },
    { id: "green", min: 25, max: 74.999, label: "Green", color: "#1f9f62" },
    { id: "purple", min: -24.999, max: 24.999, label: "Purple", color: "#7d5cff" },
    { id: "red", min: -74.999, max: -25, label: "Red", color: "#bd3d4b" },
    { id: "bright-red", min: -100, max: -75, label: "Bright red", color: "#ff4b4b" },
  ],
  viewSettings: { sort: "workbook", showDeltas: true },
  reportPreferences: {},
  isDefault: true,
  isDefaultSeed: false,
};

function score(value: number) {
  return { value, status: "ok", data_source: "e2e", fallback_mode: true, as_of: "2026-05-23T14:30:00Z" };
}

function unsupported(reason = "composite_symbol_deferred") {
  return { value: null, status: "unsupported", reason };
}

function heatmapPayload() {
  return {
    generated_at: "2026-05-23T15:00:00Z",
    timeframes: ["1W", "1D", "4H", "1H", "30M"],
    categories: [
      {
        categoryId: "indexes",
        categoryLabel: "INDEXES",
        rows: [
          {
            id: "indexes:SPY",
            symbol: "SPY",
            displayName: "SPY",
            providerSymbol: "SPY",
            scores: { "1W": score(80), "1D": score(70), "4H": score(45), "1H": score(55), "30M": score(60) },
            long_term_score: 75,
            short_term_score: 53.33,
            strength_percent: 63.33,
            squeeze: { value: null, status: "deferred", reason: "squeeze_algorithm_not_implemented" },
            row_tags: ["Trend leader"],
            availability_status: "fresh",
          },
          {
            id: "indexes:MAG7",
            symbol: "MAG7",
            displayName: "MAG7",
            providerSymbol: "MAG7",
            scores: { "1W": unsupported(), "1D": unsupported(), "4H": unsupported(), "1H": unsupported(), "30M": unsupported() },
            long_term_score: null,
            short_term_score: null,
            strength_percent: null,
            squeeze: { value: null, status: "deferred", reason: "squeeze_algorithm_not_implemented" },
            row_tags: ["Unsupported"],
            availability_status: "unsupported",
          },
        ],
      },
    ],
  };
}

test.beforeEach(async ({ page }) => {
  let refreshRequests = 0;

  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: { app_role: null, approval_status: "approved" } });
  });
  await page.route("**/api/user/momentum-heatmap/profile", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({ json: { profile, source: "server" } });
      return;
    }
    await route.fulfill({
      json: {
        profile,
        profiles: [profile],
        schedulePreferences: {
          enabled: false,
          timezone: "America/Indiana/Indianapolis",
          runTime: "07:00",
          daysOfWeek: ["mon", "tue", "wed", "thu", "fri"],
          reportMode: "latest_snapshot",
          recipients: ["operator@example.com"],
          includeCsvAttachment: true,
          includeFullTable: true,
          schedulerActive: false,
        },
        source: "server",
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/snapshots/latest", async (route) => {
    await route.fulfill({
      json: {
        profile,
        snapshot: { id: "snap-1", status: "fresh", generated_at: "2026-05-23T14:00:00Z", payload: heatmapPayload(), categorySummaries: [] },
        previousSnapshot: null,
        deltas: {},
        message: "Loaded last snapshot from 2026-05-23T14:00:00Z; refresh to update.",
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/schedule", async (route) => {
    await route.fulfill({
      json: {
        schedulePreferences: {
          enabled: false,
          timezone: "America/Indiana/Indianapolis",
          runTime: "07:00",
          daysOfWeek: ["mon", "tue", "wed", "thu", "fri"],
          reportMode: "latest_snapshot",
          recipients: ["operator@example.com"],
          includeCsvAttachment: true,
          includeFullTable: true,
          schedulerActive: false,
        },
        timingSuggestions: [
          { time: "07:00", label: "7:00 AM ET", note: "Premarket read using prior completed session/intraday bars." },
        ],
        schedulerActive: false,
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/rows", async (route) => {
    await route.fulfill({ status: 409, json: { detail: { message: "SPY is already in INDEXES." } } });
  });
  await page.route("**/api/user/momentum-heatmap/refresh", async (route) => {
    refreshRequests += 1;
    await new Promise((resolve) => setTimeout(resolve, 100));
    await route.fulfill({
      json: {
        heatmap: heatmapPayload(),
        snapshot: { id: `snap-refresh-${refreshRequests}`, status: "partial", generated_at: "2026-05-23T15:00:00Z", payload: heatmapPayload() },
        previousSnapshot: null,
        deltas: {},
        categorySummaries: [
          {
            categoryId: "indexes",
            categoryLabel: "INDEXES",
            average_strength_percent: 63.33,
            average_long_term_score: 75,
            average_short_term_score: 53.33,
            count_ok: 1,
            count_unsupported: 1,
            count_unavailable_error: 0,
            count_bullish_aligned: 1,
            count_bearish_aligned: 0,
            count_improving: 0,
            count_weakening: 0,
            status: "partial",
          },
        ],
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/report/preview", async (route) => {
    await route.fulfill({
      json: {
        report: {},
        emailStatus: "email_not_configured_for_heatmap_reports",
        html: "<div class=\"mh-report\"><h1>MacMarket Momentum Heatmap</h1><h2>Category Regime Summary</h2><p>Research dashboard only. Not trade execution or investment advice.</p></div>",
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/report/csv", async (route) => {
    await route.fulfill({ json: { csv: "category,display_label\nINDEXES,SPY\n", filename: "momentum-heatmap-report.csv" } });
  });
  await page.route("**/api/user/momentum-heatmap/report/email", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    if ((body.recipients || []).includes("other@example.com")) {
      await route.fulfill({ status: 403, json: { detail: "momentum_heatmap_recipient_not_authorized" } });
      return;
    }
    await route.fulfill({ json: { emailStatus: "sent", sentTo: body.recipients || [] } });
  });

  await page.addInitScript(() => {
    window.localStorage.removeItem("macmarket-momentum-heatmap-symbols-v1");
    window.localStorage.removeItem("macmarket-momentum-heatmap-colors-v1");
  });
  await page.exposeFunction("heatmapRefreshRequestCount", () => refreshRequests);
});

test("Momentum Heatmap operator workflow stays manual, chunked, and reportable", async ({ page }) => {
  await page.goto("/momentum-heatmap");

  await expect(page.getByRole("heading", { name: "Momentum Heatmap" })).toBeVisible();
  await expect(page.getByTestId("momentum-heatmap-command-center")).toContainText("Default Momentum Heatmap");
  await expect(page.getByText(/Loaded last snapshot from/)).toBeVisible();
  await expect.poll(async () => page.evaluate(async () => window.heatmapRefreshRequestCount?.())).toBe(0);

  await page.getByRole("button", { name: "Manage symbols" }).click();
  await expect(page.getByRole("heading", { name: "Manage symbols" })).toBeVisible();
  await page.getByRole("textbox", { name: "Symbol", exact: true }).fill(" spy ");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("SPY is already in INDEXES.")).toBeVisible();

  await expect(page.getByTestId("momentum-heatmap-filter-bar")).toBeVisible();
  await page.getByLabel("Search symbol/label").fill("SPY");
  await page.getByLabel("Sort selector").selectOption("strength-desc");
  await page.getByLabel("Alignment filter").selectOption("bullish");
  await expect(page.getByTestId("momentum-heatmap-delta-notice")).toContainText("Deltas need two successful snapshots.");

  await page.getByRole("button", { name: "Refresh visible heatmap" }).click();
  await expect(page.getByTestId("momentum-heatmap-refresh-progress")).toBeVisible();
  await expect(page.getByText(/Refreshing INDEXES|Refresh status/)).toBeVisible();
  await expect(page.getByTestId("momentum-heatmap-category-indexes")).toBeVisible();
  await expect(page.getByText("SPY").first()).toBeVisible();

  await page.getByLabel("Alignment filter").selectOption("all");
  await page.getByLabel("Search symbol/label").fill("");
  await expect(page.getByText("MAG7").first()).toBeVisible();
  await expect(page.getByTestId("momentum-heatmap-category-indexes").getByText("Unsupported").first()).toBeVisible();

  await expect(page.getByRole("button", { name: "Download CSV" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Generate report preview" }).first().click();
  await expect(page.getByRole("heading", { name: "Report settings panel" })).toBeVisible();
  await expect(page.locator(".hm-report-preview")).toContainText("MacMarket Momentum Heatmap");

  await page.getByRole("button", { name: "Score color ranges" }).click();
  await expect(page.getByRole("heading", { name: "Score color ranges" })).toBeVisible();
  await page.getByRole("button", { name: "Schedule settings" }).click();
  await expect(page.getByRole("heading", { name: "Scheduled report settings" })).toBeVisible();

  await page.getByRole("button", { name: "Report settings" }).click();
  await page.getByLabel("Email recipients").fill("other@example.com");
  await page.getByRole("button", { name: "Email report now" }).click();
  await expect(page.getByText("momentum_heatmap_recipient_not_authorized")).toBeVisible();
});

declare global {
  interface Window {
    heatmapRefreshRequestCount?: () => Promise<number>;
  }
}

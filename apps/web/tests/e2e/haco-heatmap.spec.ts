import { expect, test } from "@playwright/test";

const viewProfiles = [
  {
    id: "haco-profile-morning",
    profileId: "haco-profile-morning",
    name: "Morning Macro",
    description: "Broad morning HACO direction read.",
    slug: "morning-macro",
    categories: [
      {
        categoryId: "indexes",
        categoryLabel: "INDEXES",
        included: true,
        collapsed: false,
        rows: [
          { id: "indexes:SPY", symbol: "SPY", displayName: "SPY", providerSymbol: "SPY", workbookOrder: 0, enabled: true },
          { id: "indexes:MAG7", symbol: "MAG7", displayName: "MAG7", providerSymbol: "MAG7", workbookOrder: 1, enabled: true, unsupported: true, unsupportedReason: "composite_symbol_deferred" },
          { id: "indexes:VTI", symbol: "VTI", displayName: "ALL U.S. - VTI", providerSymbol: "VTI", workbookOrder: 2, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showChanges: true, slug: "morning-macro", isSystemSeeded: true },
    reportPreferences: {},
    isDefault: true,
    isSystemSeeded: true,
  },
  {
    id: "haco-profile-growth",
    profileId: "haco-profile-growth",
    name: "Growth Leaders",
    description: "Growth leadership HACO scan.",
    slug: "growth-leaders",
    categories: [
      {
        categoryId: "major-stocks",
        categoryLabel: "MAJOR STOCKS",
        included: true,
        collapsed: false,
        rows: [
          { id: "major-stocks:NVDA", symbol: "NVDA", displayName: "NVDA", providerSymbol: "NVDA", workbookOrder: 0, enabled: true },
          { id: "major-stocks:TSLA", symbol: "TSLA", displayName: "TSLA", providerSymbol: "TSLA", workbookOrder: 1, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showChanges: true, slug: "growth-leaders", isSystemSeeded: true },
    reportPreferences: {},
    isDefault: false,
    isSystemSeeded: true,
  },
  {
    id: "haco-profile-commodities",
    profileId: "haco-profile-commodities",
    name: "Commodities",
    description: "Commodity/rates HACO scan.",
    slug: "commodities",
    categories: [
      {
        categoryId: "commodities",
        categoryLabel: "COMMODITIES",
        included: true,
        collapsed: false,
        rows: [
          { id: "commodities:/CL", symbol: "/CL", displayName: "/CL", providerSymbol: "/CL", workbookOrder: 0, enabled: true, unsupported: true, unsupportedReason: "unsupported_symbol_format" },
          { id: "commodities:GLD", symbol: "GLD", displayName: "GLD", providerSymbol: "GLD", workbookOrder: 1, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showChanges: true, slug: "commodities", isSystemSeeded: true },
    reportPreferences: {},
    isDefault: false,
    isSystemSeeded: true,
  },
];

function profileById(profileId?: string | null) {
  return viewProfiles.find((item) => item.id === profileId || item.profileId === profileId) ?? viewProfiles[0];
}

function state(label: "LONG" | "SHORT") {
  return { value: label === "LONG" ? "long" : "short", label, status: "ok", data_source: "e2e", fallback_mode: true, as_of: "2026-05-24T14:30:00Z" };
}

function unsupported(reason = "unsupported_symbol_format") {
  return { value: null, label: "—", status: "unsupported", reason };
}

function rowPayload(row: { id: string; symbol: string; displayName: string; providerSymbol: string; unsupported?: boolean; unsupportedReason?: string }) {
  if (row.unsupported) {
    return {
      id: row.id,
      symbol: row.symbol,
      displayName: row.displayName,
      providerSymbol: row.providerSymbol,
      states: { "1W": unsupported(row.unsupportedReason), "1D": unsupported(row.unsupportedReason), "4H": unsupported(row.unsupportedReason), "1H": unsupported(row.unsupportedReason), "30M": unsupported(row.unsupportedReason) },
      overall_bias: null,
      overall_alignment_percent: null,
      daily_context: null,
      short_term_bias: null,
      short_term_alignment_percent: null,
      tags: ["Unsupported"],
      availability_status: "unsupported",
    };
  }
  const shortTerm = row.providerSymbol === "TSLA" ? "SHORT" : "LONG";
  return {
    id: row.id,
    symbol: row.symbol,
    displayName: row.displayName,
    providerSymbol: row.providerSymbol,
    states: { "1W": state("LONG"), "1D": state("LONG"), "4H": state(shortTerm), "1H": state(shortTerm), "30M": state(shortTerm) },
    overall_bias: shortTerm === "LONG" ? "LONG" : "MIXED",
    overall_alignment_percent: shortTerm === "LONG" ? 100 : 20,
    daily_context: "LONG",
    short_term_bias: shortTerm,
    short_term_alignment_percent: shortTerm === "LONG" ? 100 : -100,
    tags: shortTerm === "LONG" ? ["All LONG"] : ["Daily LONG / Short-Term Pullback", "Mixed / Chop"],
    changed_since_last: false,
  };
}

function heatmapPayload(profile = viewProfiles[0]) {
  return {
    generated_at: "2026-05-24T15:00:00Z",
    timeframes: ["1W", "1D", "4H", "1H", "30M"],
    categories: profile.categories.map((category) => ({
      categoryId: category.categoryId,
      categoryLabel: category.categoryLabel,
      rows: category.rows.map((row) => rowPayload(row)),
    })),
  };
}

test.beforeEach(async ({ page }) => {
  let refreshRequests = 0;
  const refreshStatuses: number[] = [];
  const refreshPayloads: unknown[] = [];

  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: { app_role: null, approval_status: "approved" } });
  });
  await page.route("**/api/user/haco-heatmap/profile**", async (route) => {
    const selectedProfile = profileById(new URL(route.request().url()).searchParams.get("profileId"));
    if (route.request().method() === "PUT") {
      const body = JSON.parse(route.request().postData() || "{}");
      const target = profileById(body.profileId);
      Object.assign(target, body, { id: target.id, profileId: target.profileId });
      await route.fulfill({ json: { profile: target, profiles: viewProfiles, source: "server" } });
      return;
    }
    await route.fulfill({ json: { profile: selectedProfile, profiles: viewProfiles, source: "server" } });
  });
  await page.route("**/api/user/haco-heatmap/snapshots/latest**", async (route) => {
    const selectedProfile = profileById(new URL(route.request().url()).searchParams.get("profileId"));
    await route.fulfill({
      json: {
        profile: selectedProfile,
        snapshot: { id: `haco-snap-${selectedProfile.slug}`, status: "fresh", generated_at: "2026-05-24T14:00:00Z", payload: heatmapPayload(selectedProfile), categorySummaries: [] },
        previousSnapshot: null,
        changes: {},
        message: "Loaded last HACO Direction snapshot from 2026-05-24T14:00:00Z; refresh to update.",
      },
    });
  });
  await page.route("**/api/user/haco-heatmap/refresh", async (route) => {
    refreshRequests += 1;
    const body = JSON.parse(route.request().postData() || "{}");
    refreshPayloads.push(body);
    const selectedProfile = profileById(body.profileId);
    await new Promise((resolve) => setTimeout(resolve, 100));
    refreshStatuses.push(200);
    await route.fulfill({
      json: {
        heatmap: heatmapPayload(selectedProfile),
        snapshot: { id: `haco-refresh-${refreshRequests}`, status: "partial", generated_at: "2026-05-24T15:00:00Z", payload: heatmapPayload(selectedProfile) },
        previousSnapshot: null,
        changes: {},
        categorySummaries: [
          { categoryId: selectedProfile.categories[0].categoryId, categoryLabel: selectedProfile.categories[0].categoryLabel, average_alignment_percent: 60, count_long: 2, count_short: 0, count_mixed: 1, count_unsupported: 1, count_unavailable_error: 0, status: "partial" },
        ],
      },
    });
  });
  await page.route("**/api/user/haco-heatmap/report/preview", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const selectedProfile = profileById(body.profileId);
    await route.fulfill({
      json: {
        report: {},
        emailStatus: "email_not_configured_for_haco_heatmap_reports",
        html: `<div class="hh-report"><h1>HACO Direction Heatmap</h1><h2>${selectedProfile.name}</h2><p>Research dashboard only. Not trade execution or investment advice.</p></div>`,
      },
    });
  });
  await page.route("**/api/user/haco-heatmap/report/csv", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const selectedProfile = profileById(body.profileId);
    await route.fulfill({ json: { csv: `category,display_label\n${selectedProfile.categories[0].categoryLabel},${selectedProfile.categories[0].rows[0].displayName}\n`, filename: "haco-direction-heatmap-report.csv" } });
  });

  await page.exposeFunction("hacoRefreshRequestCount", () => refreshRequests);
  await page.exposeFunction("hacoRefreshRequestStatuses", () => refreshStatuses);
  await page.exposeFunction("hacoRefreshPayloads", () => refreshPayloads);
});

test("HACO Direction Heatmap operator workflow stays manual, chunked, and reportable", async ({ page }) => {
  await page.goto("/haco-heatmap");

  await expect(page.getByRole("heading", { name: "HACO Direction Heatmap" })).toBeVisible();
  await expect(page.getByTestId("haco-heatmap-command-center")).toContainText("Morning Macro");
  await expect(page.getByTestId("haco-heatmap-view-selector")).toBeVisible();
  await expect(page.getByRole("option", { name: "Morning Macro" })).toBeAttached();
  await expect(page.getByRole("option", { name: "Growth Leaders" })).toBeAttached();
  await expect(page.getByRole("option", { name: "Commodities" })).toBeAttached();
  await expect(page.getByText(/Loaded last HACO Direction snapshot/)).toBeVisible();
  await expect.poll(async () => page.evaluate(async () => window.hacoRefreshRequestCount?.())).toBe(0);
  await expect(page.getByText("SPYSPY")).toHaveCount(0);
  await expect(page.getByText("ALL U.S. - VTIVTI")).toHaveCount(0);
  await expect(page.getByText("Provider: SPY")).toHaveCount(0);
  await expect(page.getByText("Provider: VTI")).toBeVisible();

  await page.getByTestId("haco-heatmap-view-selector").selectOption("haco-profile-growth");
  await expect(page.getByTestId("haco-heatmap-command-center")).toContainText("Growth Leaders");
  await expect(page.getByText("NVDA").first()).toBeVisible();
  await expect.poll(async () => page.evaluate(async () => window.hacoRefreshRequestCount?.())).toBe(0);

  await page.getByTestId("haco-heatmap-view-selector").selectOption("haco-profile-commodities");
  await expect(page.getByText("GLD").first()).toBeVisible();
  await expect(page.getByText("/CL").first()).toBeVisible();

  await expect(page.getByTestId("haco-heatmap-filter-bar")).toBeVisible();
  await expect(page.getByTestId("haco-heatmap-filter-bar").getByLabel("Search symbol/label")).toBeVisible();
  await expect(page.getByTestId("haco-heatmap-filter-bar").getByLabel("Sort selector")).toBeVisible();
  await expect(page.getByTestId("haco-heatmap-filter-bar").getByLabel("Direction filter")).toBeVisible();
  await expect(page.getByTestId("haco-heatmap-filter-bar")).toContainText("Hide unsupported");
  await page.getByRole("button", { name: "Advanced filters" }).click();
  await expect(page.getByTestId("haco-advanced-filters")).toBeVisible();
  await expect(page.getByLabel("Alignment minimum")).toBeVisible();
  await expect(page.getByLabel("Alignment maximum")).toBeVisible();
  await page.getByRole("button", { name: "Advanced filters" }).click();
  await expect(page.getByTestId("haco-advanced-filters")).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
  await expect(page.getByTestId("haco-heatmap-filter-bar")).toBeVisible();
  const filterBox = await page.getByTestId("haco-heatmap-filter-bar").boundingBox();
  const categoryBox = await page.getByTestId("haco-heatmap-category-commodities").boundingBox();
  expect(filterBox?.height).toBeLessThan(80);
  expect(categoryBox && filterBox ? categoryBox.y + categoryBox.height > filterBox.y + filterBox.height : true).toBeTruthy();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByLabel("Search symbol/label").fill("GLD");
  await page.getByLabel("Sort selector").selectOption("alignment-desc");
  await page.getByLabel("Direction filter").selectOption("long");
  await expect(page.getByTestId("haco-heatmap-change-notice")).toContainText("Changes need two successful snapshots.");

  await page.getByRole("button", { name: "Refresh included" }).click();
  await expect(page.getByTestId("haco-heatmap-refresh-progress")).toBeVisible();
  await expect(page.getByTestId("haco-heatmap-category-commodities")).toContainText("LONG");
  await expect.poll(async () => page.evaluate(async () => window.hacoRefreshRequestStatuses?.())).toEqual([200]);
  const refreshPayloads = await page.evaluate(async () => window.hacoRefreshPayloads?.());
  expect(refreshPayloads).toHaveLength(1);
  expect(refreshPayloads?.[0]).toMatchObject({
    profileId: "haco-profile-commodities",
    categories: [
      {
        categoryId: "commodities",
        categoryLabel: "COMMODITIES",
      },
    ],
  });
  expect((refreshPayloads?.[0] as { categories: Array<Record<string, unknown>> }).categories[0]).not.toHaveProperty("included");
  expect((refreshPayloads?.[0] as { categories: Array<{ rows: Array<Record<string, unknown>> }> }).categories[0].rows[0]).not.toHaveProperty("workbookOrder");

  await page.getByLabel("Direction filter").selectOption("all");
  await page.getByLabel("Search symbol/label").fill("");
  await expect(page.getByTestId("haco-heatmap-category-commodities").getByText("Unsupported").first()).toBeVisible();

  await expect(page.getByRole("button", { name: "Download CSV" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Generate report preview" }).first().click();
  await expect(page.getByRole("heading", { name: "HACO Direction report preview" })).toBeVisible();
  await expect(page.locator(".hm-report-preview")).toContainText("HACO Direction Heatmap");

  await page.getByRole("button", { name: "Manage symbols" }).click();
  await expect(page.getByRole("heading", { name: "Manage HACO symbols" })).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await expect(page.getByRole("heading", { name: "HACO view settings" })).toBeVisible();
});

declare global {
  interface Window {
    hacoRefreshRequestCount?: () => Promise<number>;
    hacoRefreshRequestStatuses?: () => Promise<number[]>;
    hacoRefreshPayloads?: () => Promise<unknown[]>;
  }
}

import { expect, test } from "@playwright/test";

const viewProfiles = [
  {
    id: "hm-profile-morning",
    profileId: "hm-profile-morning",
    name: "Morning Macro",
    description: "Broad morning market regime read.",
    slug: "morning-macro",
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
    viewSettings: { sort: "workbook", showDeltas: true, slug: "morning-macro", isSystemSeeded: true },
    isDefault: true,
    isSystemSeeded: true,
  },
  {
    id: "hm-profile-growth",
    profileId: "hm-profile-growth",
    name: "Growth Leaders",
    description: "Growth leadership scan.",
    slug: "growth-leaders",
    categories: [
      {
        categoryId: "major-stocks",
        categoryLabel: "MAJOR STOCKS",
        included: true,
        collapsed: false,
        rows: [
          { id: "major-stocks:NVDA", categoryId: "major-stocks", categoryLabel: "MAJOR STOCKS", symbol: "NVDA", displayName: "NVDA", providerSymbol: "NVDA", workbookOrder: 0, enabled: true },
          { id: "major-stocks:TSLA", categoryId: "major-stocks", categoryLabel: "MAJOR STOCKS", symbol: "TSLA", displayName: "TSLA", providerSymbol: "TSLA", workbookOrder: 1, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showDeltas: true, slug: "growth-leaders", isSystemSeeded: true },
    isDefault: false,
    isSystemSeeded: true,
  },
  {
    id: "hm-profile-commodities",
    profileId: "hm-profile-commodities",
    name: "Commodities",
    description: "Commodity/rates scan.",
    slug: "commodities",
    categories: [
      {
        categoryId: "commodities",
        categoryLabel: "COMMODITIES",
        included: true,
        collapsed: false,
        rows: [
          { id: "commodities:/CL", categoryId: "commodities", categoryLabel: "COMMODITIES", symbol: "/CL", displayName: "/CL", providerSymbol: "/CL", workbookOrder: 0, enabled: true, unsupported: true, unsupportedReason: "unsupported_symbol_format" },
          { id: "commodities:GLD", categoryId: "commodities", categoryLabel: "COMMODITIES", symbol: "GLD", displayName: "GLD", providerSymbol: "GLD", workbookOrder: 1, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showDeltas: true, slug: "commodities", isSystemSeeded: true },
    isDefault: false,
    isSystemSeeded: true,
  },
  {
    id: "hm-profile-pullback",
    profileId: "hm-profile-pullback",
    name: "Pullback Watch",
    description: "Long-term bullish names with weaker short-term momentum.",
    slug: "pullback-watch",
    categories: [
      {
        categoryId: "major-stocks",
        categoryLabel: "MAJOR STOCKS",
        included: true,
        collapsed: false,
        rows: [
          { id: "major-stocks:MSFT", categoryId: "major-stocks", categoryLabel: "MAJOR STOCKS", symbol: "MSFT", displayName: "MSFT", providerSymbol: "MSFT", workbookOrder: 0, enabled: true },
          { id: "major-stocks:NVDA", categoryId: "major-stocks", categoryLabel: "MAJOR STOCKS", symbol: "NVDA", displayName: "NVDA", providerSymbol: "NVDA", workbookOrder: 1, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showDeltas: true, slug: "pullback-watch", isSystemSeeded: true, alignmentFilter: "pullback", hideUnavailable: true, strengthMin: 25 },
    isDefault: false,
    isSystemSeeded: true,
  },
  {
    id: "hm-profile-custom",
    profileId: "hm-profile-custom",
    name: "Custom Watchlist",
    description: "User-editable watchlist.",
    slug: "custom-watchlist",
    categories: [
      {
        categoryId: "custom-watchlist",
        categoryLabel: "CUSTOM WATCHLIST",
        included: true,
        collapsed: false,
        rows: [
          { id: "custom-watchlist:SPY", categoryId: "custom-watchlist", categoryLabel: "CUSTOM WATCHLIST", symbol: "SPY", displayName: "SPY", providerSymbol: "SPY", workbookOrder: 0, enabled: true },
          { id: "custom-watchlist:QQQ", categoryId: "custom-watchlist", categoryLabel: "CUSTOM WATCHLIST", symbol: "QQQ", displayName: "QQQ", providerSymbol: "QQQ", workbookOrder: 1, enabled: true },
        ],
      },
    ],
    viewSettings: { sort: "workbook", showDeltas: true, slug: "custom-watchlist", isSystemSeeded: true },
    isDefault: false,
    isSystemSeeded: true,
  },
].map((profile) => ({
  ...profile,
  colorRanges: [
    { id: "bright-green", min: 75, max: 100, label: "Bright green", color: "#56f08a" },
    { id: "green", min: 25, max: 74.999, label: "Green", color: "#1f9f62" },
    { id: "purple", min: -24.999, max: 24.999, label: "Purple", color: "#7d5cff" },
    { id: "red", min: -74.999, max: -25, label: "Red", color: "#bd3d4b" },
    { id: "bright-red", min: -100, max: -75, label: "Bright red", color: "#ff4b4b" },
  ],
  reportPreferences: {},
  isDefaultSeed: false,
}));

function profileById(profileId?: string | null) {
  return viewProfiles.find((item) => item.id === profileId || item.profileId === profileId) ?? viewProfiles[0];
}

function score(value: number) {
  return { value, status: "ok", data_source: "e2e", fallback_mode: true, as_of: "2026-05-23T14:30:00Z" };
}

function unsupported(reason = "composite_symbol_deferred") {
  return { value: null, status: "unsupported", reason };
}

function squeeze(state: "high" | "mid" | "low" | "none") {
  const labels = { high: "High squeeze", mid: "Mid squeeze", low: "Low squeeze", none: "No squeeze" };
  return {
    value: labels[state],
    status: "ok",
    state,
    reason: "strongest_active_squeeze:1D",
    as_of: "2026-05-23T14:30:00Z",
    timeframes: { "1D": { status: "ok", state, value: labels[state], oscillator_value: 1.25 } },
  };
}

function rowPayload(row: { id: string; symbol: string; displayName: string; providerSymbol: string; unsupported?: boolean; unsupportedReason?: string }) {
  if (row.unsupported) {
    return {
      id: row.id,
      symbol: row.symbol,
      displayName: row.displayName,
      providerSymbol: row.providerSymbol,
      scores: { "1W": unsupported(row.unsupportedReason), "1D": unsupported(row.unsupportedReason), "4H": unsupported(row.unsupportedReason), "1H": unsupported(row.unsupportedReason), "30M": unsupported(row.unsupportedReason) },
      long_term_score: null,
      short_term_score: null,
      strength_percent: null,
      squeeze: { value: null, status: "unavailable", reason: row.unsupportedReason ?? "unsupported_symbol_format" },
      row_tags: ["Unsupported"],
      availability_status: "unsupported",
    };
  }
  return {
    id: row.id,
    symbol: row.symbol,
    displayName: row.displayName,
    providerSymbol: row.providerSymbol,
    scores: { "1W": score(80), "1D": score(70), "4H": score(45), "1H": score(55), "30M": score(60) },
    long_term_score: 75,
    short_term_score: 53.33,
    strength_percent: 63.33,
    squeeze: squeeze("mid"),
    row_tags: ["Trend leader"],
    availability_status: "fresh",
  };
}

function heatmapPayload(profile = viewProfiles[0]) {
  return {
    generated_at: "2026-05-23T15:00:00Z",
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
  let profiles = JSON.parse(JSON.stringify(viewProfiles)) as typeof viewProfiles;
  const getProfile = (profileId?: string | null) => profiles.find((item) => item.id === profileId || item.profileId === profileId) ?? profiles[0];

  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: { app_role: null, approval_status: "approved" } });
  });
  await page.route("**/api/user/momentum-heatmap/profile**", async (route) => {
    const url = new URL(route.request().url());
    const selectedProfile = getProfile(url.searchParams.get("profileId"));
    if (route.request().method() === "PUT") {
      const body = JSON.parse(route.request().postData() || "{}");
      const target = getProfile(body.profileId);
      Object.assign(target, body, { id: target.id, profileId: target.profileId });
      await route.fulfill({ json: { profile: target, profiles, source: "server" } });
      return;
    }
    await route.fulfill({
      json: {
        profile: selectedProfile,
        profiles,
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
  await page.route("**/api/user/momentum-heatmap/snapshots/latest**", async (route) => {
    const selectedProfile = getProfile(new URL(route.request().url()).searchParams.get("profileId"));
    await route.fulfill({
      json: {
        profile: selectedProfile,
        snapshot: { id: `snap-${selectedProfile.slug}`, status: "fresh", generated_at: "2026-05-23T14:00:00Z", payload: heatmapPayload(selectedProfile), categorySummaries: [] },
        previousSnapshot: null,
        deltas: {},
        message: "Loaded last snapshot from 2026-05-23T14:00:00Z; refresh to update.",
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/schedule**", async (route) => {
    const selectedProfile = getProfile(new URL(route.request().url()).searchParams.get("profileId"));
    await route.fulfill({
      json: {
        profile: selectedProfile,
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
    const body = JSON.parse(route.request().postData() || "{}");
    const selectedProfile = getProfile(body.profileId);
    const category = selectedProfile.categories.find((item) => item.categoryId === body.categoryId);
    const providerSymbol = String(body.providerSymbol || body.symbol || "").trim().toUpperCase();
    if (!category) {
      await route.fulfill({ status: 404, json: { detail: "momentum_heatmap_category_not_found" } });
      return;
    }
    if (category.rows.some((row) => row.providerSymbol === providerSymbol)) {
      await route.fulfill({ status: 409, json: { detail: { message: `${providerSymbol} is already in ${category.categoryLabel}.` } } });
      return;
    }
    const row = {
      id: `${category.categoryId}:${providerSymbol}:e2e`,
      categoryId: category.categoryId,
      categoryLabel: category.categoryLabel,
      symbol: providerSymbol,
      displayName: String(body.displayName || providerSymbol),
      providerSymbol,
      workbookOrder: category.rows.length,
      enabled: true,
      userAdded: true,
    };
    category.rows.push(row);
    await route.fulfill({ json: { profile: selectedProfile, profiles, source: "server", status: "added", row, warning: null } });
  });
  await page.route("**/api/user/momentum-heatmap/rows/**", async (route) => {
    const url = new URL(route.request().url());
    const selectedProfile = getProfile(url.searchParams.get("profileId"));
    const rowId = decodeURIComponent(url.pathname.split("/").pop() || "");
    for (const category of selectedProfile.categories) {
      category.rows = category.rows.filter((row) => row.id !== rowId);
    }
    await route.fulfill({ json: { deleted: true, profile: selectedProfile, profiles, source: "server" } });
  });
  await page.route("**/api/user/momentum-heatmap/refresh", async (route) => {
    refreshRequests += 1;
    const body = JSON.parse(route.request().postData() || "{}");
    const selectedProfile = getProfile(body.profileId);
    await new Promise((resolve) => setTimeout(resolve, 100));
    await route.fulfill({
      json: {
        heatmap: heatmapPayload(selectedProfile),
        snapshot: { id: `snap-refresh-${refreshRequests}`, status: "partial", generated_at: "2026-05-23T15:00:00Z", payload: heatmapPayload(selectedProfile) },
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
    const body = JSON.parse(route.request().postData() || "{}");
    const selectedProfile = getProfile(body.profileId);
    await route.fulfill({
      json: {
        report: {},
        emailStatus: "email_not_configured_for_heatmap_reports",
        html: `<div class="mh-report"><h1>${selectedProfile.name}</h1><h2>Category Regime Summary</h2><p>Research dashboard only. Not trade execution or investment advice.</p></div>`,
      },
    });
  });
  await page.route("**/api/user/momentum-heatmap/report/csv", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    const selectedProfile = getProfile(body.profileId);
    await route.fulfill({ json: { csv: `category,display_label\n${selectedProfile.categories[0].categoryLabel},${selectedProfile.categories[0].rows[0].displayName}\n`, filename: "momentum-heatmap-report.csv" } });
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
  await expect(page.getByTestId("momentum-heatmap-command-center")).toContainText("Morning Macro");
  await expect(page.getByTestId("momentum-heatmap-view-selector")).toBeVisible();
  await expect(page.getByRole("option", { name: "Morning Macro" })).toBeAttached();
  await expect(page.getByRole("option", { name: "Growth Leaders" })).toBeAttached();
  await expect(page.getByRole("option", { name: "Commodities" })).toBeAttached();
  await expect(page.getByRole("option", { name: "Pullback Watch" })).toBeAttached();
  await expect(page.getByRole("option", { name: "Custom Watchlist" })).toBeAttached();
  await expect(page.getByText(/Loaded last snapshot from/)).toBeVisible();
  await expect.poll(async () => page.evaluate(async () => window.heatmapRefreshRequestCount?.())).toBe(0);

  await page.getByTestId("momentum-heatmap-view-selector").selectOption("hm-profile-growth");
  await expect(page.getByTestId("momentum-heatmap-command-center")).toContainText("Growth Leaders");
  await expect(page.getByText("NVDA").first()).toBeVisible();
  await expect.poll(async () => page.evaluate(async () => window.heatmapRefreshRequestCount?.())).toBe(0);

  await page.getByTestId("momentum-heatmap-view-selector").selectOption("hm-profile-commodities");
  await expect(page.getByTestId("momentum-heatmap-command-center")).toContainText("Commodities");
  await expect(page.getByText("GLD").first()).toBeVisible();
  await expect(page.getByText("/CL").first()).toBeVisible();
  await expect.poll(async () => page.evaluate(async () => window.heatmapRefreshRequestCount?.())).toBe(0);

  await page.getByTestId("momentum-heatmap-view-selector").selectOption("hm-profile-morning");
  await expect(page.getByTestId("momentum-heatmap-command-center")).toContainText("Morning Macro");

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
  await expect(page.getByText("Mid squeeze").first()).toBeVisible();

  await page.getByLabel("Alignment filter").selectOption("all");
  await page.getByLabel("Search symbol/label").fill("");
  await expect(page.getByText("MAG7").first()).toBeVisible();
  await expect(page.getByTestId("momentum-heatmap-category-indexes").getByText("Unsupported").first()).toBeVisible();

  await page.getByTestId("momentum-heatmap-view-selector").selectOption("hm-profile-custom");
  await expect(page.getByTestId("momentum-heatmap-command-center")).toContainText("Custom Watchlist");
  await page.getByRole("textbox", { name: "Symbol", exact: true }).fill("IBM");
  await page.getByRole("textbox", { name: "Display label" }).fill("IBM Test");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("IBM Test").first()).toBeVisible();
  await page.getByTitle("Remove IBM Test").click();
  await expect(page.getByText("IBM Test")).toHaveCount(0);

  await expect(page.getByRole("button", { name: "Download CSV" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Generate report preview" }).first().click();
  await expect(page.getByRole("heading", { name: "Report settings panel" })).toBeVisible();
  await expect(page.locator(".hm-report-preview")).toContainText("Custom Watchlist");

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

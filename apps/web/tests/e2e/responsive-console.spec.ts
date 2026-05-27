import { expect, test, type Page } from "@playwright/test";

const routeWideMobileViewport = { width: 390, height: 844 };

const viewportMatrix = [
  { name: "narrow-320", width: 320, height: 700 },
  { name: "narrow-360", width: 360, height: 780 },
  { name: "phone", width: 390, height: 844 },
  { name: "landscape-phone", width: 844, height: 390 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 1000 },
] as const;

const routeWideRoutes = [
  { path: "/analyze", heading: "Symbol Snapshot", control: "Analyze" },
  { path: "/charts/haco", heading: "HACO operator workspace", control: "Run HACO analysis" },
  { path: "/charts/momentum", heading: "Momentum Intelligence workspace", control: "Run Momentum analysis" },
  { path: "/momentum-heatmap", heading: "Momentum Heatmap", control: "Refresh visible heatmap" },
  { path: "/haco-heatmap", heading: "HACO Direction Heatmap", control: "Refresh included" },
  { path: "/schedules", heading: "Scheduled Strategy Reports", control: "Create" },
  { path: "/welcome", heading: "Welcome guide", control: "Print this welcome guide" },
  { path: "/settings", heading: "Settings", control: "Save" },
  { path: "/admin/pending-users", heading: "Admin approvals & invites", control: "Send invite" },
  { path: "/admin/users", heading: "Admin users", control: "Suspend" },
  { path: "/admin/provider-health", heading: "Provider readiness", control: "Re-probe now" },
  { path: "/account", heading: "Account", control: "Sign out" },
  { path: "/recommendations", heading: "Recommendations" },
  { path: "/analysis", heading: "Trade Setup" },
  { path: "/replay-runs", heading: "Replay workspace" },
  { path: "/orders", heading: "Paper Orders" },
  { path: "/dashboard", heading: "Operator dashboard" },
] as const;

const viewportMatrixRoutes = [
  { path: "/dashboard", heading: "Operator dashboard" },
  { path: "/analyze", heading: "Symbol Snapshot", control: "Analyze" },
  { path: "/charts/haco", heading: "HACO operator workspace", control: "Run HACO analysis" },
  { path: "/charts/momentum", heading: "Momentum Intelligence workspace", control: "Run Momentum analysis" },
  { path: "/momentum-heatmap", heading: "Momentum Heatmap", control: "Refresh visible heatmap" },
  { path: "/haco-heatmap", heading: "HACO Direction Heatmap", control: "Refresh included" },
] as const;

function bars() {
  const start = Date.UTC(2026, 0, 1);
  return Array.from({ length: 48 }, (_, index) => ({
    index,
    time: new Date(start + index * 86_400_000).toISOString().slice(0, 10),
    open: 100 + index * 0.2,
    high: 101 + index * 0.2,
    low: 99 + index * 0.2,
    close: 100.5 + index * 0.2,
    volume: 1_000_000 + index * 1000,
  }));
}

function hacoPayload() {
  const candles = bars();
  return {
    symbol: "SPY",
    timeframe: "1D",
    candles,
    heikin_ashi_candles: candles,
    markers: [{ index: 42, time: candles[42].time, marker_type: "flip", direction: "buy", price: 108, text: "Flip" }],
    haco_strip: candles.map((candle, index) => ({ index, time: candle.time, value: index % 2 ? -1 : 1, state: index % 2 ? "red" : "green" })),
    hacolt_strip: candles.map((candle, index) => ({ index, time: candle.time, value: index % 3 ? 1 : -1, direction: index % 3 ? "up" : "down" })),
    explanation: { current_haco_state: "green", latest_flip: "buy", latest_flip_bars_ago: 3, current_hacolt_direction: "up" },
    data_source: "e2e-provider",
    fallback_mode: false,
    session_policy: "regular_hours",
  };
}

function momentumPayload() {
  const candles = bars();
  const line = candles.map((candle, index) => ({ index, time: candle.time, value: index - 20 }));
  const ema = candles.map((candle, index) => ({ index, time: candle.time, value: index - 22 }));
  const snapshot = {
    total_score: 62,
    total_label: "Bullish",
    total_state: "bull",
    trend_score: 65,
    momo_score: 58,
    true_momentum: 1.4,
    true_momentum_ema: 1.1,
    true_momentum_score: 62,
    hilo_thrust: 55,
    hilo_score: 57,
    atr_bias: 5,
    macd_bias: 6,
    ma_bias: 10,
    component_breakdown: {
      true_momentum_score: 62,
      hilo_thrust: 55,
      bull_ma: 1,
      bear_ma: 0,
      atr_value: 2.1,
      macd_bias: 6,
      intraday_penalty: 0,
      base_score: 62,
    },
  };
  return {
    symbol: "SPY",
    timeframe: "1D",
    candles,
    true_momentum_line: line,
    true_momentum_ema_line: ema,
    hilo_slowd_line: candles.map((candle, index) => ({ index, time: candle.time, value: 45 + (index % 20) })),
    hilo_slowd_x_line: candles.map((candle, index) => ({ index, time: candle.time, value: 42 + (index % 18) })),
    hilo_thrust_strip: candles.map((candle, index) => ({ index, time: candle.time, value: index % 2 ? 60 : 40, state: index % 2 ? "bullish" : "neutral" })),
    score_strip: candles.map((candle, index) => ({ index, time: candle.time, total_score: index % 2 ? 62 : 55, state: "bull" })),
    markers: [],
    latest_snapshot: snapshot,
    explanation: { snapshot, reversal_warning: false, pullback_signal: true, no_trade_warning: false, notes: ["e2e"] },
    data_source: "e2e-provider",
    fallback_mode: false,
    session_policy: "regular_hours",
    higher_timeframe_source: "provider",
    higher_timeframe: "1W",
    parity_status: "research",
    calculation_notes: [],
    visual_parity_snapshot: {
      as_of: "2026-01-28",
      symbol: "SPY",
      timeframe: "1D",
      history_range: "1Y",
      total_score: 62,
      total_label: "Bullish",
      trend_score: 65,
      momo_score: 58,
      true_momentum: 1.4,
      true_momentum_ema: 1.1,
      hilo_slowd: 55,
      hilo_slowd_x: 50,
      tos_hilo_elite_scalar: null,
      hilo_thrust_state: "bullish",
      hilo_score: 57,
      pullback_signal: true,
      reversal_warning: false,
      no_trade_warning: false,
      iv_percent: null,
      source_notes: [],
      unavailable_fields: ["iv_percent", "tos_hilo_elite_scalar"],
    },
    visual_parity_series: [],
    true_momentum_panel_markers: [],
    hilo_panel_markers: [],
    squeeze_pro: {
      enabled: true,
      status: "ok",
      parameters: {},
      version: "e2e",
      histogram_mode: "macmarket_linear_regression_momentum_approximation",
      arrow_mode: "disabled",
      series: candles.map((candle, index) => ({
        index,
        time: candle.time,
        oscillator_value: index - 20,
        oscillator_state: "up",
        oscillator_color: "#21c06e",
        squeeze_state: index % 2 ? "mid" : "none",
        squeeze_color: index % 2 ? "#d14b4b" : "#21c06e",
        delta_high: null,
        delta_mid: null,
        delta_low: null,
        status: "ok",
      })),
    },
  };
}

function momentumHeatmapProfile() {
  return {
    id: "hm-profile-morning",
    profileId: "hm-profile-morning",
    name: "Morning Macro",
    description: "Broad morning market regime read.",
    slug: "morning-macro",
    isDefault: true,
    isSystemSeeded: true,
    colorRanges: [
      { id: "green", min: 25, max: 100, label: "Green", color: "#56f08a" },
      { id: "neutral", min: -24, max: 24, label: "Neutral", color: "#7d5cff" },
      { id: "red", min: -100, max: -25, label: "Red", color: "#ff4b4b" },
    ],
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
    viewSettings: { sort: "workbook", showDeltas: true },
    reportPreferences: {},
  };
}

function momentumHeatmapPayload() {
  const profile = momentumHeatmapProfile();
  return {
    generated_at: "2026-05-27T13:00:00Z",
    timeframes: ["1W", "1D", "4H", "1H", "30M"],
    categories: profile.categories.map((category) => ({
      categoryId: category.categoryId,
      categoryLabel: category.categoryLabel,
      rows: category.rows.map((row) => row.unsupported ? {
        id: row.id,
        symbol: row.symbol,
        displayName: row.displayName,
        providerSymbol: row.providerSymbol,
        scores: { "1W": { value: null, status: "unsupported", reason: row.unsupportedReason }, "1D": { value: null, status: "unsupported", reason: row.unsupportedReason }, "4H": { value: null, status: "unsupported", reason: row.unsupportedReason }, "1H": { value: null, status: "unsupported", reason: row.unsupportedReason }, "30M": { value: null, status: "unsupported", reason: row.unsupportedReason } },
        long_term_score: null,
        short_term_score: null,
        strength_percent: null,
        squeeze: { value: null, status: "unavailable", reason: row.unsupportedReason },
        row_tags: ["Unsupported"],
      } : {
        id: row.id,
        symbol: row.symbol,
        displayName: row.displayName,
        providerSymbol: row.providerSymbol,
        scores: { "1W": { value: 80, status: "ok" }, "1D": { value: 70, status: "ok" }, "4H": { value: 50, status: "ok" }, "1H": { value: 55, status: "ok" }, "30M": { value: 60, status: "ok" } },
        long_term_score: 75,
        short_term_score: 55,
        strength_percent: 65,
        squeeze: { value: "Mid squeeze", status: "ok", state: "mid", reason: "1D" },
        row_tags: ["Trend leader"],
      }),
    })),
  };
}

function hacoHeatmapProfile() {
  return {
    id: "haco-profile-morning",
    profileId: "haco-profile-morning",
    name: "Morning Macro",
    isDefault: true,
    isSystemSeeded: true,
    categories: [
      {
        categoryId: "commodities",
        categoryLabel: "COMMODITIES",
        included: true,
        collapsed: false,
        rows: [
          { id: "commodities:GLD", symbol: "GLD", displayName: "GLD", providerSymbol: "GLD", workbookOrder: 0, enabled: true },
          { id: "commodities:/CL", symbol: "/CL", displayName: "/CL", providerSymbol: "/CL", workbookOrder: 1, enabled: true, unsupported: true, unsupportedReason: "unsupported_symbol_format" },
        ],
      },
    ],
  };
}

function hacoHeatmapPayload() {
  const profile = hacoHeatmapProfile();
  const states = { "1W": "long", "1D": "long", "4H": "short", "1H": "long", "30M": "long" };
  return {
    generated_at: "2026-05-27T13:00:00Z",
    categories: profile.categories.map((category) => ({
      categoryId: category.categoryId,
      categoryLabel: category.categoryLabel,
      rows: category.rows.map((row) => row.unsupported ? {
        id: row.id,
        symbol: row.symbol,
        displayName: row.displayName,
        providerSymbol: row.providerSymbol,
        states: Object.fromEntries(Object.keys(states).map((timeframe) => [timeframe, { value: null, label: "-", status: "unsupported", reason: row.unsupportedReason }])),
        overall_bias: null,
        overall_alignment_percent: null,
        daily_context: null,
        short_term_bias: null,
        short_term_alignment_percent: null,
        tags: ["Unsupported"],
      } : {
        id: row.id,
        symbol: row.symbol,
        displayName: row.displayName,
        providerSymbol: row.providerSymbol,
        states: Object.fromEntries(Object.entries(states).map(([timeframe, value]) => [timeframe, { value, label: String(value).toUpperCase(), status: "ok" }])),
        overall_bias: "LONG",
        overall_alignment_percent: 78,
        daily_context: "LONG",
        short_term_bias: "MIXED",
        short_term_alignment_percent: 55,
        tags: ["LONG", "Mixed short-term"],
      }),
    })),
  };
}

function operatorMe(appRole: "admin" | "user" = "admin") {
  return {
    id: 1,
    email: "operator@example.com",
    display_name: "Operator One",
    app_role: appRole,
    approval_status: "approved",
    mfa_enabled: true,
    risk_dollars_per_trade: 1000,
    risk_dollars_per_trade_default: 1000,
    paper_max_order_notional: 5000,
    paper_max_order_notional_default: 5000,
    commission_per_trade: 0,
    commission_per_trade_default: 0,
    commission_per_contract: 0.65,
    commission_per_contract_default: 0.65,
    auth_provider: "clerk",
    last_seen_at: "2026-05-27T13:00:00Z",
    last_authenticated_at: "2026-05-27T13:00:00Z",
  };
}

function recommendationItem() {
  return {
    id: 1,
    created_at: "2026-05-27T13:00:00Z",
    symbol: "SPY",
    recommendation_id: "rec-responsive-e2e",
    market_data_source: "polygon",
    fallback_mode: false,
    payload: {
      thesis: "Provider-backed continuation setup for responsive console QA.",
      catalyst: { type: "macro" },
      entry: { setup_type: "Event Continuation", zone_low: 514, zone_high: 516, trigger_text: "hold above pivot" },
      invalidation: { price: 509, reason: "failed hold" },
      targets: { target_1: 521, target_2: 526 },
      quality: { expected_rr: 1.8, confidence: 0.66 },
      workflow: { timeframe: "1D", market_data_source: "polygon", fallback_mode: false, source_strategy: "Event Continuation" },
    },
  };
}

function replayRunItem() {
  return {
    id: 22,
    symbol: "SPY",
    source_recommendation_id: "rec-responsive-e2e",
    source_strategy: "Event Continuation",
    created_at: "2026-05-27T13:00:00Z",
    recommendation_count: 1,
    approved_count: 1,
    fill_count: 1,
    ending_heat: 0.12,
    ending_open_notional: 5150,
    market_data_source: "polygon",
    fallback_mode: false,
    has_stageable_candidate: true,
    stageable_recommendation_id: "rec-responsive-e2e",
    summary_metrics: { recommendation_count: 1, approved_count: 1, fill_count: 1, ending_heat: 0.12, ending_open_notional: 5150 },
    thesis: "Responsive QA replay detail.",
    key_levels: { entry: { zone_low: 514, zone_high: 516 }, invalidation: { price: 509 }, targets: { target_1: 521, target_2: 526 } },
  };
}

function orderItem() {
  return {
    order_id: "ord-responsive-e2e",
    replay_run_id: 22,
    recommendation_id: "rec-responsive-e2e",
    symbol: "SPY",
    status: "filled",
    side: "buy",
    shares: 10,
    limit_price: 515,
    created_at: "2026-05-27T13:00:00Z",
    market_data_source: "polygon",
    fallback_mode: false,
    fills: [{ fill_price: 515, filled_shares: 10, timestamp: "2026-05-27T13:00:05Z" }],
  };
}

function dashboardPayload() {
  return {
    market_regime: "risk_on",
    last_refresh: "2026-05-27T13:00:00Z",
    account: { app_role: "admin", approval_status: "approved" },
    provider_health: {
      summary: "ok",
      auth: "ok",
      email: "ok",
      market_data: "polygon",
      configured_provider: "polygon",
      effective_read_mode: "provider",
      workflow_execution_mode: "provider",
      failure_reason: "",
    },
    risk_calendar: {
      decision: {
        decision_state: "allow",
        risk_level: "normal",
        recommended_action: "Standard paper-only sizing.",
        warning_summary: "No event block in e2e snapshot.",
        allow_new_entries: true,
        requires_confirmation: false,
        missing_evidence: [],
      },
    },
    macro_context: { series: [], missing_data: [] },
    index_context: { indices: [], missing_data: [] },
    latest_market_snapshot: { symbol: "SPY", as_of: "2026-05-27T13:00:00Z", close: 515, source: "polygon", fallback_mode: false },
    active_recommendations: [recommendationItem()],
    recent_replay_runs: [replayRunItem()],
    recent_orders: [orderItem()],
    pending_admin_actions: [{ id: 2, email: "new.operator@example.com", display_name: "New Operator" }],
    alerts: [{ kind: "provider", level: "info", message: "Provider-backed bars ready." }],
    workflow_guide: ["Start in Analyze", "Review Recommendations", "Run Replay", "Stage Paper Order"],
    recent_audit_events: [{ event_type: "invite_sent", timestamp: "2026-05-27T13:00:00Z", detail: "Invite sent", status: "sent" }],
  };
}

async function installResponsiveMocks(page: Page) {
  await page.route("**/api/**", async (route) => {
    await route.fulfill({ status: 404, json: { detail: "not mocked in responsive e2e" } });
  });
  await page.route("**/api/user/me", async (route) => {
    await route.fulfill({ json: operatorMe("admin") });
  });
  await page.route("**/api/user/analyze/**", async (route) => {
    await route.fulfill({
      json: {
        symbol: "SPY",
        market_mode: "equities",
        timeframe: "1D",
        source: "provider",
        market_regime: "risk_on",
        technical_summary: "Provider-backed bars, regular-hours context.",
        strategy_scoreboard: [
          { rank: 1, strategy: "Event Continuation", status: "watch", score: 0.78, expected_rr: 1.8, confidence: 0.66, reason_text: "Aligned with regime", thesis: "Continuation only after confirmation.", score_breakdown: { strategy_fit_score: 0.8, regime_fit_score: 0.7, liquidity_score: 0.9 } },
          { rank: 2, strategy: "Mean Reversion", status: "inactive", score: 0.34, expected_rr: 1.1, confidence: 0.42, reason_text: "Trend remains too strong", thesis: "No fade setup.", score_breakdown: { strategy_fit_score: 0.3 } },
        ],
        levels: { support: [510.2, 504.1], resistance: [518.4, 522.9], pivot: 514.5 },
        indicator_snapshot: { ema20_vs_price: "above", rsi: 58, macd: 1.2, atr: 4.1, relative_volume: 1.3 },
        catalyst_summary: "No live news catalyst loaded in e2e.",
        scenarios: { bull: "Breakout holds.", base: "Wait for confirmation.", bear: "Lose pivot." },
        operator_note: "Use this snapshot before promoting a setup.",
        next_actions: [{ label: "Review in Recommendations", path: "/recommendations" }, { label: "Open Strategy Workbench", path: "/analysis" }],
      },
    });
  });
  await page.route("**/api/charts/haco", async (route) => route.fulfill({ json: hacoPayload() }));
  await page.route("**/api/charts/momentum", async (route) => route.fulfill({ json: momentumPayload() }));
  await page.route("**/api/user/settings", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ json: operatorMe("admin") });
      return;
    }
    await route.fulfill({ json: operatorMe("admin") });
  });
  await page.route("**/api/user/onboarding-status", async (route) => {
    await route.fulfill({ json: { has_schedule: true, has_replay: true, has_order: true, has_viewed_haco: true, completed: 4, total: 4 } });
  });
  await page.route("**/api/user/analysis/setup**", async (route) => {
    await route.fulfill({
      json: {
        symbol: "SPY",
        strategy: "Event Continuation",
        market_mode: "equities",
        timeframe: "1D",
        source: "provider",
        market_data_source: "polygon",
        fallback_mode: false,
        workflow_source: "polygon",
        status: "active",
        thesis: "Provider-backed continuation setup for responsive QA.",
        trigger: "hold above pivot",
        entry_zone: { low: 514, high: 516 },
        invalidation: { price: 509, reason: "failed hold" },
        targets: [521, 526],
        confidence: 0.66,
        filters: ["provider-backed", "paper-only"],
        notes: ["Responsive QA fixture."],
        expected_range: null,
        option_structure: null,
        options_chain_preview: null,
        operator_guidance: "Continue paper-only review.",
        quality: { expected_rr: 1.8, confidence: 0.66 },
        chart_context: hacoPayload(),
        macro_context: { series: [], missing_data: [] },
        news_context: { items: [], missing_data: [] },
        index_context: { indices: [], missing_data: [] },
        risk_calendar: { decision: { decision_state: "allow", risk_level: "normal", recommended_action: "Continue paper-only review." } },
      },
    });
  });
  await page.route("**/api/user/symbol-universe/preview", async (route) => {
    await route.fulfill({ json: { symbols: ["SPY", "QQQ"], unsupported: [], source: "responsive-e2e" } });
  });
  await page.route("**/api/user/recommendations**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/queue/promote")) {
      await route.fulfill({ json: { recommendation_id: "rec-responsive-e2e", action: "make_active", approved: true } });
      return;
    }
    if (url.includes("/queue")) {
      await route.fulfill({
        json: {
          queue: [{
            rank: 1,
            symbol: "SPY",
            strategy: "Event Continuation",
            timeframe: "1D",
            market_mode: "equities",
            workflow_source: "polygon",
            status: "top_candidate",
            score: 0.82,
            expected_rr: 1.8,
            confidence: 0.66,
            thesis: "Provider-backed continuation setup.",
            trigger: "hold above pivot",
            entry_zone: { low: 514, high: 516 },
            invalidation: { price: 509, reason: "failed hold" },
            targets: [521, 526],
            reason_text: "Strong regime alignment",
          }],
          summary: { total: 1, top_candidate_count: 1, watchlist_count: 0, no_trade_count: 0 },
        },
      });
      return;
    }
    if (url.includes("/generate") && method === "POST") {
      await route.fulfill({ json: { recommendation_id: "rec-responsive-e2e", market_data_source: "polygon", fallback_mode: false } });
      return;
    }
    if (url.includes("/opportunity-intelligence")) {
      await route.fulfill({ json: { selected_count: 0, memo: null, sections: [], missing_data: [] } });
      return;
    }
    if (url.includes("/analysis-packet")) {
      await route.fulfill({ json: { packet: { summary: "Responsive QA packet." } } });
      return;
    }
    if (url.includes("/approve")) {
      await route.fulfill({ json: { approved: true } });
      return;
    }
    await route.fulfill({ json: { items: [recommendationItem()] } });
  });
  await page.route("**/api/user/replay-runs**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "POST") {
      await route.fulfill({ json: replayRunItem() });
      return;
    }
    if (url.endsWith("/steps") || url.includes("/steps?")) {
      await route.fulfill({
        json: {
          items: [{
            id: 1,
            step_index: 1,
            recommendation_id: "rec-responsive-e2e",
            approved: true,
            rejection_reason: null,
            thesis: "Responsive QA replay step.",
            entry: { zone_low: 514, zone_high: 516 },
            invalidation: { price: 509 },
            targets: { target_1: 521, target_2: 526 },
            quality: 0.82,
            confidence: 0.66,
            pre_step_snapshot: { equity: 10000, current_heat: 0, open_positions_notional: 0 },
            post_step_snapshot: { equity: 10020, current_heat: 0.12, open_positions_notional: 5150 },
            timestamp: "2026-05-27T13:00:00Z",
            event_text: "Paper fill simulated.",
          }],
        },
      });
      return;
    }
    if (/\/api\/user\/replay-runs\/\d+/.test(new URL(url).pathname)) {
      await route.fulfill({ json: replayRunItem() });
      return;
    }
    await route.fulfill({ json: { items: [replayRunItem()] } });
  });
  await page.route("**/api/user/orders**", async (route) => {
    const url = route.request().url();
    if (url.includes("/portfolio-summary")) {
      await route.fulfill({
        json: {
          open_positions: 1,
          total_open_notional: 5150,
          unrealized_pnl: 120,
          realized_pnl: 75,
          gross_realized_pnl: 82,
          net_realized_pnl: 75,
          total_commission_paid: 7,
          closed_trade_count: 1,
          win_rate: 1,
          lifecycle_status: "paper_only",
          notes: "Responsive QA summary.",
        },
      });
      return;
    }
    if (route.request().method() === "POST") {
      await route.fulfill({ json: orderItem() });
      return;
    }
    await route.fulfill({ json: { items: [orderItem()] } });
  });
  await page.route("**/api/user/paper-positions/review", async (route) => {
    await route.fulfill({
      json: {
        items: [{
          position_id: 1,
          symbol: "SPY",
          side: "long",
          quantity: 10,
          average_entry_price: 515,
          current_mark_price: 527,
          market_data_source: "polygon",
          market_data_fallback_mode: false,
          mark_as_of: "2026-05-27T13:00:00Z",
          market_session_policy: "regular_hours",
          unrealized_pnl: 120,
          unrealized_return_pct: 2.33,
          estimated_current_notional: 5270,
          entry_notional: 5150,
          stop_price: 509,
          target_1: 521,
          target_2: 526,
          distance_to_stop_pct: -3.41,
          distance_to_target_1_pct: -1.14,
          distance_to_target_2_pct: -0.19,
          days_held: 1,
          holding_period_status: "normal",
          current_recommendation_status: "watch",
          current_rank: 1,
          already_open: true,
          action_classification: "hold",
          action_summary: "Paper position remains inside planned review bounds.",
          warnings: [],
          missing_data: [],
        }],
      },
    });
  });
  await page.route("**/api/user/paper-positions**", async (route) => {
    if (route.request().url().includes("/review")) {
      await route.fulfill({
        json: {
          items: [{
            position_id: 1,
            symbol: "SPY",
            side: "long",
            quantity: 10,
            average_entry_price: 515,
            current_mark_price: 527,
            market_data_source: "polygon",
            market_data_fallback_mode: false,
            mark_as_of: "2026-05-27T13:00:00Z",
            market_session_policy: "regular_hours",
            unrealized_pnl: 120,
            unrealized_return_pct: 2.33,
            estimated_current_notional: 5270,
            entry_notional: 5150,
            stop_price: 509,
            target_1: 521,
            target_2: 526,
            distance_to_stop_pct: -3.41,
            distance_to_target_1_pct: -1.14,
            distance_to_target_2_pct: -0.19,
            days_held: 1,
            holding_period_status: "normal",
            current_recommendation_status: "watch",
            current_rank: 1,
            already_open: true,
            action_classification: "hold",
            action_summary: "Paper position remains inside planned review bounds.",
            warnings: [],
            missing_data: [],
          }],
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        items: [{
          id: 1,
          symbol: "SPY",
          side: "long",
          opened_qty: 10,
          remaining_qty: 10,
          avg_entry_price: 515,
          open_notional: 5150,
          status: "open",
          opened_at: "2026-05-27T13:00:00Z",
          closed_at: null,
          recommendation_id: "rec-responsive-e2e",
          replay_run_id: 22,
          order_id: "ord-responsive-e2e",
          estimated_close_fee: 0,
          fee_model: "e2e",
        }],
      },
    });
  });
  await page.route("**/api/user/paper-trades**", async (route) => {
    await route.fulfill({
      json: {
        items: [{
          id: 5,
          symbol: "SPY",
          side: "long",
          shares: 10,
          entry_price: 510,
          close_price: 518,
          gross_pnl: 80,
          net_pnl: 75,
          commission_paid: 5,
          realized_pnl: 75,
          opened_at: "2026-05-26T13:00:00Z",
          closed_at: "2026-05-27T13:00:00Z",
          status: "closed",
          recommendation_id: "rec-responsive-e2e",
          replay_run_id: 22,
          order_id: "ord-responsive-e2e",
          can_reopen: false,
        }],
      },
    });
  });
  await page.route("**/api/user/options/paper-structures/review", async (route) => {
    await route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/user/strategy-schedules", async (route) => {
    await route.fulfill({
      json: {
        items: [{
          id: 10,
          name: "Morning strategy scan",
          frequency: "weekdays",
          run_time: "08:30",
          timezone: "America/Indiana/Indianapolis",
          enabled: true,
          latest_status: "delivered",
          latest_run_at: "2026-05-27T12:30:00Z",
          next_run_at: "2026-05-28T12:30:00Z",
          payload: { symbols: ["SPY", "QQQ", "NVDA"], enabled_strategies: ["Event Continuation"], top_n: 5, email_delivery_target: "operator@example.com", market_mode: "equities" },
          config_summary: { market_mode: "equities", symbols_count: 3, strategy_count: 1, top_n: 5, delivery_target: "operator@example.com" },
          latest_payload_summary: { top_candidate_count: 1, watchlist_count: 2, no_trade_count: 1 },
          history: [{ id: 99, status: "delivered", delivered_to: "operator@example.com", created_at: "2026-05-27T12:30:00Z", email_provider: "console", summary: { top_candidate_count: 1, watchlist_count: 2, no_trade_count: 1 } }],
        }],
      },
    });
  });
  await page.route("**/api/user/watchlists", async (route) => {
    await route.fulfill({ json: { items: [{ id: 1, name: "Core ETFs", symbols: ["SPY", "QQQ", "IWM"], created_at: "2026-05-27T13:00:00Z" }] } });
  });
  await page.route("**/api/user/momentum-heatmap/profile**", async (route) => {
    const profile = momentumHeatmapProfile();
    await route.fulfill({ json: { profile, profiles: [profile], source: "server", schedulePreferences: { enabled: false, recipients: [] } } });
  });
  await page.route("**/api/user/momentum-heatmap/snapshots/latest**", async (route) => {
    await route.fulfill({ json: { snapshot: { id: "mh-snap", payload: momentumHeatmapPayload(), categorySummaries: [] }, previousSnapshot: null, deltas: {}, message: "Loaded last snapshot from 2026-05-27T13:00:00Z; refresh to update." } });
  });
  await page.route("**/api/user/momentum-heatmap/schedule**", async (route) => {
    await route.fulfill({ json: { schedulePreferences: { enabled: false, recipients: [] }, timingSuggestions: [], schedulerActive: false } });
  });
  await page.route("**/api/user/haco-heatmap/profile**", async (route) => {
    const profile = hacoHeatmapProfile();
    await route.fulfill({ json: { profile, profiles: [profile], source: "server" } });
  });
  await page.route("**/api/user/haco-heatmap/snapshots/latest**", async (route) => {
    await route.fulfill({ json: { snapshot: { id: "hh-snap", payload: hacoHeatmapPayload(), categorySummaries: [] }, previousSnapshot: null, changes: {}, message: "Loaded last HACO Direction snapshot from 2026-05-27T13:00:00Z; refresh to update." } });
  });
  await page.route("**/api/admin/users/pending", async (route) => {
    await route.fulfill({ json: { items: [{ id: 2, email: "new.operator@example.com", display_name: "New Operator" }] } });
  });
  await page.route("**/api/admin/invites", async (route) => {
    await route.fulfill({ json: { items: [{ id: 3, email: "invited@example.com", display_name: "Invited Operator", status: "sent", invited_by: "operator@example.com", created_at: "2026-05-27T13:00:00Z", invite_token: "masked" }] } });
  });
  await page.route("**/api/user/dashboard", async (route) => {
    await route.fulfill({ json: dashboardPayload() });
  });
  await page.route("**/api/admin/users", async (route) => {
    await route.fulfill({
      json: {
        items: [
          { id: 1, display_name: "Operator One", email: "operator@example.com", app_role: "admin", approval_status: "approved", mfa_enabled: true, invite_status: "accepted", last_seen_at: "2026-05-27T13:00:00Z", last_authenticated_at: "2026-05-27T13:00:00Z", external_auth_user_id: "user_e2e" },
          { id: 2, display_name: "Operator Two", email: "two@example.com", app_role: "user", approval_status: "approved", mfa_enabled: false, invite_status: "accepted", last_seen_at: "2026-05-26T13:00:00Z", last_authenticated_at: "2026-05-26T13:00:00Z", external_auth_user_id: "user_e2e_2" },
        ],
      },
    });
  });
  await page.route("**/api/admin/provider-health**", async (route) => {
    await route.fulfill({
      json: {
        checked_at: "2026-05-27T13:00:00Z",
        providers: [
          { provider: "market_data", mode: "configured", status: "ok", details: "Polygon ready", configured_provider: "polygon", effective_read_mode: "provider", workflow_execution_mode: "provider", operational_impact: "Workflows use provider-backed bars.", sample_symbol: "SPY", latency_ms: 42, last_success_at: "2026-05-27T13:00:00Z", config_state: "configured", probe_state: "ok" },
          { provider: "alpaca_paper", mode: "paper", status: "configured", details: "Paper readiness only", config_state: "configured", probe_state: "unavailable", configured: true, credentials_present: true, paper_routing_enabled: false, readiness_scope: "paper-readiness-only" },
        ],
      },
    });
  });
}

async function assertNoPageOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 2);
}

async function assertContainedDenseSurfaces(page: Page) {
  const result = await page.evaluate(() => {
    const wrappers = Array.from(document.querySelectorAll<HTMLElement>(".op-table-wrap, .hm-table-wrap"))
      .filter((element) => element.offsetParent !== null)
      .map((element) => ({
        className: element.className,
        scrollWidth: element.scrollWidth,
        clientWidth: element.clientWidth,
      }));
    return { count: wrappers.length, wrappers };
  });
  for (const wrapper of result.wrappers) {
    expect(wrapper.clientWidth).toBeGreaterThan(0);
    expect(wrapper.scrollWidth).toBeGreaterThanOrEqual(wrapper.clientWidth);
  }
}

async function settleResponsivePage(page: Page, heading: string, control?: string) {
  await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible({ timeout: 15_000 });
  if (control) {
    await expect(page.getByRole("button", { name: control }).first()).toBeVisible({ timeout: 15_000 });
  }
  await page.waitForLoadState("networkidle", { timeout: 1_000 }).catch(() => undefined);
  await page.waitForTimeout(100);
}

async function assertChartFramesReady(page: Page) {
  await expect(page.locator(".op-chart-frame").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".op-chart-frame canvas").first()).toBeVisible({ timeout: 15_000 });
  const frames = await page.locator(".op-chart-frame").evaluateAll((elements) =>
    elements
      .filter((element) => (element as HTMLElement).offsetParent !== null)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return { width: rect.width, height: rect.height, canvasCount: element.querySelectorAll("canvas").length };
      }),
  );
  expect(frames.length).toBeGreaterThan(0);
  for (const frame of frames) {
    expect(frame.width).toBeGreaterThan(2);
    expect(frame.height).toBeGreaterThan(20);
  }
  expect(frames.some((frame) => frame.canvasCount > 0)).toBeTruthy();
}

function collectConsoleProblems(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  return problems;
}

test.beforeEach(async ({ page }) => {
  await installResponsiveMocks(page);
});

test("route-wide mobile console pages do not create document-level horizontal overflow", async ({ page }) => {
  test.setTimeout(180_000);
  await page.setViewportSize(routeWideMobileViewport);
  for (const route of routeWideRoutes) {
    await test.step(route.path, async () => {
      await page.goto(route.path);
      await settleResponsivePage(page, route.heading, route.control);
      await assertNoPageOverflow(page);
      await assertContainedDenseSurfaces(page);
    });
  }
});

for (const viewport of viewportMatrix) {
  test.describe(`${viewport.name} targeted responsive matrix`, () => {
    for (const route of viewportMatrixRoutes) {
      test(`${route.path} keeps shell and priority surfaces contained`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(route.path);
        await settleResponsivePage(page, route.heading, route.control);
        await assertNoPageOverflow(page);
        await assertContainedDenseSurfaces(page);
      });
    }
  });
}

test("mobile drawer exposes accessible state, keyboard access, and closes after navigation", async ({ page }) => {
  await page.setViewportSize(routeWideMobileViewport);
  await page.goto("/analyze");
  await expect(page.getByRole("heading", { name: "Symbol Snapshot" })).toBeVisible();
  const toggle = page.getByTestId("mobile-nav-toggle");
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-controls", "console-navigation");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("#console-navigation")).toBeVisible();
  await expect(page.locator(".op-drawer-close")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const snapshotLink = page.getByRole("link", { name: "Symbol Snapshot" });
  await expect(snapshotLink).toHaveAttribute("aria-current", "page");
  await page.getByRole("link", { name: "Scheduled Reports" }).click();
  await expect(page).toHaveURL(/\/schedules$/);
  await expect(page.getByRole("heading", { name: "Scheduled Strategy Reports" })).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await assertNoPageOverflow(page);
});

test("mobile drawer hides admin links until admin role is confirmed", async ({ page }) => {
  await page.unroute("**/api/user/me");
  let releaseMe: (() => void) | null = null;
  const meReady = new Promise<void>((resolve) => {
    releaseMe = resolve;
  });
  await page.route("**/api/user/me", async (route) => {
    await meReady;
    await route.fulfill({ json: operatorMe("admin") });
  });

  await page.setViewportSize(routeWideMobileViewport);
  await page.goto("/analyze");
  await expect(page.getByRole("heading", { name: "Symbol Snapshot" })).toBeVisible();
  const toggle = page.getByTestId("mobile-nav-toggle");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("link", { name: "Admin / Users" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Provider Health" })).toHaveCount(0);

  releaseMe?.();
  await expect(page.getByRole("link", { name: "Admin / Users" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Provider Health" })).toBeVisible();
});

for (const chartRoute of [
  { path: "/charts/haco", heading: "HACO operator workspace", control: "Run HACO analysis" },
  { path: "/charts/momentum", heading: "Momentum Intelligence workspace", control: "Run Momentum analysis" },
] as const) {
  test(`${chartRoute.path} resizes chart panes without mobile overflow or console errors`, async ({ page }) => {
    const consoleProblems = collectConsoleProblems(page);
    await page.setViewportSize(routeWideMobileViewport);
    await page.goto(chartRoute.path);
    await settleResponsivePage(page, chartRoute.heading, chartRoute.control);
    await assertChartFramesReady(page);
    await assertNoPageOverflow(page);

    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForTimeout(250);
    await assertChartFramesReady(page);
    await assertNoPageOverflow(page);

    await page.setViewportSize({ width: 320, height: 700 });
    await page.waitForTimeout(250);
    await assertChartFramesReady(page);
    await assertNoPageOverflow(page);
    expect(consoleProblems).toEqual([]);
  });
}

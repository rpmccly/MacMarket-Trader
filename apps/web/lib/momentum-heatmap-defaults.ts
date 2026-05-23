export const MOMENTUM_HEATMAP_STORAGE_KEY = "macmarket-momentum-heatmap-symbols-v1";

export type MomentumHeatmapRowConfig = {
  id: string;
  categoryId: string;
  categoryLabel: string;
  symbol: string;
  displayName: string;
  providerSymbol: string;
};

export type MomentumHeatmapCategoryConfig = {
  categoryId: string;
  categoryLabel: string;
  rows: MomentumHeatmapRowConfig[];
};

type SymbolEntry = string | { symbol: string; displayName: string; providerSymbol?: string };

function rowId(categoryId: string, displayName: string): string {
  return `${categoryId}:${displayName.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toUpperCase()}`;
}

function makeRows(categoryId: string, categoryLabel: string, entries: SymbolEntry[]): MomentumHeatmapRowConfig[] {
  return entries.map((entry) => {
    const normalized = typeof entry === "string"
      ? { symbol: entry, displayName: entry, providerSymbol: entry }
      : { providerSymbol: entry.symbol, ...entry };
    return {
      id: rowId(categoryId, normalized.displayName),
      categoryId,
      categoryLabel,
      symbol: normalized.symbol,
      displayName: normalized.displayName,
      providerSymbol: normalized.providerSymbol ?? normalized.symbol,
    };
  });
}

export const DEFAULT_MOMENTUM_HEATMAP_CATEGORIES: MomentumHeatmapCategoryConfig[] = [
  {
    categoryId: "indexes",
    categoryLabel: "INDEXES",
    rows: makeRows("indexes", "INDEXES", [
      "SPY",
      "QQQ",
      "DIA",
      "IWM",
      "RSP",
      "QQQE",
      "MAG7",
      "MTUM",
      { symbol: "VTI", displayName: "ALL U.S. - VTI", providerSymbol: "VTI" },
      { symbol: "VT", displayName: "ALL WORLD - VT", providerSymbol: "VT" },
      { symbol: "/NKD", displayName: "Japan - /NKD", providerSymbol: "/NKD" },
      { symbol: "DAX:DBI", displayName: "Eur - DAX:DBI", providerSymbol: "DAX:DBI" },
      { symbol: "FXI", displayName: "China - FXI", providerSymbol: "FXI" },
      "EEM",
    ]),
  },
  {
    categoryId: "sectors",
    categoryLabel: "SECTORS",
    rows: makeRows("sectors", "SECTORS", [
      "XLB",
      "XLC",
      "XLE",
      "OIH",
      "XLF",
      "KRE",
      "XLI",
      "XLK",
      "XLP",
      "XLU",
      "XLV",
      "XLY",
      "XLRE",
      "XBI",
      "XME",
      "XRT",
      "GDX",
      "SMH",
      "IGV",
      "$DJT",
      "ITB",
      "ARKK",
      "ITA",
      "JETS",
      "UFO",
      "BOTZ",
      "URA",
      "ICLN",
      "TAN",
      "KWEB",
    ]),
  },
  {
    categoryId: "major-stocks",
    categoryLabel: "MAJOR STOCKS",
    rows: makeRows("major-stocks", "MAJOR STOCKS", [
      "AAPL",
      "ALAB",
      "AMAT",
      "AMZN",
      "AMD",
      "APP",
      "AVGO",
      "BABA",
      "BRK/B",
      "CAT",
      "CEG",
      "COIN",
      "CRDO",
      "CRWD",
      "CVNA",
      "GE",
      "GEV",
      "GOOGL",
      "GS",
      "IONQ",
      "IREN",
      "HD",
      "HOOD",
      "INTC",
      "JPM",
      "LITE",
      "LLY",
      "META",
      "MSFT",
      "MSTR",
      "MU",
      "NBIS",
      "NFLX",
      "NVDA",
      "OKLO",
      "ORCL",
      "PLTR",
      "RKLB",
      "SLB",
      "TSLA",
      "TSM",
      "UNH",
      "V",
      "VRT",
      "WMT",
      "XOM",
    ]),
  },
  {
    categoryId: "bonds-misc",
    categoryLabel: "BONDS + MISC",
    rows: makeRows("bonds-misc", "BONDS + MISC", [
      "/ZT",
      "/ZN",
      "/ZB",
      "TLT",
      "LQD",
      "HYG",
      "$DXY",
      "AUD/JPY",
      "/VX",
      "VIX",
      "VXX",
      "VVIX",
      "$SPXA50R",
      "$PCALL",
      "SKEW",
      "T10Y2Y:FRED",
    ]),
  },
  {
    categoryId: "commodities",
    categoryLabel: "COMMODITIES",
    rows: makeRows("commodities", "COMMODITIES", [
      "$DJCI",
      "/CL",
      "USO",
      "/RB",
      "/NG",
      "/HG",
      "/GC",
      "GLD",
      "/SI",
      "SLV",
      "/BTC",
      "/ETH",
      "/ZC",
      "/ZS",
      "/ZW",
    ]),
  },
];

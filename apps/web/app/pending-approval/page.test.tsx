import React from "react";
import type { ReactNode } from "react";
import { createRequire } from "node:module";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/brand-header", async () => {
  const ReactModule = await import("react");
  return {
    BrandHeader: ({ tagline }: { tagline?: string }) => ReactModule.createElement("header", null, tagline),
  };
});

import Page from "./page";

const require = createRequire(import.meta.url);
const { renderToStaticMarkup } = require("react-dom/server") as {
  renderToStaticMarkup: (element: ReactNode) => string;
};

describe("pending approval page", () => {
  it("renders normal pending approval copy", async () => {
    const html = renderToStaticMarkup(await Page({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Pending approval");
    expect(html).toContain("operator desk access is pending admin review");
  });

  it("renders identity sync failure copy separately from pending approval", async () => {
    const html = renderToStaticMarkup(await Page({ searchParams: Promise.resolve({ reason: "identity-sync" }) }));

    expect(html).toContain("Identity sync needs attention");
    expect(html).toContain("could not hydrate a stable email/profile");
    expect(html).not.toContain("operator desk access is pending admin review");
  });

  it("renders profile-check outage copy without raw backend errors", async () => {
    const html = renderToStaticMarkup(await Page({ searchParams: Promise.resolve({ reason: "profile-error" }) }));

    expect(html).toContain("Approval check unavailable");
    expect(html).toContain("Provider Health");
    expect(html).not.toContain("identity_sync_failed");
  });
});

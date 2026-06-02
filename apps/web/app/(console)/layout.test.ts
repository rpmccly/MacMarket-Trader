import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./layout.tsx", import.meta.url), "utf8");

describe("console layout approval gate", () => {
  it("distinguishes identity sync failures from true pending approval", () => {
    expect(source).toContain("identity_sync_failed");
    expect(source).toContain('/pending-approval?reason=identity-sync');
    expect(source).toContain('/pending-approval?reason=profile-error');
    expect(source).toContain('redirect("/sign-in")');
    expect(source).not.toContain("profile === null");
  });
});

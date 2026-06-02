import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");

describe("sign-up page", () => {
  it("uses Clerk sign-up for invite-first operator access", () => {
    expect(source).toContain('import { SignUp } from "@clerk/nextjs"');
    expect(source).toContain("<SignUp />");
    expect(source).toContain("Request access");
    expect(source).toContain("invite-first operator access");
    expect(source).not.toContain("mock");
    expect(source).not.toContain("Bearer");
  });
});

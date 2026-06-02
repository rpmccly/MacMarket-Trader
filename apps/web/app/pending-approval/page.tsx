import Link from "next/link";
import React from "react";

import { BrandHeader } from "@/components/brand-header";

type SearchParams = Record<string, string | string[] | undefined>;

function firstParam(value: string | string[] | undefined): string {
  return Array.isArray(value) ? String(value[0] ?? "") : String(value ?? "");
}

function pendingCopy(reason: string): { title: string; body: string; hint: string } {
  if (reason === "identity-sync") {
    return {
      title: "Identity sync needs attention",
      body: "Your Clerk session is valid, but MacMarket could not hydrate a stable email/profile from the backend Clerk API.",
      hint: "Ask an admin to verify backend Clerk profile hydration settings, then retry sign-in.",
    };
  }
  if (reason === "profile-error") {
    return {
      title: "Approval check unavailable",
      body: "MacMarket could not complete the local approval check for this session.",
      hint: "Retry sign-in after the backend is healthy. If this persists, ask an admin to check Provider Health.",
    };
  }
  return {
    title: "Pending approval",
    body: "Your identity is verified, but operator desk access is pending admin review.",
    hint: "You will receive an approval email when your status changes.",
  };
}

export default async function Page({ searchParams }: { searchParams?: Promise<SearchParams> }) {
  const params = searchParams ? await searchParams : {};
  const copy = pendingCopy(firstParam(params.reason));
  return (
    <>
      <BrandHeader tagline="Private Alpha" />
      <section style={{ maxWidth: 720, margin: "80px auto", padding: 24, border: "1px solid #2b3642", background: "#111922" }}>
        <h1 style={{ marginTop: 0 }}>{copy.title}</h1>
        <p>{copy.body}</p>
        <p style={{ color: "#9fb0c3" }}>{copy.hint}</p>
        <Link href="/sign-in" style={{ color: "#4b8cff" }}>Return to sign in</Link>
      </section>
    </>
  );
}

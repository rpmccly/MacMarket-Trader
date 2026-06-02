export const dynamic = "force-dynamic";

import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { ConsoleShell } from "@/components/console-shell";
import { backendUrl } from "@/lib/backend";
import { isE2EAuthBypassEnabled } from "@/lib/e2e-auth";
import type { UserProfile } from "@/lib/user-profile";

type ProfileLoadResult =
  | { kind: "ok"; profile: UserProfile }
  | { kind: "auth" }
  | { kind: "identity-sync" }
  | { kind: "profile-error" };

function detailCode(payload: unknown): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) return "";
  const detail = (payload as Record<string, unknown>).detail;
  if (typeof detail === "string") return detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return "";
  const code = (detail as Record<string, unknown>).code;
  return typeof code === "string" ? code : "";
}

async function readErrorPayload(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function loadProfile(token: string): Promise<ProfileLoadResult> {
  try {
    const response = await fetch(backendUrl("/user/me"), {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (response.ok) {
      return { kind: "ok", profile: (await response.json()) as UserProfile };
    }
    const payload = await readErrorPayload(response);
    if (response.status === 424 || detailCode(payload) === "identity_sync_failed") {
      return { kind: "identity-sync" };
    }
    if (response.status === 401) return { kind: "auth" };
    return { kind: "profile-error" };
  } catch {
    return { kind: "profile-error" };
  }
}

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  if (isE2EAuthBypassEnabled()) {
    return <ConsoleShell>{children}</ConsoleShell>;
  }

  const { userId, getToken } = await auth();
  if (!userId) {
    redirect("/sign-in");
  }

  const token = await getToken();
  if (!token) {
    redirect("/sign-in");
  }

  const profileResult = await loadProfile(token);
  if (profileResult.kind === "auth") {
    redirect("/sign-in");
  }
  if (profileResult.kind === "identity-sync") {
    redirect("/pending-approval?reason=identity-sync");
  }
  if (profileResult.kind === "profile-error") {
    redirect("/pending-approval?reason=profile-error");
  }

  const profile = profileResult.profile;
  if (profile.approval_status === "pending") {
    redirect("/pending-approval");
  }
  if (profile.approval_status === "rejected" || profile.approval_status === "suspended") {
    redirect("/access-denied");
  }

  return <ConsoleShell>{children}</ConsoleShell>;
}

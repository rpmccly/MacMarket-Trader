import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { AdminUsersPanel } from "@/components/admin/admin-users-panel";
import { backendUrl } from "@/lib/backend";
import { isE2EAuthBypassEnabled } from "@/lib/e2e-auth";
import type { UserProfile } from "@/lib/user-profile";

export default async function Page() {
  if (isE2EAuthBypassEnabled()) {
    return <AdminUsersPanel />;
  }

  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in");
  const token = await getToken();
  if (!token) redirect("/sign-in");

  const response = await fetch(backendUrl("/user/me"), {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) redirect("/access-denied");
  const profile = (await response.json()) as UserProfile;
  if (profile.app_role !== "admin") redirect("/access-denied");

  return <AdminUsersPanel />;
}

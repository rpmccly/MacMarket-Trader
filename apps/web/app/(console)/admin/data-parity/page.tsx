import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { DataParityLab } from "@/components/admin/data-parity-lab";
import { isE2EAuthBypassEnabled } from "@/lib/e2e-auth";
import { backendUrl } from "@/lib/backend";
import type { UserProfile } from "@/lib/user-profile";

export default async function Page() {
  const e2eBypass = isE2EAuthBypassEnabled();
  if (!e2eBypass) {
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
  }

  return <DataParityLab />;
}

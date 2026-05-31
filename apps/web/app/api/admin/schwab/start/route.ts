import { NextResponse } from "next/server";

import { resolveAuthTokenState } from "@/app/api/_utils/auth-token";
import { backendUrl } from "@/lib/backend";

async function parseUpstream(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export async function GET(request: Request) {
  const resolved = await resolveAuthTokenState(request);
  if (!resolved.token && resolved.authPending) {
    return NextResponse.json({ detail: "Authentication initializing" }, { status: 425 });
  }
  if (!resolved.token) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  const upstream = await fetch(backendUrl("/auth/schwab/start?return_path=/admin/data-parity"), {
    method: "GET",
    headers: { Authorization: `Bearer ${resolved.token}` },
    redirect: "manual",
    cache: "no-store",
  });
  const location = upstream.headers.get("location");
  if (location) {
    return NextResponse.redirect(location, { status: 302 });
  }
  const payload = await parseUpstream(upstream);
  return NextResponse.json(payload ?? { detail: "Schwab OAuth start failed." }, { status: upstream.status || 502 });
}

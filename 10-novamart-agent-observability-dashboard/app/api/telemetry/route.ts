import { NextResponse } from "next/server";

import { readCallerIdentity } from "@/lib/aws/identity";
import { readLatestLogActivity } from "@/lib/aws/logs";

export const dynamic = "force-dynamic";

export async function GET() {
  const [identity, activity] = await Promise.all([
    readCallerIdentity(),
    readLatestLogActivity(),
  ]);

  return NextResponse.json(
    {
      identity: identity.ok
        ? { ok: true, data: identity.data, readAt: identity.readAt }
        : identity,
      logActivity: activity.ok
        ? { ok: true, data: activity.data, readAt: activity.readAt }
        : activity,
    },
    { headers: { "cache-control": "no-store" } },
  );
}

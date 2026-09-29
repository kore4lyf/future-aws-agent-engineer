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
      readAt: new Date().toISOString(),
      identity: identity.ok ? identity.data : identity.error,
      logActivity: activity.ok ? activity.data : activity.error,
    },
    { headers: { "cache-control": "no-store" } },
  );
}

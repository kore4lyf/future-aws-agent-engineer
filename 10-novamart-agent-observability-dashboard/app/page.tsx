import { readCallerIdentity } from "@/lib/aws/identity";
import { readLatestLogActivity } from "@/lib/aws/logs";

export const dynamic = "force-dynamic";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b py-2 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

export default async function Home() {
  const [identity, activity] = await Promise.all([
    readCallerIdentity(),
    readLatestLogActivity(),
  ]);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">NovaMart Agent Operations Console</h1>
        <p className="text-muted-foreground text-sm">
          Foundation check: these values are read from AWS on every request.
        </p>
      </header>

      <section>
        <h2 className="mb-2 text-sm font-medium">Caller identity</h2>
        {identity.ok ? (
          <>
            <Row label="Account" value={identity.data.accountLabel} />
            <Row label="Region" value={identity.data.region} />
          </>
        ) : (
          <p className="text-sm">
            Identity unavailable. {identity.error.message}{" "}
            <span className="text-muted-foreground">({identity.error.code})</span>
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium">Log group activity</h2>
        {activity.ok ? (
          <>
            <Row label="Log group" value={activity.data.logGroup} />
            <Row
              label="Latest stream"
              value={activity.data.latestStreamName ?? "none found"}
            />
            <Row
              label="Last log event"
              value={
                activity.data.lastEventTime
                  ? new Date(activity.data.lastEventTime).toISOString()
                  : "no log events found"
              }
            />
          </>
        ) : (
          <p className="text-sm">
            Log group unavailable. {activity.error.message}{" "}
            <span className="text-muted-foreground">({activity.error.code})</span>
          </p>
        )}
      </section>
    </main>
  );
}

import { readCallerIdentity } from "@/lib/aws/identity";
import { readLatestLogActivity } from "@/lib/aws/logs";
import type { ReadFailure, ReadResult } from "@/lib/aws/result";

export const dynamic = "force-dynamic";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b py-2 last:border-b-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-xs">{value}</span>
    </div>
  );
}

function ReadError({ error }: { error: ReadFailure }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-sm">
        {error.message}{" "}
        <span className="text-muted-foreground">({error.code})</span>
      </p>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground">
          Technical detail
        </summary>
        <dl className="mt-1 flex flex-col gap-0.5 font-mono">
          <div className="flex gap-2">
            <dt className="text-muted-foreground">code</dt>
            <dd>{error.code}</dd>
          </div>
          {error.requestId ? (
            <div className="flex gap-2">
              <dt className="text-muted-foreground">request id</dt>
              <dd>{error.requestId}</dd>
            </div>
          ) : null}
          <div className="flex gap-2">
            <dt className="text-muted-foreground">read at</dt>
            <dd>{new Date(error.readAt).toISOString()}</dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

function Panel<T>({
  title,
  result,
  children,
}: {
  title: string;
  result: ReadResult<T>;
  children: (data: T) => React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium">{title}</h2>
      {result.ok ? (
        <div>
          {children(result.data)}
          <p className="text-muted-foreground pt-2 text-xs">
            Read at {new Date(result.readAt).toISOString()}
          </p>
        </div>
      ) : (
        <ReadError error={result.error} />
      )}
    </section>
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
        <h1 className="text-2xl font-semibold">
          NovaMart Agent Operations Console
        </h1>
        <p className="text-muted-foreground text-sm">
          Foundation check: these values are read from AWS on every request.
        </p>
      </header>

      <Panel title="Caller identity" result={identity}>
        {(data) => (
          <>
            <Row label="Account" value={data.accountLabel} />
            <Row label="Region" value={data.region} />
          </>
        )}
      </Panel>

      <Panel title="Log group activity" result={activity}>
        {(data) => (
          <>
            <Row label="Log group" value={data.logGroup} />
            <Row
              label="Latest stream"
              value={data.latestStreamName ?? "no log streams"}
            />
            <Row
              label="Last log event"
              value={
                data.lastEventTime
                  ? new Date(data.lastEventTime).toISOString()
                  : "no log events found"
              }
            />
          </>
        )}
      </Panel>
    </main>
  );
}

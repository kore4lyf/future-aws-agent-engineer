import "server-only";

import { DescribeLogStreamsCommand } from "@aws-sdk/client-cloudwatch-logs";

import { defaultDeps, type AwsDeps } from "@/lib/aws/clients";
import { readConsoleConfig, READ_TIMEOUT_MS } from "@/lib/config";
import { readFailure, readSuccess, toReadFailure, type ReadResult } from "@/lib/aws/result";

export interface LogGroupActivity {
  logGroup: string;
  latestStreamName: string | null;
  lastEventTime: number | null;
}

export async function readLatestLogActivity(
  makeDeps: () => AwsDeps = defaultDeps,
  timeoutMs: number = READ_TIMEOUT_MS,
): Promise<ReadResult<LogGroupActivity>> {
  const readAt = Date.now();

  try {
    const { logGroup } = readConsoleConfig();
    const response = await makeDeps().logs.send(
      new DescribeLogStreamsCommand({
        logGroupName: logGroup,
        orderBy: "LastEventTime",
        descending: true,
        limit: 1,
      }),
      { abortSignal: AbortSignal.timeout(timeoutMs) },
    );

    const stream = response.logStreams?.[0];

    return readSuccess(
      {
        logGroup,
        latestStreamName: stream?.logStreamName ?? null,
        lastEventTime: stream?.lastEventTimestamp ?? null,
      },
      readAt,
    );
  } catch (error) {
    return readFailure(toReadFailure(error, "The log group read", readAt, timeoutMs));
  }
}

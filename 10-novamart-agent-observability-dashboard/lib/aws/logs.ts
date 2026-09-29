import "server-only";

import { DescribeLogStreamsCommand } from "@aws-sdk/client-cloudwatch-logs";

import { getAwsDeps, type AwsDeps } from "@/lib/aws/clients";
import { readConsoleConfig, READ_TIMEOUT_MS } from "@/lib/config";
import {
  isAbortError,
  readFailure,
  readSuccess,
  type ReadResult,
} from "@/lib/aws/result";

export interface LogGroupActivity {
  logGroup: string;
  latestStreamName: string | null;
  lastEventTime: number | null;
}

export async function readLatestLogActivity(
  deps: AwsDeps = getAwsDeps(),
  timeoutMs: number = READ_TIMEOUT_MS,
): Promise<ReadResult<LogGroupActivity>> {
  const { logGroup } = readConsoleConfig();
  const readAt = Date.now();

  try {
    const response = await deps.logs.send(
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
    if (isAbortError(error)) {
      return readFailure(
        {
          code: "ReadTimeout",
          message: `The read of ${logGroup} did not finish in ${timeoutMs}ms.`,
          name: error.name,
        },
        readAt,
      );
    }

    const awsError = error as { name?: string; message?: string; $metadata?: { requestId?: string } };

    return readFailure(
      {
        code: awsError.name ?? "ReadFailed",
        message: awsError.message ?? "The AWS read failed for an unknown reason.",
        requestId: awsError.$metadata?.requestId,
        name: awsError.name ?? "Error",
      },
      readAt,
    );
  }
}

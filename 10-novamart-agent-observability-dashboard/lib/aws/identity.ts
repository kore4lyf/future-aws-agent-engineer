import "server-only";

import { GetCallerIdentityCommand } from "@aws-sdk/client-sts";

import { getAwsDeps, type AwsDeps } from "@/lib/aws/clients";
import { readConsoleConfig, READ_TIMEOUT_MS } from "@/lib/config";
import { isAbortError, readFailure, readSuccess, type ReadResult } from "@/lib/aws/result";

export interface CallerIdentity {
  account: string;
  accountLabel: string;
  region: string;
}

export function maskAccount(account: string): string {
  if (account.length < 4) return "****";
  return `****${account.slice(-4)}`;
}

export async function readCallerIdentity(
  deps: AwsDeps = getAwsDeps(),
  timeoutMs: number = READ_TIMEOUT_MS,
): Promise<ReadResult<CallerIdentity>> {
  const { region } = readConsoleConfig();
  const readAt = Date.now();

  try {
    const response = await deps.sts.send(new GetCallerIdentityCommand({}), {
      abortSignal: AbortSignal.timeout(timeoutMs),
    });
    const account = response.Account ?? "";

    return readSuccess(
      { account, accountLabel: maskAccount(account), region },
      readAt,
    );
  } catch (error) {
    if (isAbortError(error)) {
      return readFailure(
        {
          code: "ReadTimeout",
          message: `The caller identity read did not finish in ${timeoutMs}ms.`,
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

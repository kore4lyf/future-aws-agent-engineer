import "server-only";

import { GetCallerIdentityCommand } from "@aws-sdk/client-sts";

import { defaultDeps, type AwsDeps } from "@/lib/aws/clients";
import { readConsoleConfig, READ_TIMEOUT_MS } from "@/lib/config";
import { readFailure, readSuccess, toReadFailure, type ReadResult } from "@/lib/aws/result";

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
  makeDeps: () => AwsDeps = defaultDeps,
  timeoutMs: number = READ_TIMEOUT_MS,
): Promise<ReadResult<CallerIdentity>> {
  const readAt = Date.now();

  try {
    const region = readConsoleConfig().region;
    const identity = await makeDeps().sts.send(new GetCallerIdentityCommand({}), {
      abortSignal: AbortSignal.timeout(timeoutMs),
    });
    const account = identity.Account ?? "";

    return readSuccess(
      { account, accountLabel: maskAccount(account), region },
      readAt,
    );
  } catch (error) {
    return readFailure(toReadFailure(error, "The caller identity read", readAt, timeoutMs));
  }
}

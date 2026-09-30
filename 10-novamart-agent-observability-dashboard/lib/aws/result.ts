import "server-only";

import { redactAccountId } from "@/lib/aws/redact";

export interface ReadFailure {
  code: string;
  message: string;
  requestId?: string;
  name: string;
  readAt: number;
}

export type ReadResult<T> =
  | { ok: true; data: T; readAt: number }
  | { ok: false; error: ReadFailure; readAt: number };

export function readSuccess<T>(data: T, readAt: number): ReadResult<T> {
  return { ok: true, data, readAt };
}

export function readFailure<T>(error: ReadFailure): ReadResult<T> {
  return { ok: false, error, readAt: error.readAt };
}

export function isAbortError(error: unknown): error is Error {
  return (
    error instanceof Error &&
    (error.name === "AbortError" || error.name === "TimeoutError")
  );
}

export function toReadFailure(
  error: unknown,
  context: string,
  readAt: number,
  timeoutMs: number,
): ReadFailure {
  if (isAbortError(error)) {
    return {
      code: "ReadTimeout",
      message: `${context} did not finish in ${timeoutMs}ms.`,
      name: error.name,
      readAt,
    };
  }

  const awsError = error as {
    name?: string;
    message?: string;
    code?: string;
    $metadata?: { requestId?: string };
  };

  return {
    code: awsError.code ?? awsError.name ?? "ReadFailed",
    message: redactAccountId(
      awsError.message ?? "The AWS read failed for an unknown reason.",
    ),
    requestId: awsError.$metadata?.requestId,
    name: awsError.name ?? "Error",
    readAt,
  };
}

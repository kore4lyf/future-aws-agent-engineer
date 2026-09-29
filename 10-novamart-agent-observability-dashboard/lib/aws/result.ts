import "server-only";

export interface ReadFailure {
  code: string;
  message: string;
  requestId?: string;
  name: string;
}

export type ReadResult<T> =
  | { ok: true; data: T; readAt: number }
  | { ok: false; error: ReadFailure; readAt: number };

export function readSuccess<T>(data: T, readAt: number): ReadResult<T> {
  return { ok: true, data, readAt };
}

export function readFailure<T>(error: ReadFailure, readAt: number): ReadResult<T> {
  return { ok: false, error, readAt };
}

export function isAbortError(error: unknown): error is Error {
  return (
    error instanceof Error &&
    (error.name === "AbortError" || error.name === "TimeoutError")
  );
}

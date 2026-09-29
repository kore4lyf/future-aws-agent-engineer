import "server-only";

export const DEFAULT_LOG_GROUP = "/aws/bedrock/agentcore/novamart-agentcore";
export const DEFAULT_XRAY_SERVICE = "NovaMart-Orchestrator";
export const READ_TIMEOUT_MS = 8000;

export interface ConsoleConfig {
  region: string;
  logGroup: string;
  xrayService: string;
  readTimeoutMs: number;
}

export class MissingConfigError extends Error {
  readonly code = "MissingConfiguration";

  constructor(readonly variable: string) {
    super(`Set ${variable} in .env.local before starting the console.`);
    this.name = "MissingConfigError";
  }
}

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new MissingConfigError(name);
  return value;
}

function optional(name: string, fallback: string): string {
  const value = process.env[name]?.trim();
  return value ? value : fallback;
}

export function readConsoleConfig(): ConsoleConfig {
  return {
    region: required("AWS_REGION"),
    logGroup: optional("LOG_GROUP", DEFAULT_LOG_GROUP),
    xrayService: optional("XRAY_SERVICE", DEFAULT_XRAY_SERVICE),
    readTimeoutMs: READ_TIMEOUT_MS,
  };
}

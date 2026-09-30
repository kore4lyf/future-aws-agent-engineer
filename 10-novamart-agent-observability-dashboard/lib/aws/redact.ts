import "server-only";

const ACCOUNT_ID = /\b\d{12}\b/g;

export function redactAccountId(message: string): string {
  return message.replace(ACCOUNT_ID, "[redacted account]");
}

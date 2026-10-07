import 'dotenv/config';

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(
      `Missing required environment variable ${name}. Copy .env.example to .env and fill it in.`
    );
  }
  return value;
}

function optional(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value ? value : undefined;
}

function bool(name: string, fallback = false): boolean {
  const value = process.env[name]?.trim()?.toLowerCase();
  if (!value) return fallback;
  return value === 'true' || value === '1' || value === 'yes';
}

function int(name: string, fallback: number): number {
  const value = Number(process.env[name]?.trim());
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

const nodeEnv = optional('NODE_ENV') ?? 'development';

export const config = {
  nodeEnv,
  port: int('PORT', 3001),
  isProduction: nodeEnv === 'production',

  awsRegion: optional('AWS_REGION') ?? 'us-east-1',
  /**
   * ARN of the deployed AgentCore Runtime. InvokeAgentRuntime accepts either the
   * full ARN or an agent id plus account id.
   */
  agentRuntimeArn: optional('AGENT_RUNTIME_ARN'),
  /** Defaults to DEFAULT; set to hit a specific endpoint version, e.g. v2. */
  agentQualifier: optional('AGENT_RUNTIME_QUALIFIER') ?? 'DEFAULT',

  /** Cognito user pool used to verify incoming bearer tokens. */
  userPoolId: optional('COGNITO_USER_POOL_ID'),
  userPoolRegion: optional('COGNITO_USER_POOL_REGION') ?? optional('AWS_REGION') ?? 'us-east-1',
  /** When set, only ID tokens with this client id are accepted. */
  userPoolClientId: optional('COGNITO_USER_POOL_CLIENT_ID'),

  /** Optional DynamoDB table holding conversation history. */
  historyTableName: optional('HISTORY_TABLE_NAME'),

  /** Origins allowed to call this API. */
  corsOrigins: (optional('CORS_ORIGINS') ?? 'http://localhost:5173')
    .split(',')
    .map((o) => o.trim())
    .filter(Boolean),

  /** Skips JWT verification and answers with canned replies. */
  mockMode: bool('MOCK_MODE', false),
  requestTimeoutMs: int('AGENT_TIMEOUT_MS', 120_000),
  maxMessageLength: int('MAX_MESSAGE_LENGTH', 8000),
};

/** Fails fast at boot when a required production value is missing. */
export function assertConfiguration(): void {
  if (config.mockMode) return;

  if (!config.agentRuntimeArn) {
    throw new Error(
      'AGENT_RUNTIME_ARN is required. Set it to your AgentCore Runtime ARN, or enable MOCK_MODE=true for local development.'
    );
  }
  if (!config.userPoolId) {
    throw new Error(
      'COGNITO_USER_POOL_ID is required to verify bearer tokens. Set it, or enable MOCK_MODE=true for local development.'
    );
  }
}

export { required };
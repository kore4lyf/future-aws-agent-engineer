import { InvokeAgentRuntimeCommand, BedrockAgentCoreClient } from '@aws-sdk/client-bedrock-agentcore';
import { config } from './config.js';
import { mockReplyFor } from './mockAgent.js';

export interface AgentReply {
  text: string;
}

let client: BedrockAgentCoreClient | null = null;

function getClient(): BedrockAgentCoreClient {
  if (!client) {
    client = new BedrockAgentCoreClient({ region: config.awsRegion });
  }
  return client;
}

export class AgentError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'AgentError';
    this.status = status;
    this.code = code;
  }
}

/**
 * Calls the agent runtime and returns its reply text.
 *
 * `runtimeSessionId` is what gives the agent its conversation memory, so it is
 * always passed through from the client's session id.
 */
export async function invokeAgent(input: {
  message: string;
  runtimeSessionId: string;
  userId: string;
  customerId: string;
}): Promise<AgentReply> {
  // Mock mode answers locally so the chat flow can be exercised without AWS.
  if (config.mockMode) {
    return { text: mockReplyFor(input.message) };
  }

  if (!config.agentRuntimeArn) {
    throw new AgentError(503, 'AGENT_NOT_CONFIGURED', 'The support agent is not configured.');
  }

  const command = new InvokeAgentRuntimeCommand({
    agentRuntimeArn: config.agentRuntimeArn,
    qualifier: config.agentQualifier,
    runtimeSessionId: input.runtimeSessionId,
    runtimeUserId: input.userId,
    payload: new TextEncoder().encode(JSON.stringify({
      prompt: input.message,
      customer_id: input.customerId,
    })),
  });

  let response;
  try {
    response = await getClient().send(command, {
      abortSignal: AbortSignal.timeout(config.requestTimeoutMs),
    });
  } catch (error) {
    throw toAgentError(error);
  }

  const text = await collectOutput(response as { response: AsyncIterable<Uint8Array> });
  return { text };
}

/**
 * Joins the streamed response chunks into one string.
 *
 * The runtime returns an event stream; `text/event-data` is the documented
 * format, but some agents emit newline-delimited JSON instead, so both are
 * accepted here.
 */
async function collectOutput(response: {
  response?: AsyncIterable<Uint8Array> | undefined;
}): Promise<string> {
  const stream = response.response;
  if (!stream) return '';

  const decoder = new TextDecoder();
  let raw = '';

  for await (const chunk of stream) {
    raw += decoder.decode(chunk, { stream: true });
  }
  raw += decoder.decode();

  return parseAgentOutput(raw);
}

export function parseAgentOutput(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return '';

  // Server-sent events: keep the data payloads.
  if (trimmed.startsWith('data:') || trimmed.includes('\ndata:')) {
    const data = trimmed
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())
      .filter((line) => line && line !== '[DONE]')
      .join('');
    const extracted = unwrapJson(data);
    return extracted ?? '';
  }

  // Newline-delimited JSON chunks.
  if (trimmed.startsWith('{')) {
    const lines = trimmed.split('\n').filter(Boolean);
    const parts: string[] = [];
    for (const line of lines) {
      const value = unwrapJson(line.trim());
      if (value) parts.push(value);
    }
    if (parts.length > 0) return parts.join('');
  }

  return unwrapJson(trimmed) ?? trimmed;
}

/** Pulls a human-readable field out of an agent's JSON reply. */
function unwrapJson(payload: string): string | null {
  if (!payload) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    return payload;
  }
  if (typeof parsed === 'string') return parsed;
  if (parsed && typeof parsed === 'object') {
    const record = parsed as Record<string, unknown>;
    for (const key of ['result', 'output', 'response', 'text', 'completion', 'message']) {
      const value = record[key];
      if (typeof value === 'string') return value;
      if (value && typeof value === 'object') {
        const nested = (value as Record<string, unknown>).text;
        if (typeof nested === 'string') return nested;
      }
    }
  }
  return JSON.stringify(parsed);
}

function toAgentError(error: unknown): AgentError {
  const name = (error as { name?: string })?.name ?? '';

  if (name === 'TimeoutError' || name === 'AbortError') {
    return new AgentError(504, 'AGENT_TIMEOUT', 'The agent took too long to respond. Please try again.');
  }
  if (name === 'AccessDeniedException' || name === 'UnrecognizedClientException') {
    return new AgentError(502, 'AGENT_ACCESS_DENIED', 'The support agent rejected the request.');
  }
  if (name === 'ResourceNotFoundException') {
    return new AgentError(502, 'AGENT_NOT_FOUND', 'The support agent is not deployed at the configured runtime ARN.');
  }
  if (name === 'ThrottlingException') {
    return new AgentError(429, 'AGENT_THROTTLED', 'Too many requests. Please wait a moment.');
  }

  // Include the original AWS error message in development to aid debugging.
  const raw = error instanceof Error ? error.message : String(error);
  const message = config.nodeEnv === 'development' && raw ? `Agent error: ${raw}` : 'The support agent is unavailable right now.';
  return new AgentError(502, 'AGENT_ERROR', message);
}
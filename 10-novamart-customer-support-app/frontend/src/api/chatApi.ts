import { config } from '@/config';
import type {
  ApiErrorBody,
  HealthResponse,
  ListSessionsResponse,
  SendMessageRequest,
  SendMessageResponse,
} from '@/types/api';
import { isTokenExpiring } from '@/lib/jwt';
import type { AuthService } from '@/auth/types';

export class ApiError extends Error {
  readonly code: string;
  readonly requiresAuth: boolean;
  readonly status: number;

  constructor(status: number, code: string, message: string, requiresAuth = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requiresAuth = requiresAuth;
  }
}

/** Supplies a currently-valid ID token, or null when signed out. */
export type TokenProvider = () => Promise<string | null>;

export interface ChatApiOptions {
  baseUrl?: string;
  tokenProvider?: TokenProvider;
  fetchImpl?: typeof fetch;
}

const DEMO_HISTORY_PREFIX = 'novamart.demo.history';

/**
 * In-memory + localStorage history used when the gateway has no DynamoDB
 * behind it, so the session list is still usable end to end.
 */
const demoStore = new Map<string, string[]>();

function readDemoSessions(sessionId: string): string[] {
  return demoStore.get(sessionId) ?? [];
}

function writeDemoSessions(sessionId: string, entries: string[]): void {
  demoStore.set(sessionId, entries);
  try {
    const all = Object.fromEntries(demoStore.entries());
    localStorage.setItem(DEMO_HISTORY_PREFIX, JSON.stringify(all));
  } catch {
    /* storage unavailable, keep in memory */
  }
}

export class ChatApi {
  private readonly baseUrl: string;
  private readonly tokenProvider: TokenProvider;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ChatApiOptions = {}) {
    this.baseUrl = (options.baseUrl ?? config.gatewayUrl ?? '').replace(/\/$/, '');
    this.fetchImpl = options.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.tokenProvider =
      options.tokenProvider ??
      (async () => {
        if (!config.cognito) return null;
        const { getSessionTokens } = await import('@/auth/cognitoAuthService');
        return getSessionTokens();
      });
  }

  private url(path: string): string {
    return `${this.baseUrl}${path}`;
  }

  /** Adds the Cognito bearer token, refreshing once when it has expired. */
  private async request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
    const token = await this.tokenProvider();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((init.headers as Record<string, string>) ?? {}),
    };
    if (token) headers.Authorization = `Bearer ${token}`;

    let response: Response;
    try {
      response = await this.fetchImpl(this.url(path), { ...init, headers });
    } catch {
      throw new ApiError(0, 'NETWORK_ERROR', 'Cannot reach the support service. Check your connection.');
    }

    if (response.status === 401 && retry) {
      const refreshed = await this.refreshOnce();
      if (refreshed) return this.request<T>(path, init, false);
    }

    if (!response.ok) {
      throw await this.toApiError(response);
    }

    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  private async refreshOnce(): Promise<boolean> {
    if (!config.cognito) return false;
    try {
      const { refreshSessionTokens } = await import('@/auth/cognitoAuthService');
      return Boolean(await refreshSessionTokens());
    } catch {
      return false;
    }
  }

  private async toApiError(response: Response): Promise<ApiError> {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      /* non-JSON error body, fall through to the generic message */
    }
    const message = body?.error?.message ?? `Request failed with status ${response.status}.`;
    return new ApiError(
      response.status,
      body?.error?.code ?? 'UNKNOWN',
      message,
      Boolean(body?.error?.requiresAuth) || response.status === 401,
    );
  }

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/api/health', { method: 'GET' });
  }

  async listSessions(): Promise<ListSessionsResponse> {
    return this.request<ListSessionsResponse>('/api/sessions', { method: 'GET' });
  }

  async sendMessage(body: SendMessageRequest): Promise<SendMessageResponse> {
    return this.request<SendMessageResponse>('/api/sessions/messages', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.request<void>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    });
  }
}

/** Client used in demo mode: answers locally, no network calls. */
export class DemoChatApi {
  async health(): Promise<HealthResponse> {
    return { status: 'ok', live: false, region: 'local' };
  }

  async listSessions(): Promise<ListSessionsResponse> {
    let raw: Record<string, string[]> = {};
    try {
      raw = (JSON.parse(localStorage.getItem(DEMO_HISTORY_PREFIX) ?? '{}') as Record<string, string[]>) ?? {};
    } catch {
      raw = {};
    }
    const sessions = Object.entries(raw).map(([sessionId, entries]) => ({
      sessionId,
      title: entries[0]?.slice(0, 60) ?? 'New conversation',
      updatedAt: new Date().toISOString(),
      messages: entries.map((content, i) => ({
        id: `${sessionId}-${i}`,
        role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
        content,
        createdAt: new Date().toISOString(),
      })),
    }));
    return { sessions };
  }

  async sendMessage({ sessionId, message }: SendMessageRequest): Promise<SendMessageResponse> {
    const entries = readDemoSessions(sessionId);
    const now = Date.now();
    const userMessage = {
      id: `${sessionId}-u-${now}`,
      role: 'user' as const,
      content: message,
      createdAt: new Date(now).toISOString(),
    };
    const reply = buildDemoReply(message);
    const assistantMessage = {
      id: `${sessionId}-a-${now}`,
      role: 'assistant' as const,
      content: reply,
      createdAt: new Date(now + 1).toISOString(),
    };
    writeDemoSessions(sessionId, [...entries, message, reply]);
    return { sessionId, userMessage, assistantMessage };
  }

  /** Exposed for the store so demo sessions can clear between test runs. */
  static clearDemoSessions(): void {
    demoStore.clear();
    try {
      localStorage.removeItem(DEMO_HISTORY_PREFIX);
    } catch {
      /* ignore */
    }
  }
}

function buildDemoReply(prompt: string): string {
  const q = prompt.toLowerCase();
  if (q.includes('order') || q.includes('track')) {
    return 'I can help track your order. Could you share the order number, for example NM-48213?';
  }
  if (q.includes('refund') || q.includes('return')) {
    return 'Returns are accepted within 30 days of delivery. Start a return from your Orders page and I will walk you through it.';
  }
  if (q.includes('password') || q.includes('account') || q.includes('login')) {
    return 'For account access, use the password reset link on the sign-in screen. Support cannot view or change passwords directly.';
  }
  return 'Thanks for reaching out. A NovaMart support specialist will review this shortly. Is there anything else I can help with?';
}

export function createChatApi(auth: AuthService): ChatApi | DemoChatApi {
  if (auth.kind === 'demo') return new DemoChatApi();
  return new ChatApi({ tokenProvider: async () => null });
}

export { isTokenExpiring };
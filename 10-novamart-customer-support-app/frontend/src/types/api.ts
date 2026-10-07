/**
 * Shared API contract between the React frontend and the gateway.
 *
 * Both packages duplicate this shape on purpose: the frontend must not import
 * server code, and the gateway must not pull in a React toolchain.
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
}

export interface ChatSession {
  sessionId: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface SendMessageRequest {
  sessionId: string;
  message: string;
}

export interface SendMessageResponse {
  sessionId: string;
  userMessage: ChatMessage;
  assistantMessage: ChatMessage;
}

export interface ListSessionsResponse {
  sessions: ChatSession[];
}

export interface HealthResponse {
  status: 'ok';
  /** True when the gateway has AWS credentials and can really call the agent. */
  live: boolean;
  region: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    /** True when the caller must sign in again. */
    requiresAuth?: boolean;
  };
}
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, ChatApi, DemoChatApi } from '@/api/chatApi';
import { config } from '@/config';
import type { ChatMessage, ChatSession, HealthResponse } from '@/types/api';

export interface ChatState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  loadingSessions: boolean;
  sending: boolean;
  error: string | null;
  health: HealthResponse | null;
  sendMessage(text: string): Promise<void>;
  selectSession(sessionId: string): void;
  newSession(): void;
  deleteSession(sessionId: string): Promise<void>;
  clearError(): void;
  reloadSessions(): Promise<void>;
}

const ACTIVE_SESSION_KEY = 'novamart.activeSession';

/** Session ids stay on the client; the agent gets one per conversation turn. */
function newSessionId(): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `sess-${Date.now().toString(36)}-${rand}`;
}

function deriveTitle(messages: ChatMessage[]): string {
  const firstUser = messages.find((m) => m.role === 'user');
  if (!firstUser) return 'New conversation';
  const singleLine = firstUser.content.replace(/\s+/g, ' ').trim();
  return singleLine.length > 60 ? `${singleLine.slice(0, 60)}…` : singleLine;
}

/**
 * Owns all conversation state. Kept separate from the components so the chat
 * behaviour can be tested without rendering the UI.
 */
export function useChatStore(onUnauthorized: () => void): ChatState {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // One client per auth mode, held in a ref so switching accounts rebuilds it.
  const apiRef = useRef<ChatApi | DemoChatApi | null>(null);
  const inFlight = useRef(false);

  const api = useMemo(() => {
    if (!apiRef.current) {
      const demoMode = config.demoMode || !config.cognito;
      apiRef.current = demoMode ? new DemoChatApi() : new ChatApi();
    }
    return apiRef.current;
  }, []);

  const applySessions = useCallback((next: ChatSession[]) => {
    setSessions(next);
    setActiveSessionId((current) => {
      if (current && next.some((s) => s.sessionId === current)) return current;
      const mostRecent = next[0];
      if (mostRecent) {
        try {
          localStorage.setItem(ACTIVE_SESSION_KEY, mostRecent.sessionId);
        } catch {
          /* ignore */
        }
        return mostRecent.sessionId;
      }
      try {
        localStorage.removeItem(ACTIVE_SESSION_KEY);
      } catch {
        /* ignore */
      }
      return null;
    });
  }, []);

  const reloadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const { sessions: loaded } = await api.listSessions();
      applySessions(loaded);
    } catch (err) {
      handleError(err);
    } finally {
      setLoadingSessions(false);
    }
    // handleError is stable enough for this hook's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, applySessions]);

  function handleError(err: unknown): void {
    if (err instanceof ApiError) {
      setError(err.message);
      if (err.requiresAuth) onUnauthorized();
      return;
    }
    setError(err instanceof Error ? err.message : 'Something went wrong.');
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.health();
        if (!cancelled) setHealth({ status: 'ok', live: true, region: 'us-east-1' });
      } catch {
        if (!cancelled) setHealth({ status: 'ok', live: false, region: 'unknown' });
      }
      try {
        const stored = safeReadActiveSession();
        if (stored && !cancelled) setActiveSessionId(stored);
        const { sessions: loaded } = await api.listSessions();
        if (!cancelled) applySessions(loaded);
      } catch (err) {
        if (!cancelled) handleError(err);
      } finally {
        if (!cancelled) setLoadingSessions(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, applySessions]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.sessionId === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  const selectSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
    try {
      localStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
    } catch {
      /* ignore */
    }
  }, []);

  const newSession = useCallback(() => {
    setActiveSessionId(null);
    setError(null);
    try {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const deleteSession = useCallback(
    async (sessionId: string) => {
      const previous = sessions;
      // Remove locally first so the list responds immediately.
      setSessions((current) => current.filter((s) => s.sessionId !== sessionId));
      setActiveSessionId((current) => (current === sessionId ? null : current));
      try {
        if (api instanceof ChatApi) await api.deleteSession(sessionId);
      } catch (err) {
        setSessions(previous);
        handleError(err);
      }
    },
    [api, sessions]
  );

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      // Double-submit guard: the button is disabled too, but Enter can race it.
      if (!trimmed || inFlight.current) return;

      inFlight.current = true;
      setSending(true);
      setError(null);

      const sessionId = activeSessionId ?? newSessionId();
      const optimistic: ChatMessage = {
        id: `pending-${Date.now()}`,
        role: 'user',
        content: trimmed,
        createdAt: new Date().toISOString(),
      };

      // Show the user's message right away, including for a brand new session.
      setSessions((current) => {
        const existing = current.find((s) => s.sessionId === sessionId);
        if (existing) {
          return current.map((s) =>
            s.sessionId === sessionId
              ? { ...s, messages: [...s.messages, optimistic], updatedAt: new Date().toISOString() }
              : s
          );
        }
        const created: ChatSession = {
          sessionId,
          title: deriveTitle([optimistic]),
          updatedAt: new Date().toISOString(),
          messages: [optimistic],
        };
        return [created, ...current];
      });
      if (!activeSessionId) selectSession(sessionId);

      try {
        const response = await api.sendMessage({ sessionId, message: trimmed });
        setSessions((current) =>
          current.map((s) => {
            if (s.sessionId !== sessionId) return s;
            // Replace the optimistic bubble with the authoritative pair.
            const withoutPending = s.messages.filter((m) => m.id !== optimistic.id);
            const hasBoth = withoutPending.some((m) => m.id === response.userMessage.id);
            const messages = hasBoth
              ? [...withoutPending, response.assistantMessage]
              : [...withoutPending, response.userMessage, response.assistantMessage];
            return {
              ...s,
              messages,
              title: deriveTitle(messages),
              updatedAt: new Date().toISOString(),
            };
          })
        );
      } catch (err) {
        handleError(err);
        // Drop the optimistic bubble so the input and transcript stay in sync.
        setSessions((current) =>
          current.map((s) =>
            s.sessionId === sessionId
              ? { ...s, messages: s.messages.filter((m) => m.id !== optimistic.id) }
              : s
          )
        );
      } finally {
        inFlight.current = false;
        setSending(false);
      }
    },
    [activeSessionId, api, selectSession]
  );

  const clearError = useCallback(() => setError(null), []);

  return {
    sessions,
    activeSessionId,
    messages: activeSession?.messages ?? [],
    loadingSessions,
    sending,
    error,
    health,
    sendMessage,
    selectSession,
    newSession,
    deleteSession,
    clearError,
    reloadSessions,
  };
}

function safeReadActiveSession(): string | null {
  try {
    return localStorage.getItem(ACTIVE_SESSION_KEY);
  } catch {
    return null;
  }
}
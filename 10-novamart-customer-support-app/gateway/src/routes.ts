import { Router, type Request, type Response, type NextFunction } from 'express';
import { authenticate, AuthError } from './auth.js';
import { config } from './config.js';
import * as history from './history.js';
import { invokeAgent, AgentError } from './agentcore.js';
import { randomUUID } from 'node:crypto';

const router = Router();

/** Attaches the verified user to the request, or 401s. */
async function requireAuth(req: Request, res: Response, next: NextFunction): Promise<void> {
  try {
    (req as Request & { principal?: { userId: string; email: string; unverified: boolean } }).principal =
      await authenticate(req.headers.authorization);
    next();
  } catch (error) {
    if (error instanceof AuthError) {
      res.status(error.status).json({ error: { code: error.code, message: error.message } });
      return;
    }
    res.status(401).json({ error: { code: 'UNAUTHORIZED', message: 'Sign in to continue.' } });
  }
}

/** Reads the principal attached by requireAuth without widening the Request type. */
function principal(req: Request): { userId: string; email: string; unverified: boolean } {
  return (req as Request & { principal?: { userId: string; email: string; unverified: boolean } }).principal!;
}

/** GET /api/health — liveness probe used by the UI to pick live vs. demo mode. */
router.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    live: Boolean(config.agentRuntimeArn) && !config.mockMode,
    region: config.awsRegion,
  });
});

/** GET /api/sessions — a per-user summary list, newest first. */
router.get('/sessions', requireAuth, async (req, res, next) => {
  try {
    const sessions = await history.listSessions(principal(req).userId);
    res.json({ sessions });
  } catch (error) {
    next(error);
  }
});

/**
 * POST /api/sessions/messages — the core chat turn.
 *
 * History is loaded before the agent runs so the runtime sees the full
 * conversation; both messages are then appended in one turn.
 */
router.post('/sessions/messages', requireAuth, async (req, res, next) => {
  const { sessionId: bodySession, message } = req.body ?? {};
  const user = principal(req);

  if (typeof message !== 'string' || message.trim().length === 0) {
    res.status(400).json({ error: { code: 'INVALID_INPUT', message: 'A message is required.' } });
    return;
  }
  if (message.length > config.maxMessageLength) {
    res.status(413).json({ error: { code: 'MESSAGE_TOO_LONG', message: 'Message exceeds the limit.' } });
    return;
  }

  // Reuse an existing session id so the agent keeps context; otherwise start one.
  const sessionId = typeof bodySession === 'string' && bodySession.length > 0 ? bodySession : randomUUID();

  // AgentCore requires runtimeSessionId to be at least 33 chars.
  const runtimeSessionId = `${user.userId}:${sessionId}`;

  try {
    // Load history so the agent gets context and the UI renders the full thread.
    const existing = await history.getSession(user.userId, sessionId);
    const userMessage = {
      id: `msg-${Date.now()}`,
      role: 'user' as const,
      content: message.trim(),
      createdAt: new Date().toISOString(),
    };

    // Persist the user's message before invoking so a failed call still saves history.
    await history.appendMessage({
      userId: user.userId,
      sessionId,
      message: userMessage,
      title: existing?.title ?? message.trim().slice(0, 60),
    });

    // The runtime session id is what gives the agent its memory across turns.
    const agentReply = await invokeAgent({
      message: message.trim(),
      runtimeSessionId,
      userId: user.userId,
      customerId: user.userId,
    });

    const assistantMessage = {
      id: `msg-${Date.now() + 1}`,
      role: 'assistant' as const,
      content: agentReply.text,
      createdAt: new Date().toISOString(),
    };

    await history.appendMessage({
      userId: user.userId,
      sessionId,
      message: assistantMessage,
      title: existing?.title ?? message.trim().slice(0, 60),
    });

    res.json({
      sessionId,
      userMessage,
      assistantMessage,
      history: existing?.messages ?? [],
    });
  } catch (error) {
    if (error instanceof AgentError) {
      res.status(error.status).json({ error: { code: error.code, message: error.message } });
      return;
    }
    next(error);
  }
});

/** DELETE /api/sessions/:id — removes a session and its messages. */
router.delete('/sessions/:id', requireAuth, async (req, res, next) => {
  const sessionId = req.params.id;
  if (!sessionId) {
    res.status(400).json({ error: { code: 'INVALID_INPUT', message: 'A session id is required.' } });
    return;
  }
  try {
    await history.deleteSession(principal(req).userId, sessionId);
    res.status(204).end();
  } catch (error) {
    next(error);
  }
});

export default router;
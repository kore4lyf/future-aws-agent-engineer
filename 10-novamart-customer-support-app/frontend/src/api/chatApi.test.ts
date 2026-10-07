import { describe, it, expect, beforeEach } from 'vitest';
import { DemoChatApi } from './chatApi.js';

describe('DemoChatApi', () => {
  beforeEach(() => {
    DemoChatApi.clearDemoSessions();
  });

  it('lists sessions from the demo store', async () => {
    const api = new DemoChatApi();
    const { sessions } = await api.listSessions();
    expect(Array.isArray(sessions)).toBe(true);
  });

  it('sends a message and returns a reply', async () => {
    const api = new DemoChatApi();
    const sessionId = 'sess-demo-001';
    const result = await api.sendMessage({ sessionId, message: 'Hello' });
    expect(result.userMessage.content).toBe('Hello');
    expect(result.assistantMessage.content.length).toBeGreaterThan(0);
    expect(result.sessionId).toBe(sessionId);
  });
});
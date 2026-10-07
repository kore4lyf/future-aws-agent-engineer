import { describe, it, expect } from 'vitest';
import { MockAuthService, MOCK_TOKEN, mockReplyFor } from './mockAgent.js';
import { config } from './config.js';

describe('mockAgent', () => {
  it('returns a deterministic reply for a known prompt', () => {
    expect(mockReplyFor('Where is my order NM-48213?')).toBe(
      'I can track that for you. Please share your order number (e.g. NM-48213) and I will pull it up.'
    );
  });

  it('returns the fallback for an unknown prompt', () => {
    const result = mockReplyFor('Tell me a story');
    expect(result).toContain('A NovaMart support specialist will review this shortly.');
  });
});

describe('config', () => {
  it('reads mockMode from env as a boolean', () => {
    expect(typeof config.mockMode).toBe('boolean');
  });
});

describe('MockAuthService', () => {
  it('authenticates in mock mode', async () => {
    if (!config.mockMode) {
      console.log('Mock mode is disabled; skipping mock auth test.');
      return;
    }
    const principal = await MockAuthService.authenticate();
    expect(principal.userId).toBe('demo-user');
    expect(principal.email).toBe('demo@novamart.example');
    expect(principal.unverified).toBe(true);
  });

  it('returns the demo token', () => {
    if (!config.mockMode) {
      console.log('Mock mode is disabled; skipping mock token test.');
      return;
    }
    expect(MockAuthService.token()).toBe(MOCK_TOKEN);
  });
});

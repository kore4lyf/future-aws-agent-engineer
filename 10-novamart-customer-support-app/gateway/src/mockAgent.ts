import { config } from './config.js';
import type { Principal } from './auth.js';

export const MOCK_TOKEN = 'demo.idtoken';

const REPLIES: Record<string, string> = {
  'where is my order':
    'I can track that for you. Please share your order number (e.g. NM-48213) and I will pull it up.',
  'how do i return an item':
    'Returns are accepted within 30 days of delivery. Start a return from your Orders page and I will walk you through the steps.',
  'i cannot log in to my account':
    'For account access, use the password-reset link on the sign-in screen. Support cannot view or change passwords directly.',
  'track my order':
    'Sure — I can help track your order. Please share the order number and I will check the status.',
  'return policy':
    'We accept returns within 30 days of delivery for unused items in original packaging.',
  'refund':
    'Refunds are processed after the return is received and inspected. You will receive an email confirmation when it completes.',
};

export function mockReplyFor(prompt: string): string {
  const q = prompt.toLowerCase();
  for (const [key, reply] of Object.entries(REPLIES)) {
    if (q.includes(key)) return reply;
  }
  return 'Thanks for reaching out. A NovaMart support specialist will review this shortly. Is there anything else I can help with?';
}

export class MockAuthService {
  static async authenticate(): Promise<Principal> {
    if (!config.mockMode) {
      throw new Error('Mock mode is not enabled.');
    }
    return { userId: 'demo-user', email: 'demo@novamart.example', unverified: true };
  }

  static token(): string {
    return MOCK_TOKEN;
  }
}
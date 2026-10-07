/**
 * Demo-mode auth service that implements the same AuthService interface
 * as the real Cognito one, so the frontend can be verified with vitest
 * without any AWS dependency.
 */

import type { AuthResult, AuthService, AuthTokens, SignUpResult } from './types';

export class DemoAuthService implements AuthService {
  readonly kind = 'demo' as const;

  async currentUser(): Promise<AuthResult | null> {
    return {
      user: { userId: 'demo', username: 'demo', email: 'demo@example.com' },
      tokens: { idToken: 'demo.idtoken', accessToken: 'demo.accessToken' },
    };
  }

  async signUp(_input: { email: string; password: string }): Promise<SignUpResult> {
    return { status: 'CONFIRMED', message: 'Account created.' };
  }

  async signIn(_input: { email: string; password: string }): Promise<AuthResult> {
    return await this.currentUser() as AuthResult;
  }

  async confirmSignUp(_input: { email: string; code: string }): Promise<AuthResult> {
    return await this.currentUser() as AuthResult;
  }

  async confirmChallenge(_input: {
    email: string;
    code?: string;
    password?: string;
  }): Promise<AuthResult> {
    return await this.currentUser() as AuthResult;
  }

  async signOut(): Promise<void> {}

  async refreshTokens(): Promise<AuthTokens | null> {
    return { idToken: 'demo.idtoken', accessToken: 'demo.accessToken' };
  }
}
import { DemoAuthService } from './demoAuthService';
import type { AuthService } from './types';
import { config } from '@/config';

let cached: AuthService | null = null;
let pending: Promise<AuthService> | null = null;

/**
 * Returns the auth service for the current configuration. Demo mode wins when
 * it is on, so the UI stays explorable even with Cognito values present.
 *
 * The Cognito implementation is imported lazily so demo mode never pulls the
 * Amplify bundle into the page.
 */
export async function getAuthService(): Promise<AuthService> {
  if (cached) return cached;
  if (config.demoMode || !config.cognito) {
    cached = new DemoAuthService();
    return cached;
  }
  if (!pending) {
    pending = import('./cognitoAuthService').then((mod) => {
      cached = new mod.CognitoAuthService();
      return cached;
    });
  }
  return pending;
}

/** Test seam: forces a specific auth service. */
export function setAuthService(service: AuthService | null): void {
  cached = service;
  pending = null;
}
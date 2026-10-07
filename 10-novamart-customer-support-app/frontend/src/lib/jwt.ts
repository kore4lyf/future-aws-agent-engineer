/**
 * Decodes a JWT without verifying it. The browser only needs the expiry to know
 * when to force a refresh; the gateway performs real signature verification.
 *
 * Returns null when the token is malformed or missing a `exp` claim.
 */
export function decodeJwtExpiry(token: string): number | null {
  const segments = token.split('.');
  if (segments.length !== 3) return null;

  try {
    const base64 = segments[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const json = decodeURIComponent(
      atob(padded)
        .split('')
        .map((c) => `%${`00${c.charCodeAt(0).toString(16)}`.slice(-2)}`)
        .join('')
    );
    const claims = JSON.parse(json) as { exp?: number };
    return typeof claims.exp === 'number' ? claims.exp : null;
  } catch {
    return null;
  }
}

/** True when the token is expired, or within `skewSeconds` of expiring. */
export function isTokenExpiring(token: string, skewSeconds = 60): boolean {
  const exp = decodeJwtExpiry(token);
  if (exp === null) return true;
  return exp - skewSeconds <= Date.now() / 1000;
}

export interface DecodedClaims {
  sub?: string;
  email?: string;
  'cognito:username'?: string;
  token_use?: string;
}

/** Reads the payload of a Cognito JWT for display purposes only. */
export function decodeJwtClaims(token: string): DecodedClaims | null {
  const segments = token.split('.');
  if (segments.length !== 3) return null;
  try {
    const base64 = segments[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');
    const json = atob(padded);
    return JSON.parse(json) as DecodedClaims;
  } catch {
    return null;
  }
}
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from 'jose';
import { config } from './config.js';

export interface Principal {
  /** Cognito subject, used to partition history per user. */
  userId: string;
  email: string;
  /** True when the token was accepted by mock mode rather than verified. */
  unverified: boolean;
}

export class AuthError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'AuthError';
    this.status = status;
    this.code = code;
  }
}

// The JWKS set is fetched once and cached by the remote key set, so every
// request after the first reuses the same public keys.
const jwksCache = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

function getJwks(region: string, userPoolId: string) {
  const cacheKey = `${region}/${userPoolId}`;
  let jwks = jwksCache.get(cacheKey);
  if (!jwks) {
    const issuer = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`;
    jwks = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks.json`));
    jwksCache.set(cacheKey, jwks);
  }
  return jwks;
}

function readBearer(header: string | undefined): string {
  if (!header?.startsWith('Bearer ')) {
    throw new AuthError(401, 'MISSING_TOKEN', 'Sign in to continue.');
  }
  const token = header.slice('Bearer '.length).trim();
  if (!token) throw new AuthError(401, 'MISSING_TOKEN', 'Sign in to continue.');
  return token;
}

/**
 * Verifies the caller's Cognito ID token and returns the principal it carries.
 *
 * Signature, issuer, audience, and expiry are all checked, so the gateway only
 * ever forwards a request whose identity came from the configured user pool.
 */
export async function authenticate(authHeader: string | undefined): Promise<Principal> {
  const token = readBearer(authHeader);

  if (config.mockMode) {
    // Demo mode accepts any well-formed token and trusts its claims, so the UI
    // can be exercised without AWS. Never enable this in production.
    return principalFromPayload(decodeUnsigned(token), true);
  }

  if (!config.userPoolId) {
    throw new AuthError(500, 'AUTH_NOT_CONFIGURED', 'Authentication is not configured.');
  }

  const region = config.userPoolRegion;
  const issuer = `https://cognito-idp.${region}.amazonaws.com/${config.userPoolId}`;
  const jwks = getJwks(region, config.userPoolId);

  try {
    const { payload } = await jwtVerify(token, jwks, {
      issuer,
      // Cognito's ID-token audience is the app client id.
      audience: config.userPoolClientId ?? undefined,
    });

    if (payload.token_use !== 'id') {
      throw new AuthError(401, 'WRONG_TOKEN_USE', 'An ID token is required.');
    }
    return principalFromPayload(payload, false);
  } catch (error) {
    if (error instanceof AuthError) throw error;
    // jose throws distinct errors for expiry, bad signature, and bad audience.
    const code = (error as { code?: string })?.code ?? 'INVALID_TOKEN';
    if (code === 'ERR_JWT_EXPIRED') {
      throw new AuthError(401, 'TOKEN_EXPIRED', 'Your session expired. Sign in again.');
    }
    throw new AuthError(401, 'INVALID_TOKEN', 'Your session is no longer valid.');
  }
}

function principalFromPayload(payload: JWTPayload | null, unverified: boolean): Principal {
  const userId = typeof payload?.sub === 'string' ? payload.sub : '';
  if (!userId) {
    throw new AuthError(401, 'INVALID_TOKEN', 'Token is missing a subject.');
  }
  return {
    userId,
    email: typeof payload?.email === 'string' ? payload.email : '',
    unverified,
  };
}

/** Reads a token's claims without checking the signature. Mock mode only. */
function decodeUnsigned(token: string): JWTPayload | null {
  const parts = token.split('.');
  if (parts.length !== 3) {
    throw new AuthError(401, 'INVALID_TOKEN', 'Malformed token.');
  }
  try {
    const json = Buffer.from(parts[1], 'base64url').toString('utf8');
    return JSON.parse(json) as JWTPayload;
  } catch {
    throw new AuthError(401, 'INVALID_TOKEN', 'Malformed token.');
  }
}
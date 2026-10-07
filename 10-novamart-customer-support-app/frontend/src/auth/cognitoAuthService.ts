import {
  getCurrentUser,
  signIn,
  signOut,
  signUp,
  fetchAuthSession,
  fetchUserAttributes,
  type SignUpOutput,
} from '@aws-amplify/auth';
import { Amplify } from 'aws-amplify';
import { config } from '@/config';
import { decodeJwtClaims } from '@/lib/jwt';
import type { AuthChallenge, AuthResult, AuthService, AuthTokens, AuthUser, SignUpResult } from './types';

/** Configures Amplify once, at module load. */
if (config.cognito) {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: config.cognito.userPoolId,
        userPoolClientId: config.cognito.userPoolClientId,
        loginWith: { email: true },
      },
    },
  });
}

let configured = Boolean(config.cognito);

/**
 * Configures Amplify lazily and only once. The first auth screen mounts before
 * env vars may be present in some setups, so configuration is idempotent.
 */
function ensureConfigured(): boolean {
  if (!config.cognito) return false;
  if (!configured) {
    Amplify.configure({
      Auth: {
        Cognito: {
          userPoolId: config.cognito.userPoolId,
          userPoolClientId: config.cognito.userPoolClientId,
          loginWith: { email: true },
        },
      },
    });
    configured = true;
  }
  return true;
}

function toAuthUser(userId: string, attributes: Record<string, string>): AuthUser {
  const email = attributes.email ?? '';
  return {
    userId,
    username: attributes['cognito:username'] ?? email,
    email,
  };
}

/** Maps the SDK's verbose signup result onto the three states the UI cares about. */
function mapSignUpOutput(output: SignUpOutput): SignUpResult {
  if (output.isSignUpComplete) {
    return { status: 'CONFIRMED', message: 'Account created. You are now signed in.' };
  }
  if (output.nextStep.signUpStep === 'CONFIRM_SIGN_UP') {
    const destination =
      output.nextStep.codeDeliveryDetails?.destination ??
      'your email address';
    return {
      status: 'UNCONFIRMED',
      message: `Almost there. We sent a confirmation code to ${destination}.`,
    };
  }
  return {
    status: 'UNKNOWN',
    message: 'Check your email to finish creating your account.',
  };
}

/**
 * Maps a sign-in challenge onto the shape the UI handles. Returns null when the
 * sign-in completed without an extra step.
 */
function challengeFromOutput(email: string, output: { nextStep?: { signInStep?: string } }): AuthChallenge | null {
  const step = output.nextStep?.signInStep;
  if (step === 'CONFIRM_SIGN_UP') return { step: 'CONFIRM_SIGN_UP', email };
  if (step === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
    return { step: 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED', email };
  }
  if (step === 'MFA_REQUIRED' || step === 'MFA_SETUP' || step === 'SELECT_MFA_TYPE') {
    return { step: 'MFA_REQUIRED', email };
  }
  return null;
}

/** Turns an SDK error into a message that is safe to show to a customer. */
function toFriendlyError(error: unknown): Error {
  const name = (error as { name?: string })?.name ?? '';
  const raw = error instanceof Error ? error.message : String(error);

  if (name === 'UserAlreadyExistsException' || /already exists/i.test(raw)) {
    return new Error('An account with that email already exists. Try signing in instead.');
  }
  if (name === 'UserNotFoundException') {
    return new Error('Incorrect username or password.');
  }
  if (name === 'NotAuthorizedException' || /Incorrect username or password/i.test(raw)) {
    return new Error('Incorrect username or password.');
  }
  if (name === 'PasswordResetRequiredException') {
    return new Error('Reset your password before signing in again.');
  }
  if (name === 'CodeMismatchException') {
    return new Error('That confirmation code is not valid. Request a new one.');
  }
  if (name === 'UserNotConfirmedException') {
    return new Error('Confirm your email address before signing in.');
  }
  return new Error(raw);
}

export class CognitoAuthService implements AuthService {
  readonly kind = 'cognito' as const;

  async currentUser(): Promise<AuthResult | null> {
    if (!ensureConfigured()) return null;
    try {
      const { userId, username } = await getCurrentUser();
      // Normalise the SDK's partial attribute map into a plain record.
      const attributes: Record<string, string> = {};
      try {
        const fetched = await fetchUserAttributes();
        for (const [key, value] of Object.entries(fetched ?? {})) {
          if (typeof value === 'string') attributes[key] = value;
        }
      } catch {
        // Attributes are optional context; a failure here must not block sign-in.
      }
      const tokens = await getAuthTokens();
      if (!tokens) return null;
      const attrs: Record<string, string> = {
        email: attributes.email ?? '',
        'cognito:username': attributes['cognito:username'] ?? username,
      };
      return { user: toAuthUser(userId, attrs), tokens };
    } catch {
      // A missing or expired stored session is a normal signed-out state.
      return null;
    }
  }

  async signUp(input: { email: string; password: string }): Promise<SignUpResult> {
    if (!ensureConfigured()) throw new Error('Authentication is not configured.');
    try {
      const output = await signUp({
        username: input.email,
        password: input.password,
        options: {
          userAttributes: { email: input.email },
          autoSignIn: true,
        },
      });
      return mapSignUpOutput(output);
    } catch (error) {
      throw toFriendlyError(error);
    }
  }

  async signIn(input: { email: string; password: string }): Promise<AuthResult | AuthChallenge> {
    if (!ensureConfigured()) throw new Error('Authentication is not configured.');
    try {
      const output = await signIn({ username: input.email, password: input.password });
      if (output.isSignedIn) {
        const tokens = await getAuthTokens();
        if (!tokens?.idToken) {
          throw new Error('Signed in, but could not load your profile.');
        }

        const claims = decodeJwtClaims(tokens.idToken) ?? {};
        const userId = typeof claims.sub === 'string' ? claims.sub : input.email;
        const email = typeof claims.email === 'string' ? claims.email : input.email;

        return {
          user: toAuthUser(userId, {
            email,
            'cognito:username': typeof claims['cognito:username'] === 'string' ? claims['cognito:username'] : email,
          }),
          tokens,
        };
      }

      // Surface whatever Cognito is asking for instead of failing with a
      // hard-coded message. The UI can then show the right form for it.
      const challenge = challengeFromOutput(input.email, output);
      if (!challenge) throw new Error('Sign in was not completed. Try again.');
      return challenge;
    } catch (error) {
      throw toFriendlyError(error);
    }
  }

  /**
   * Resolves a challenge surfaced by signIn. CONFIRM_SIGN_UP needs the code
   * Cognito emailed; the new-password challenge needs the new password.
   */
  async confirmSignUp(input: { email: string; code: string; password: string }): Promise<AuthResult> {
    if (!ensureConfigured()) throw new Error('Authentication is not configured.');
    const { confirmSignUp } = await import('@aws-amplify/auth');
    try {
      await confirmSignUp({ username: input.email, confirmationCode: input.code });
      
      // The user is confirmed, but not signed in - sign them in with their password
      const signInResult = await this.signIn({ email: input.email, password: input.password });
      if ('user' in signInResult) {
        return signInResult;
      }
      
      // If Cognito requires a challenge, surface it
      throw new Error('Account confirmed, but sign-in requires additional steps.');
    } catch (error) {
      throw toFriendlyError(error);
    }
  }

  async confirmChallenge(input: {
    email: string;
    code?: string;
    password?: string;
  }): Promise<AuthResult> {
    if (!ensureConfigured()) throw new Error('Authentication is not configured.');
    const { confirmSignIn } = await import('@aws-amplify/auth');
    try {
      if (input.code) {
        await confirmSignIn({ challengeResponse: input.code });
      } else if (input.password) {
        await confirmSignIn({ challengeResponse: input.password });
      } else {
        throw new Error('A code or password is required to continue.');
      }
      const user = await this.currentUser();
      if (!user) throw new Error('Signed in, but could not load your profile.');
      return user;
    } catch (error) {
      throw toFriendlyError(error);
    }
  }

  async signOut(): Promise<void> {
    if (!ensureConfigured()) return;
    try {
      await signOut();
    } catch {
      // Clearing a local session should succeed even if the revoke call fails.
    }
  }

  async refreshTokens(): Promise<AuthTokens | null> {
    return refreshSessionTokens();
  }
}

/** Returns the current ID and access tokens, or null when signed out. */
export async function getSessionTokens(): Promise<string | null> {
  if (!config.cognito) return null;
  try {
    const { tokens } = await fetchAuthSession();
    const idToken = tokens?.idToken;
    return idToken ? idToken.toString() : null;
  } catch {
    return null;
  }
}

/** Same tokens as `getSessionTokens`, in the shape the AuthService contract uses. */
export async function getAuthTokens(): Promise<AuthTokens | null> {
  if (!config.cognito) return null;
  try {
    const { tokens } = await fetchAuthSession();
    if (!tokens?.idToken) return null;
    return {
      idToken: tokens.idToken.toString(),
      accessToken: tokens.accessToken?.toString() ?? '',
    };
  } catch {
    return null;
  }
}

/** Forces a token refresh, used when the gateway reports an expired token. */
export async function refreshSessionTokens(): Promise<AuthTokens | null> {
  if (!config.cognito) return null;
  try {
    return await getAuthTokensForced();
  } catch {
    return null;
  }
}

async function getAuthTokensForced(): Promise<AuthTokens | null> {
  const { tokens } = await fetchAuthSession({ forceRefresh: true });
  if (!tokens?.idToken) return null;
  return {
    idToken: tokens.idToken.toString(),
    accessToken: tokens.accessToken?.toString() ?? '',
  };
}

/** Email of the signed-in user, read from the stored session. */
export async function getCurrentUserEmail(): Promise<string> {
  if (!config.cognito) return '';
  const claims = await getSessionTokens().then((t) => (t ? decodeJwtClaims(t) : null));
  return claims?.email ?? '';
}

export async function getUserSub(): Promise<string | null> {
  if (!config.cognito) return null;
  const token = await getSessionTokens();
  return token ? decodeJwtClaims(token)?.sub ?? null : null;
}
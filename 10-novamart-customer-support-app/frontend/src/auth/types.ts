/**
 * Auth provider abstraction.
 *
 * The UI talks to this interface, never to Amplify or the demo fake directly.
 * That keeps every screen testable and makes the Cognito wiring a one-file
 * change when the user pool is configured.
 */

export interface AuthUser {
  userId: string;
  username: string;
  email: string;
}

export interface AuthTokens {
  idToken: string;
  accessToken: string;
}

export interface AuthResult {
  user: AuthUser;
  tokens: AuthTokens;
}

export type SignUpStatus = 'CONFIRMED' | 'UNCONFIRMED' | 'UNKNOWN';

export interface SignUpResult {
  status: SignUpStatus;
  message: string;
}

/**
 * A sign-in step the UI must resolve before the session is usable.
 *
 * Surfaced explicitly instead of throwing a hard-coded message, so the app can
 * show the right form (code entry, new password, MFA) for whatever Cognito asks
 * for. `email` is the account to act on; `step` names the challenge.
 */
export type AuthChallenge =
  | { step: 'CONFIRM_SIGN_UP'; email: string; password?: string }
  | { step: 'CONFIRM_SIGN_IN'; email: string }
  | { step: 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED'; email: string }
  | { step: 'MFA_REQUIRED'; email: string };

export interface AuthService {
  readonly kind: 'cognito' | 'demo';

  /** Restores a previous session. Returns null when signed out. */
  currentUser(): Promise<AuthResult | null>;

  signUp(input: { email: string; password: string }): Promise<SignUpResult>;

  signIn(input: { email: string; password: string }): Promise<AuthResult | AuthChallenge>;

  /**
   * Confirms a sign-up with the code Cognito emailed.
   * `password` is optional; if provided, the user is signed in automatically after confirmation.
   */
  confirmSignUp(input: { email: string; code: string; password?: string }): Promise<AuthResult>;

  /**
   * Resolves a challenge surfaced by signIn.
   * - CONFIRM_SIGN_IN: the verification code Cognito emailed.
   * - CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED: the new password.
   */
  confirmChallenge(input: { email: string; code?: string; password?: string }): Promise<AuthResult>;

  signOut(): Promise<void>;

  /** Called when a request fails on an expired token. */
  refreshTokens(): Promise<AuthTokens | null>;
}
/**
 * Runtime configuration, read once from Vite env vars.
 *
 * Copy `.env.example` to `.env.local` and fill in the Cognito user pool values
 * plus the gateway URL before running `npm run dev`.
 */

interface CognitoConfig {
  userPoolId: string;
  userPoolClientId: string;
  /** Optional: only needed when the client uses a custom auth flow. */
  userPoolDomain?: string;
  signUpVerificationMethod: 'email';
}

interface AppConfig {
  region: string;
  cognito: CognitoConfig | false;
  /** Base URL of the gateway. Same-origin proxy in dev, absolute in prod. */
  gatewayUrl: string;
  /**
   * Demo mode swaps Cognito and the gateway for local fakes so the UI can be
   * exercised without any AWS account. Set VITE_DEMO_MODE=true.
   */
  demoMode: boolean;
}

function readCognito(): CognitoConfig | false {
  const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID?.trim();
  const userPoolClientId = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID?.trim();

  // A half-configured pool would fail deep inside the SDK with an opaque error,
  // so surface it while the app is still rendering its setup screen.
  if (!userPoolId || !userPoolClientId) {
    if (import.meta.env.VITE_DEMO_MODE !== 'true') {
      return false;
    }
    return false;
  }

  return {
    userPoolId,
    userPoolClientId,
    userPoolDomain: import.meta.env.VITE_COGNITO_DOMAIN?.trim() || undefined,
    signUpVerificationMethod: 'email',
  };
}

export const config: AppConfig = {
  region: import.meta.env.VITE_AWS_REGION?.trim() || 'us-east-1',
  cognito: readCognito(),
  gatewayUrl: import.meta.env.VITE_GATEWAY_URL?.trim() || '',
  demoMode: import.meta.env.VITE_DEMO_MODE === 'true',
};

export const isAuthConfigured = Boolean(config.cognito);
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { getAuthService } from '@/auth';
import type {
  AuthChallenge,
  AuthUser,
  SignUpResult,
} from '@/auth/types';

interface AuthContextValue {
  user: AuthUser | null;
  /** True while the stored session is being restored on first paint. */
  initialising: boolean;
  /** The pending challenge Cognito is asking for, or null when signed in. */
  challenge: AuthChallenge | null;
  signIn(email: string, password: string): Promise<void>;
  signUp(email: string, password: string): Promise<SignUpResult>;
  confirmSignUp(input: { email: string; code: string; password?: string }): Promise<void>;
  resolveChallenge(input: { code?: string; password?: string }): Promise<void>;
  signOut(): Promise<void>;
  clearChallenge(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [challenge, setChallenge] = useState<AuthChallenge | null>(null);
  const [initialising, setInitialising] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const auth = await getAuthService();
        const session = await auth.currentUser();
        if (!cancelled) setUser(session?.user ?? null);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setInitialising(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const auth = await getAuthService();
    const result = await auth.signIn({ email, password });
    if ('user' in result) {
      setUser(result.user);
      setChallenge(null);
    } else {
      // Cognito is asking for an extra step — show the right form.
      setChallenge(result);
    }
  }, []);

  const signUp = useCallback(async (email: string, password: string) => {
    const auth = await getAuthService();
    const result = await auth.signUp({ email, password });
    if (result.status === 'UNCONFIRMED') {
      // Surface the email-verification challenge so the UI can ask for the code.
      // Store password for sign-in after confirmation
      setChallenge({ step: 'CONFIRM_SIGN_UP', email, password });
      return result;
    }
    // autoSignIn leaves the pool already authenticated when no confirm step is
    // required, so read the session back rather than guessing.
    const session = await auth.currentUser();
    if (session) {
      setUser(session.user);
      setChallenge(null);
    }
    return result;
  }, []);

  const signOut = useCallback(async () => {
    const auth = await getAuthService();
    await auth.signOut();
    setUser(null);
    setChallenge(null);
  }, []);

  const confirmSignUp = useCallback(async (input: { email: string; code: string; password: string }) => {
    const auth = await getAuthService();
    const result = await auth.confirmSignUp(input);
    setUser(result.user);
    setChallenge(null);
  }, []);

  const resolveChallenge = useCallback(
    async (input: { code?: string; password?: string }) => {
      if (!challenge) return;
      const auth = await getAuthService();
      const result = await auth.confirmChallenge({
        email: challenge.email,
        code: input.code,
        password: input.password,
      });
      setUser(result.user);
      setChallenge(null);
    },
    [challenge]
  );

  const clearChallenge = useCallback(() => setChallenge(null), []);

  const value = useMemo(
    () => ({ user, initialising, challenge, signIn, signUp, confirmSignUp, resolveChallenge, signOut, clearChallenge }),
    [user, initialising, challenge, signIn, signUp, confirmSignUp, resolveChallenge, signOut, clearChallenge]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>.');
  return context;
}